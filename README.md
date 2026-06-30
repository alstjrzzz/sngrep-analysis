# sngrep-analysis

고트래픽 환경에서 sngrep의 패킷 드롭을 실측하는 sngrep fork.

sngrep은 캡처 스레드 하나가 한 패킷의 캡처, 파싱, 그룹화를 순서대로 처리하고, 화면 표시는
별도 스레드가 맡는다. 캡처 콜백이 끝나야 다음 패킷을 꺼내므로 캡처 스레드가 패킷 도착 속도를 
못 따라가면 커널 링버퍼에서 드롭이 난다고 가정했다. 실제 드롭 여부와 위치, 원인, 시점 및 
캡처 스레드의 작업 시간 구성을 확인하기 위한 측정 코드와 자동화 스크립트를 제공한다.

sngrep에 대한 정보는 원본 README와 wiki를 참고하면 된다.
[irontec/sngrep](https://github.com/irontec/sngrep)
[irontec/sngrep/wiki](https://github.com/irontec/sngrep/wiki)

## 1. 추가한 코드

포크 이후 추가하거나 수정한 코드는 다음과 같다. 측정 자동화 스크립트는 bench/ 한곳에 모여
있고, 그 외에는 sngrep 본체 세 파일에 측정 코드를 넣었다. 본체에 넣은 측정 코드는 원래 처리
흐름(IP/TCP 재조립, 파싱, 그룹화) 사이에 끼워 넣어야 시간을 측정할 수 있어서 한곳에 모으지 못하고
capture.c와 sip.c에 흩어져 있다. 대신 모두 주석으로 표시해 원본 코드와 구분되게 했다.

| 위치 | 종류 | 내용 |
|---|---|---|
| src/capture.c | 드롭 측정 | 드롭 모니터 스레드. 캡처 소스마다 커널의 캡처 통계를 주기적으로 읽어 받은/버린 패킷 수를 CSV로 남긴다. 캡처 스레드와 별도로 돌아서, 캡처가 막혀 있는 동안에도 계속 기록한다. |
| src/capture.c | 단계별 시간 측정 | 한 패킷을 처리하는 단계별 소요 시간을 잰다. 단계는 IP 재조립, TCP 재조립(TCP-SIP일 때), 락 대기, 파싱+그룹화, 파일 기록이다. 기본은 꺼져 있다. |
| src/capture.h | 단계별 시간 측정 | 위 측정을 capture.c와 sip.c가 함께 쓰기 위한 변수/함수 선언. |
| src/sip.c | 단계별 시간 측정 | 파싱+그룹화 단계를 파싱(SIP 텍스트에서 필드 추출)과 그룹화(패킷을 해당 통화에 연결)를 분리하여 측정한다. |
| bench/ | 측정 자동화 | sngrep, SIPp(통화 발생기), CPU/RAM 샘플러를 한 번에 돌리고 결과를 그래프로 제공한다. 자세한 사용법은 [bench/README.md](https://github.com/alstjrzzz/sngrep-analysis/blob/master/bench/README.md) 참고. |

## 2. 환경과 리소스

Linux가 필요하다. sngrep은 POSIX 전용이라 Windows에서는 빌드되지 않고, 측정하려는 드롭이
리눅스 커널 캡처 링버퍼에서 나는 현상이며, 측정 자동화도 apt 패키지(sip-tester, sysstat 등)에
의존하기 때문이다. 배포판은 Ubuntu를 권장한다.

측정은 VM에서 한다. 발신·수신·캡처를 한 머신에 격리해 재현성을 확보하고, 호스트 NIC 병목
없이 루프백(lo)으로만 트래픽을 흘리기 위해서다. 발신(SIPp UAC), 수신(SIPp UAS), 캡처(sngrep)를
한 VM 안에 두고 lo로 트래픽을 흘린다. lo도 커널 캡처 링버퍼를 그대로 통과하므로 보려는 드롭이
재현되고, 물리 NIC을 끼우면 NIC 병목이 측정을 흐리기 때문에 일부러 lo를 쓴다.

권장 사양과, 현재까지 결과(6장)를 낸 실제 검증 환경은 다음과 같다.

| 항목 | 권장 | 기준 검증 환경 |
|---|---|---|
| OS | Linux (Ubuntu) | Ubuntu 26.04 Desktop |
| vCPU | 2 이상 | 4 |
| RAM | 4GB 이상 | 4GB |
| 디스크 | 25GB 이상 | 25GB |
| 가상화 | — | VirtualBox |
| 호스트 | — | i5-1335U(10C/12T) / 16GB |

## 3. 테스트 구성

초당 통화 수를 단계적으로 올리는 것을 기본 축으로 두고, 아래 변수를
바꿔가며 측정한다. 매 실행마다 드롭 수, 코어별 CPU, RAM이 같은 시간축에 기록되므로, 리소스가
붕괴점에 영향을 줬는지 함께 확인할 수 있다.

| 변수 | 값 | 관찰 항목 |
|---|---|---|
| 초당 통화 수 (항상) | 100~8000 cps | 드롭이 시작되는 PPS 지점 |
| 트래픽 종류 | signaling / hold / rtp | RTP 미디어 부하가 드롭에 주는 영향 |
| 통화 유지 시간 | 0 / 30s / 60s | 동시 통화 수·메모리·RTP 볼륨 변화 |
| 커널 링버퍼 크기 | 2 / 16 / 64 MB | 버퍼 크기와 드롭의 관계 |

통화당 SIP 메시지가 약 7개이므로 pps는 대략 cps × 7이다. RTP 시나리오는 sngrep -r 옵션과
SIPp 미디어를 쓴다.

### 측정 항목

측정이 다루는 항목이다. T는 test를 뜻한다.

- T1, 드롭 발생 여부와 위치 — signaling 시나리오(기본 -B 2)에서 커널 캡처 링버퍼 드롭과
  NIC 드롭을 구분한다.
- T2, 뒷단 역압 여부 — 콜백 처리시간(추가 측정 예정)과 드롭 시점을 비교한다.
- T3, 드롭의 시간 양상 — 트래픽 패턴(즉시 끊기 vs 유지)을 비교해 스파이크와 추세를 가른다.
- T4, 파싱 병목 — 단계별 시간을 측정한다.
- T5, 표시·캡처 스레드 락 경합 — 락 대기시간을 측정한다(예정).
- T6, 링버퍼 확장의 드롭 완화 효과 — BUFFER_MB를 스윕한다.

## 4. 실행

의존성:

```bash
# 빌드
sudo apt install -y git build-essential autoconf automake libtool pkg-config \
    libpcap-dev libncurses-dev
# 측정 자동화 스크립트
sudo apt install -y tmux sip-tester python3-matplotlib sysstat
```

빌드하고 측정한다:

```bash
./bootstrap.sh && ./configure && make -j$(nproc)   # 측정 코드 포함 빌드
sudo ./bench/run_bench.sh                           # 기본 signaling 측정
sudo chown -R $USER:$USER bench/results
python3 bench/plot.py bench/results/<run_dir>       # report.png 생성
```

다른 차원 예:

```bash
sudo SCENARIO=hold HOLD_MS=30000 ./bench/run_bench.sh
sudo SCENARIO=rtp  RATES="100 1000 3000" ./bench/run_bench.sh
sudo BUFFER_MB=16  ./bench/run_bench.sh
```

## 5. 결과 해석

report.png는 3단 그래프다.

1. received / dropped pps: 어느 단계에서 드롭이 터지는지
2. 누적 드롭 비율
3. CPU(전체와 코어별)와 RAM. 한 코어만 100%면 sngrep 단일 스레드 한계이고(자원 탓이
   아님), 전 코어가 100%면 CPU 경합의 영향이며, RAM이 평평하면 메모리는 무관하다.

## 6. 현재까지 결과

전체 측정 결과 리포트는 RESULTS.md에 있다. 요약하면,

- T1: sngrep은 부하에서 드롭한다. 전부 커널 캡처 링버퍼 드롭이고 NIC 드롭은 0이다. 버퍼를
  64MB로 키워도 32% 드롭한다. 코어가 유휴고 RAM도 여유인데 드롭하므로 단일 스레드 한계로
  본다.
- T4: 캡처 스레드 시간의 90%가 파싱과 그룹화다(패킷당 약 104µs). 파싱 병렬화를 정당화한다.

## 7. 라이선스

원본 sngrep과 같이 GPLv3다 (COPYING, LICENSE). irontec/sngrep의 포크다.
