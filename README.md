# sngrep-analysis

고트래픽 환경에서 **sngrep이 패킷을 드롭하는지, 어디서 드롭하는지**를 실측하기 위한
sngrep 포크. 새 SIP 캡처 모니터링 툴을 설계하기 전에, "sngrep의 단일 스레드 직렬
처리(캡처→파싱→그룹화→표시)가 커널 캡처 링버퍼를 넘치게 한다"는 가설을 데이터로
검증하는 것이 목적이다.

> 원본: [irontec/sngrep](https://github.com/irontec/sngrep) (GPLv3). 빌드/사용 일반 문서는
> 원본 `README`·[wiki](https://github.com/irontec/sngrep/wiki) 참고. 이 저장소는 거기에
> **계측 코드와 측정 하네스**를 더한 것이다.

---

## 1. 검증하려는 가설

sngrep은 libpcap으로 캡처하고 **캡처·파싱·그룹화·표시를 단일 스레드에서 직렬로**
처리한다(`src/capture.c`의 `parse_packet`이 `pcap_loop` 콜백 안에서 전부 동기 실행).
이 콜백이 리턴해야 다음 패킷을 꺼내므로, 처리가 무거우면 그동안 **커널 캡처 링버퍼가
비워지지 않아 넘친다**. 드롭은 거의 항상 이 링버퍼에서 일어난다.

- 캡처 링버퍼 드롭 = `pcap_stats`의 `ps_drop` (← 우리가 노리는 것)
- NIC 하드웨어 드롭 = `ps_ifdrop`
- 파싱·그룹화·표시는 전역 뮤텍스(`capture_cfg.lock`) 하나로 직렬화되며, UI 렌더 스레드도
  같은 락을 잡는다 → 표시가 파싱을 멈춰 세운다.

## 2. 추가한 것

| 위치 | 내용 |
|---|---|
| `src/capture.c` | **드롭 모니터 스레드** — 온라인 소스마다 `pcap_stats()`를 주기 샘플링해 CSV로 기록. 캡처 락·파싱 경로를 건드리지 않아 측정을 왜곡하지 않고, `parse_packet`이 멈춰도 계속 샘플링한다. 환경변수 `SNGREP_STATS_CSV`, `SNGREP_STATS_INTERVAL_MS`. |
| `bench/` | **자동 측정 하네스** — sngrep(실제 TUI를 tmux에서) + SIPp UAS + 코어별 CPU/RAM 샘플러 + SIPp 콜레이트 램프를 한 방에 돌리고, 결과를 타임스탬프 폴더에 모아 matplotlib 그래프까지 생성. 자세한 사용법은 [`bench/README.md`](bench/README.md). |

## 3. 환경 / 리소스

- **OS**: Linux 필수 (sngrep은 POSIX 전용 — Windows 네이티브 빌드 불가). 측정은 Ubuntu VM에서.
- **검증 VM** (기준): Ubuntu 26.04 Desktop, **4 vCPU / 4GB RAM / 25GB**, VirtualBox.
  호스트는 i5-1335U(10C/12T) / 16GB. 노트북이라 측정 시 **AC 전원 + 최고 성능 모드** 권장
  (배터리 throttling / 발열 throttling 주의).
- **토폴로지**: 발신(SIPp UAC)·수신(SIPp UAS)·캡처(sngrep) 전부 한 VM 안, 트래픽은
  루프백(`lo`). `lo`도 커널 캡처 링버퍼(`ps_drop`)를 그대로 통과하므로 우리가 보려는
  드롭이 재현된다. 물리 NIC을 끼우면 NIC 병목이 측정을 흐리므로 의도적으로 `lo`를 쓴다.
- **의존성**:
  ```bash
  # 빌드
  sudo apt install -y git build-essential autoconf automake libtool pkg-config \
      libpcap-dev libncurses-dev
  # 측정 하네스
  sudo apt install -y tmux sip-tester python3-matplotlib sysstat
  ```

## 4. 테스트 구성 (차원)

콜레이트 램프를 독립변수로 두고, 아래 차원을 바꿔가며 측정한다. **매 실행마다
`ps_drop`/`ps_ifdrop` + 코어별 CPU + RAM이 같은 시간축에 기록**되어, 자원이
붕괴점에 영향을 줬는지 항상 함께 본다.

| 차원 | 값 | 답하는 질문 | 하네스 제어 |
|---|---|---|---|
| 콜레이트 램프 (항상) | 100→8000 cps | 붕괴 PPS 지점 | `RATES` |
| 트래픽 종류 | `signaling` / `hold` / `rtp` | SIP 시그널링만 vs RTP 미디어 부하 — SIP/RTP 분리 근거 | `SCENARIO` |
| 통화 유지 시간 | 0 / 30s / 60s | 동시 통화 수·메모리, RTP 볼륨 | `HOLD_MS` |
| 커널 링버퍼 크기 | 2 / 16 / 64 MB | 버퍼만 키우면 막히나 | `BUFFER_MB` |
| (옵션) vCPU 수 | 2 / 4 / 6 | 자원이 붕괴점을 좌우하나 | VM 재시작(반자동) |

> `~7 SIP msgs/call` 이므로 대략 `pps ≈ cps × 7`. RTP 시나리오는 sngrep `-r` + SIPp 미디어를 사용.

### 측정 항목 (연구 질문 매핑)

- **T1 — 드롭 실재/위치**: signaling 램프, 기본 `-B 2`. `ps_drop` vs `ps_ifdrop`로 위치 확인.
- **T2 — 원인이 뒷단 역압인가**: 콜백 처리시간(추가 계측 예정) vs 드롭 시점.
- **T3 — 스파이크 vs 추세**: 트래픽 패턴(즉시끊기 vs 유지) 비교.
- **T4 — 병목이 파싱인가**: 단계별 프로파일링(예정).
- **T5 — 표시/그룹화 락 경합**: `capture_cfg.lock` 대기시간(예정).
- **T6 — 링버퍼 효과**: `BUFFER_MB` 스윕.

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

`report.png` 3단 그래프:
1. received / dropped pps — 어느 단계에서 drop이 터지는지
2. 누적 drop %
3. CPU(전체 + 코어별) + RAM — **한 코어만 100%면 sngrep 단일 스레드 한계(자원 탓 아님),
   전 코어 100%면 CPU 경합 영향, RAM 평평하면 메모리는 무관**

## 7. 현재까지 결과

- **T1 입증 (2026-06-29, lo, 4vCPU/4GB VM)**: sngrep은 부하에서 드롭한다. 드롭은 전부
  `ps_drop`(캡처 링버퍼)이고 `ps_ifdrop`=0 → 유저공간(직렬 파싱)이 못 비워서 나는 역압.
  첫 측정에서 누적 ~35% 손실 관측. 정밀 붕괴 PPS·CPU 포화 여부는 하네스로 재측정 중.

## 8. 라이선스

원본 sngrep과 동일하게 GPLv3 (`COPYING`/`LICENSE`). irontec/sngrep의 포크임.
