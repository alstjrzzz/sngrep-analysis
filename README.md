# sngrep-analysis

고트래픽 환경에서 sngrep이 패킷을 드롭하는지, 드롭한다면 어디서 드롭하는지를 실측하는
sngrep 포크다.

sngrep은 캡처 스레드 하나에서 한 패킷의 캡처, 파싱, 그룹화를 pcap_loop 콜백 안에서 순서대로
처리하고(src/capture.c의 parse_packet), 화면 표시는 별도 스레드가 capture_cfg.lock을 공유하며
맡는다. 콜백이 리턴해야 다음 패킷을 꺼내므로, 처리가 도착 속도를 못 따라가면 커널 캡처
링버퍼가 넘쳐 드롭이 날 수 있다(pcap_stats의 ps_drop). 이 단일 스레드 처리가 병목으로 의심돼,
어디서 얼마나 드롭하고 그 스레드가 어디에 시간을 쓰는지 보려고 측정 코드를 달았다.

원본은 irontec/sngrep (GPLv3, https://github.com/irontec/sngrep) 이다. 빌드와 사용에 대한
일반 문서는 원본 README와 wiki(https://github.com/irontec/sngrep/wiki)를 참고하면 된다.
이 저장소는 거기에 측정 코드와 측정 자동화 스크립트를 더한 것이다.

## 1. 추가한 코드

포크 이후 추가하거나 수정한 코드는 다음과 같다. 측정 자동화 스크립트는 bench/ 한곳에 모여
있고, 그 외에는 sngrep 본체 세 파일에 측정 코드를 넣었다. 본체에 넣은 측정 코드는 원래 처리
흐름(IP/TCP 재조립, 파싱, 그룹화) 사이에 끼워 넣어야 시간을 잴 수 있어서 한곳에 모으지 못하고
capture.c와 sip.c에 흩어져 있다. 대신 모두 주석으로 표시해 원본 코드와 구분되게 했다.

| 위치 | 종류 | 내용 |
|---|---|---|
| src/capture.c | 드롭 측정 | 드롭 모니터 스레드. 캡처 소스마다 pcap_stats()를 주기적으로 읽어 받은/버린 패킷 수를 CSV로 남긴다. 캡처 스레드와 별도로 돌아서, 캡처가 막혀 있는 동안에도 계속 기록한다. |
| src/capture.c | 단계별 시간 측정 | 패킷 처리 함수(parse_packet)의 단계별 소요 시간을 잰다. 단계는 IP 재조립, TCP 재조립(TCP-SIP일 때만), 락 대기, 파싱+그룹화, 파일 기록이다. 기본은 꺼져 있다. |
| src/capture.h | 단계별 시간 측정 | 위 측정을 capture.c와 sip.c가 함께 쓰기 위한 변수/함수 선언. |
| src/sip.c | 단계별 시간 측정 | 위 "파싱+그룹화" 단계를 파싱(SIP 텍스트에서 필드 추출)과 그룹화(패킷을 해당 통화에 연결) 둘로 나눠 따로 잰다. |
| bench/ | 측정 자동화 | sngrep, SIPp(통화 발생기), CPU/RAM 샘플러를 한 번에 돌리고 결과를 그래프로 만든다. 자세한 사용법은 bench/README.md 참고. |

## 2. 환경과 리소스

OS는 Linux가 필수다. (sngrep은 POSIX 전용이라 Windows 네이티브 빌드가 안 된다.) 측정은
Ubuntu VM에서 한다.

기준 검증 VM은 Ubuntu 26.04 Desktop, 4 vCPU / 4GB RAM / 25GB, VirtualBox다. 호스트는
i5-1335U(10C/12T) / 16GB. 노트북이므로 측정할 때는 AC 전원에 연결하고 최고 성능 모드로
둔다. (배터리 throttling, 발열 throttling 주의.)

토폴로지는 발신(SIPp UAC), 수신(SIPp UAS), 캡처(sngrep)를 모두 한 VM 안에 두고 트래픽은
루프백(lo)으로 흘린다. lo도 커널 캡처 링버퍼(ps_drop)를 그대로 통과하므로 보려는 드롭이
재현된다. 물리 NIC을 끼우면 NIC 병목이 측정을 흐리기 때문에 일부러 lo를 쓴다.

의존성:

```bash
# 빌드
sudo apt install -y git build-essential autoconf automake libtool pkg-config \
    libpcap-dev libncurses-dev
# 측정 자동화 스크립트
sudo apt install -y tmux sip-tester python3-matplotlib sysstat
```

## 3. 테스트 구성

통화 발생률(초당 통화 수, cps)을 단계적으로 올리는 것을 기본 축으로 두고, 아래 차원을
바꿔가며 측정한다. 매 실행마다 ps_drop과 ps_ifdrop, 코어별 CPU, RAM이 같은 시간축에
기록되므로, 자원이 붕괴점에 영향을 줬는지 항상 함께 확인할 수 있다.

| 차원 | 값 | 답하는 질문 | 제어 변수 |
|---|---|---|---|
| 통화 발생률 (항상) | 100~8000 cps | 붕괴 PPS 지점 | RATES |
| 트래픽 종류 | signaling / hold / rtp | SIP 시그널링만 vs RTP 미디어 부하. SIP/RTP 분리 근거 | SCENARIO |
| 통화 유지 시간 | 0 / 30s / 60s | 동시 통화 수, 메모리, RTP 볼륨 | HOLD_MS |
| 커널 링버퍼 크기 | 2 / 16 / 64 MB | 버퍼만 키우면 막히는지 | BUFFER_MB |
| (옵션) vCPU 수 | 2 / 4 / 6 | 자원이 붕괴점을 좌우하는지 | VM 재시작(반자동) |

통화당 SIP 메시지가 약 7개이므로 pps는 대략 cps × 7이다. RTP 시나리오는 sngrep -r 옵션과
SIPp 미디어를 쓴다.

### 측정 항목 T1~T6

이 포크로 확인하려는 질문 목록이다. T는 test를 뜻하고, 각 항목이 하나의 질문이다.

- T1, 드롭이 실제로 나는가, 어디서 나는가: signaling 시나리오, 기본 -B 2. ps_drop과 ps_ifdrop을
  비교해 드롭이 커널 링버퍼에서 나는지 NIC에서 나는지 확인한다.
- T2, 원인이 뒷단 역압인가: 콜백 처리시간(추가 측정 예정)과 드롭 시점 비교.
- T3, 스파이크인가 추세인가: 트래픽 패턴(즉시 끊기 vs 유지) 비교.
- T4, 병목이 파싱인가: 단계별 시간 측정.
- T5, 표시와 캡처 스레드의 락 경합: capture_cfg.lock 대기시간(예정).
- T6, 링버퍼를 키우면 막히는가: BUFFER_MB 스윕.

## 4. 실행

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

- T1: sngrep은 부하에서 드롭한다. 전부 ps_drop(캡처 링버퍼)이고 ps_ifdrop은 0이다. 버퍼를
  64MB로 키워도 32% 드롭한다. 코어가 유휴고 RAM도 여유인데 드롭하므로 단일 스레드 한계로
  본다.
- T4: 캡처 스레드 시간의 90%가 파싱과 그룹화다(패킷당 약 104µs). 파싱 병렬화를 정당화한다.

## 7. 라이선스

원본 sngrep과 같이 GPLv3다 (COPYING, LICENSE). irontec/sngrep의 포크다.
