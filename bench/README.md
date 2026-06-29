# bench: sngrep 캡처 드롭 측정 하네스

T1 측정용 자동화 장치다. sngrep이 부하에서 패킷을 드롭하는지, 드롭한다면 어디서(커널 캡처
링버퍼 ps_drop인지, NIC ps_ifdrop인지), 그리고 호스트 CPU/RAM이 한계인지를 본다.

드롭 수치는 이 포크에 컴파일돼 들어간 pcap_stats 샘플러 스레드(src/capture.c)에서 나온다.
샘플러는 소스별 CSV를 쓰고, 이 하네스는 거기에 부하를 걸면서 CPU/RAM을 같은 시간축에
기록한다.

## 의존성 (Ubuntu)

```bash
sudo apt install -y tmux sip-tester python3-matplotlib
# sngrep 본체를 먼저 빌드해야 한다:  ./bootstrap.sh && ./configure && make -j$(nproc)
```

## 실행

저장소 루트에서 root 권한으로 실행한다. (raw 캡처에 권한이 필요하다.)

```bash
sudo ./bench/run_bench.sh
```

sngrep(분리된 tmux 페인), SIPp UAS, CPU/RAM 샘플러, SIPp UAC 램프를 모두 띄우고 단계별
램프를 돌린 뒤, 결과를 bench/results/<timestamp>_<scenario>_B<buffer>/ 에 저장한다.

그 다음 그래프를 그린다.

```bash
python3 bench/plot.py bench/results/<해당_폴더>
# 같은 폴더에 report.png를 생성한다
```

### 설정 (환경변수)

| 변수 | 기본값 | 의미 |
|-----|---------|------|
| SCENARIO | signaling | signaling(연결 후 즉시 BYE, 미디어 없음), hold(유지 후 BYE), rtp(RTP 미디어 + sngrep -r) |
| HOLD_MS | 5000 | hold 시나리오의 통화 유지 시간 |
| RATES | 100 500 1000 2000 4000 8000 | 콜레이트 단계(cps). 통화당 SIP 메시지 약 7개이므로 pps는 대략 cps × 7 |
| STAGE_SEC | 25 | 단계당 시간(초) |
| BUFFER_MB | 2 | sngrep -B 값, 커널 링버퍼 크기 (T6용으로 스윕) |
| INTERVAL_MS | 250 | 드롭 샘플러 간격 |

예:

```bash
sudo SCENARIO=hold HOLD_MS=8000 ./bench/run_bench.sh
sudo SCENARIO=rtp  RATES="100 1000 3000" ./bench/run_bench.sh
sudo BUFFER_MB=16  ./bench/run_bench.sh        # 링버퍼 스윕
```

## 출력 파일 (실행 폴더마다)

- stats.csv: 드롭 샘플러. ts_unix_ms,elapsed_ms,source,recv,drop,ifdrop,d_recv,d_drop,d_ifdrop,drop_pct
- sys.csv: 코어별 CPU%와 RAM(MB), 1초마다
- stages.csv: 타임스탬프와 콜레이트 대응. 단계 정렬용
- config.txt: 실행 파라미터
- report.png: 그래프

## 결과 읽는 법

- 어느 단계에서 d_drop이 양수가 되면 그 pps가 붕괴 시작점이다.
- ifdrop이 0으로 유지되면 드롭은 캡처 링버퍼에서 일어난 것이다. 즉 sngrep 유저스페이스가
  너무 느린 것이지 NIC 문제가 아니다.
- CPU 패널: 전체는 낮은데 한 코어만 100%면 sngrep 단일 스레드 한계다(깨끗한 결과). 모든
  코어가 100%면 CPU 경합이 결과에 영향을 준 것이다.
- RAM 패널: 평평하거나 한계 안에 머물면 메모리는 한계가 아니었다.

## 참고와 주의

- rtp 시나리오는 SIPp의 내장 uac_pcap을 쓰는데 미디어 pcap 파일이 필요하다. RTP가 흐르지
  않으면 SIPp 미디어 파일 연결이 빠진 것이니 그 사실을 보고한다.
- sngrep은 실제 TUI를 (tmux 안에서) 띄우므로 표시 경합이 측정에 포함된다. 표시 없는 변형이
  필요하면 sngrep을 -N 옵션으로 따로 돌린다.
- 결과 폴더는 git에서 제외된다.
