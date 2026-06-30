# sngrep-analysis

고트래픽 환경에서 sngrep의 패킷 드롭을 실측하는 sngrep fork.

sngrep은 캡처 스레드 하나가 한 패킷의 캡처, 파싱, 그룹화를 순서대로 처리하고, 화면 표시는
별도 스레드가 맡는다. 캡처 콜백이 끝나야 다음 패킷을 꺼내므로 캡처 스레드가 패킷 도착 속도를 
못 따라가면 커널 링버퍼에서 드롭이 난다고 가정했다. 실제 드롭 여부와 위치, 원인, 시점 및 
캡처 스레드의 작업 시간 구성을 확인하기 위한 측정 코드와 자동화 스크립트를 제공한다.

sngrep에 대한 정보는 원본 [README](https://github.com/irontec/sngrep#sngrep-)와 [wiki](https://github.com/irontec/sngrep/wiki)를 참고하면 된다.

## 1. 추가한 코드

포크 이후 추가하거나 수정한 코드는 다음과 같다. 측정 자동화 스크립트는 bench/ 한곳에 모여
있고, 그 외에는 sngrep 본체 세 파일에 측정 코드를 넣었다. 본체에 넣은 측정 코드는 원래 처리
흐름(IP/TCP 재조립, 파싱, 그룹화) 사이에 끼워 넣어야 시간을 측정할 수 있어서 한곳에 모으지 못하고
capture.c와 sip.c에 흩어져 있다. 대신 모두 주석으로 표시해 원본 코드와 구분되게 했다.

| 위치 | 종류 | 내용 |
|---|---|---|
| src/capture.c | 드롭 측정 | 드롭 모니터 스레드. 캡처 소스마다 커널의 캡처 통계를 주기적으로 읽어 받은/버린 패킷 수를 CSV로 남긴다. |
| src/capture.c | 단계별 시간 측정 | 한 패킷을 처리하는 단계별 소요 시간을 잰다. 단계는 IP 재조립, TCP 재조립(TCP-SIP일 때), 락 대기, 파싱+그룹화, 파일 기록이다. 기본은 꺼져 있다. |
| src/capture.h | 단계별 시간 측정 | 위 측정을 capture.c와 sip.c가 함께 쓰기 위한 변수/함수 선언. |
| src/sip.c | 단계별 시간 측정 | 파싱+그룹화 단계를 파싱(SIP 텍스트에서 필드 추출)과 그룹화(패킷을 해당 통화에 연결)를 분리하여 측정한다. |
| bench/ | 측정 자동화 | sngrep, SIPp(통화 발생기), CPU/RAM 샘플러를 한 번에 돌리고 결과를 그래프로 제공한다. 자세한 사용법은 [bench/README.md](https://github.com/alstjrzzz/sngrep-analysis/blob/master/bench/README.md) 참고. |

## 2. 환경과 리소스

| 항목 | 권장 | 기준 검증 환경 |
|---|---|---|
| OS | Only Linux (Ubuntu) | Ubuntu 26.04 Desktop |
| vCPU | 2 이상 | 4 |
| RAM | 4GB 이상 | 4GB |
| 디스크 | 25GB 이상 | 25GB |

sngrep이 POSIX 전용이라 Windows에서는 빌드되지 않는다.

호스트 NIC 병목에 의한 오염을 방지하기 위해 가상환경에서 측정한다.

## 3. 테스트 구성

초당 통화 수(CPS)를 단계적으로 올리는 것을 기본 축으로 두고, 아래 변수를
바꿔가며 측정한다. 매 실행마다 드롭 수, 코어별 CPU, RAM이 같은 시간축에 기록되므로, 리소스가
붕괴점에 영향을 줬는지 함께 확인할 수 있다.

| 변수 | 값 | 관찰 항목 |
|---|---|---|
| CPS | 100~8000 cps | 드롭이 시작되는 PPS 지점 |
| 트래픽 종류 | signaling / hold / rtp | RTP 미디어 부하가 드롭에 주는 영향 |
| 통화 유지 시간 | 0 / 30s / 60s | 동시 통화 수·메모리·RTP 볼륨 변화 |
| 커널 링버퍼 크기 | 2 / 16 / 64 MB | 버퍼 크기와 드롭의 관계 |

### 테스트 단계
- T1, 드롭 위치 구분: 커널 캡처 링버퍼 드롭과 NIC 드롭을 구분한다.
- T2, 처리 지연 측정: 콜백 처리시간과 드롭 시점을 비교한다.
- T3, 드롭 패턴 비교: 트래픽 유지 방식(즉시종료/유지)별 스파이크/추세를 비교한다.
- T4, 단계 내 병목 측정: 단계별 처리 시간을 측정한다.
- T5, 락 경합 측정: 표시·캡처 스레드 간 락 대기시간을 측정한다.
- T6, 버퍼 크기별 드롭률: 링버퍼 크기(2/16/64MB)별로 드롭률을 비교한다.

## 4. 실행

저장소 클론:
```bash
git clone https://github.com/alstjrzzz/sngrep-analysis.git
cd sngrep-analysis
```

패키지 설치:
```bash
sudo apt install -y git build-essential autoconf automake libtool pkg-config \
    libpcap-dev libncurses-dev
sudo apt install -y tmux sip-tester python3-matplotlib sysstat
```

빌드:
```bash
./bootstrap.sh && ./configure && make -j$(nproc)
```

기본 signaling 측정과 그래프 생성:
```bash
sudo ./bench/run_bench.sh
sudo chown -R $USER:$USER bench/results
python3 bench/plot.py bench/results/<run_dir>
```

다른 시나리오/버퍼 크기로 측정(선택):
```bash
sudo SCENARIO=hold HOLD_MS=30000 ./bench/run_bench.sh
sudo SCENARIO=rtp  RATES="100 1000 3000" ./bench/run_bench.sh
sudo BUFFER_MB=16  ./bench/run_bench.sh
```

## 5. 결과

초당 통화 수만 100에서 8000 cps까지 단계적으로 올린 signaling 측정이다(나머지 변수는 기본값).
트래픽 종류·유지시간·링버퍼 크기를 바꾼 결과는 RESULTS.md에 있다.

![signaling 측정](bench/results/20260629_045659_signaling_B2/report.png)

위에서부터 수신·드롭 패킷량, 누적 손실률, CPU·메모리 사용률, 코어별 CPU다. 드롭은 2000 cps
구간부터 시작하고, 전부 커널 캡처 링버퍼(ps_drop)에서 나며 NIC 드롭(ps_ifdrop)은 0이다.
드롭이 나는 동안에도 CPU 전체는 60~68%에 그치고(한 코어만 100%에 닿는다) RAM은 평평하다.
자원이 남는데 드롭한다.

![캡처 스레드 시간 구성](bench/results/20260629_073854_signaling_B2/profile.png)

캡처 스레드가 한 패킷을 처리하며 각 단계에 쓴 시간 구성이다. 90%가 파싱+그룹화이고 그 안에서
파싱이 약 73%다. 재조립·락·dump는 미미하다. 병목은 파싱이다.

버퍼 스윕(2/16/64MB), RTP, 정확한 수치는 [RESULTS.md](RESULTS.md)에 있다.

## 6. 라이선스

[irontec/sngrep/license](https://github.com/irontec/sngrep/blob/master/LICENSE)
