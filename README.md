# sngrep-analysis

고트래픽 환경에서 sngrep이 패킷을 드롭하는지, 드롭한다면 어디서 드롭하는지를 실측하기
위한 sngrep 포크다. 새 SIP 캡처 모니터링 툴을 설계하기 전에, sngrep의 단일 스레드 직렬
처리(캡처, 파싱, 그룹화, 표시)가 커널 캡처 링버퍼를 넘치게 한다는 가설을 데이터로 검증하는
것이 목적이다.

원본은 irontec/sngrep (GPLv3, https://github.com/irontec/sngrep) 이다. 빌드와 사용에 대한
일반 문서는 원본 README와 wiki(https://github.com/irontec/sngrep/wiki)를 참고하면 된다.
이 저장소는 거기에 계측 코드와 측정 하네스를 더한 것이다.

## 1. 검증하려는 가설

sngrep은 libpcap으로 패킷을 캡처하고, 캡처부터 파싱, 그룹화, 표시까지를 단일 스레드에서
순서대로 처리한다. (src/capture.c의 parse_packet이 pcap_loop 콜백 안에서 모든 단계를 동기
실행한다.) 이 콜백이 리턴해야 다음 패킷을 꺼내므로, 한 패킷 처리가 무거우면 그동안 커널
캡처 링버퍼가 비워지지 않고 넘친다. 드롭은 거의 항상 이 링버퍼에서 발생한다.

측정 대상은 캡처 링버퍼 드롭, 즉 pcap_stats의 ps_drop 값이다. NIC 하드웨어 드롭(ps_ifdrop)과
구분해서 본다. 또한 파싱, 그룹화, 표시는 전역 뮤텍스(capture_cfg.lock) 하나로 직렬화되고
UI 렌더 스레드도 같은 락을 잡기 때문에, 화면을 갱신하는 동안에는 파싱이 진행되지 못한다.

## 2. 추가한 코드

포크 이후 추가하거나 수정한 코드는 다음과 같다. 측정 하네스는 bench/ 한곳에 모여 있고,
그 외에는 sngrep 본체 세 파일에 계측 코드를 넣었다.

표의 T1, T4는 측정하려는 연구 질문 번호다(4장 측정 항목 참고). T1은 드롭이 실제로 나는지와
어디서 나는지, T4는 병목이 파싱인지를 본다. 본체에 넣은 계측 코드는 원래 처리 흐름(IP/TCP
재조립, 파싱, 그룹화) 사이에 끼워 넣어야 시간을 잴 수 있어서 한곳에 모으지 못하고 capture.c와
sip.c 안에 흩어져 있다. 대신 모두 T1, T4 주석을 달아 원본 코드와 구분되게 했고, 어느 파일의
무엇인지는 아래 표로 정리한다.

| 위치 | 종류 | 내용 |
|---|---|---|
| src/capture.c | T1 계측 | 드롭 모니터 스레드. 온라인 소스마다 pcap_stats()를 주기적으로 샘플링해 CSV로 기록한다. 캡처 락과 파싱 경로를 건드리지 않아 측정을 왜곡하지 않고, parse_packet이 멈춰도 계속 샘플링한다. 환경변수 SNGREP_STATS_CSV, SNGREP_STATS_INTERVAL_MS로 제어한다. |
| src/capture.c | T4 계측 | parse_packet 단계별 타이머(IP 재조립, TCP 재조립, 락 대기, 파싱+그룹화, 덤프)를 누적해 profile.csv로 기록한다. SNGREP_PROFILE이 설정됐을 때만 켜져서 T1 드롭 측정에는 부담을 주지 않는다. |
| src/capture.h | T4 계측 | sip.c와 공유하는 프로파일링 전역 변수와 prof_now_ns() 선언. |
| src/sip.c | T4 계측 | sip_check_packet 안에서 파싱(정규식, 페이로드 파싱)과 그룹화(Call-ID 조회, 메시지 추가, 상태 갱신) 시간을 따로 잰다. |
| bench/ | 측정 하네스 | sngrep(실제 TUI를 tmux에서 구동), SIPp UAS, 코어별 CPU/RAM 샘플러, SIPp 콜레이트 램프를 한 번에 돌리고 결과를 타임스탬프 폴더에 모아 matplotlib 그래프까지 만든다. 자세한 사용법은 bench/README.md 참고. |

## 3. 환경과 리소스

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
# 측정 하네스
sudo apt install -y tmux sip-tester python3-matplotlib sysstat
```

## 4. 테스트 구성

콜레이트 램프를 독립변수로 두고 아래 차원을 바꿔가며 측정한다. 매 실행마다 ps_drop과
ps_ifdrop, 코어별 CPU, RAM이 같은 시간축에 기록되므로, 자원이 붕괴점에 영향을 줬는지 항상
함께 확인할 수 있다.

| 차원 | 값 | 답하는 질문 | 하네스 제어 |
|---|---|---|---|
| 콜레이트 램프 (항상) | 100~8000 cps | 붕괴 PPS 지점 | RATES |
| 트래픽 종류 | signaling / hold / rtp | SIP 시그널링만 vs RTP 미디어 부하. SIP/RTP 분리 근거 | SCENARIO |
| 통화 유지 시간 | 0 / 30s / 60s | 동시 통화 수, 메모리, RTP 볼륨 | HOLD_MS |
| 커널 링버퍼 크기 | 2 / 16 / 64 MB | 버퍼만 키우면 막히는지 | BUFFER_MB |
| (옵션) vCPU 수 | 2 / 4 / 6 | 자원이 붕괴점을 좌우하는지 | VM 재시작(반자동) |

통화당 SIP 메시지가 약 7개이므로 pps는 대략 cps × 7이다. RTP 시나리오는 sngrep -r 옵션과
SIPp 미디어를 쓴다.

### 측정 항목

연구 질문과의 매핑은 다음과 같다.

- T1, 드롭 실재와 위치: signaling 램프, 기본 -B 2. ps_drop과 ps_ifdrop으로 위치를 확인한다.
- T2, 원인이 뒷단 역압인가: 콜백 처리시간(추가 계측 예정)과 드롭 시점 비교.
- T3, 스파이크인가 추세인가: 트래픽 패턴(즉시 끊기 vs 유지) 비교.
- T4, 병목이 파싱인가: 단계별 프로파일링.
- T5, 표시/그룹화 락 경합: capture_cfg.lock 대기시간(예정).
- T6, 링버퍼 효과: BUFFER_MB 스윕.

## 5. 실행

```bash
./bootstrap.sh && ./configure && make -j$(nproc)   # 계측 포함 빌드
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

## 6. 결과 해석

report.png는 3단 그래프다.

1. received / dropped pps: 어느 단계에서 드롭이 터지는지
2. 누적 드롭 비율
3. CPU(전체와 코어별)와 RAM. 한 코어만 100%면 sngrep 단일 스레드 한계이고(자원 탓이
   아님), 전 코어가 100%면 CPU 경합의 영향이며, RAM이 평평하면 메모리는 무관하다.

## 7. 현재까지 결과

전체 측정 결과 리포트는 RESULTS.md에 있다. 요약하면,

- T1: sngrep은 부하에서 드롭한다. 전부 ps_drop(캡처 링버퍼)이고 ps_ifdrop은 0이다. 버퍼를
  64MB로 키워도 32% 드롭한다. 코어가 유휴고 RAM도 여유인데 드롭하므로 단일 스레드 한계로
  본다.
- T4: 캡처 스레드 시간의 90%가 파싱과 그룹화다(패킷당 약 104µs). 파싱 병렬화를 정당화한다.

## 8. 라이선스

원본 sngrep과 같이 GPLv3다 (COPYING, LICENSE). irontec/sngrep의 포크다.
