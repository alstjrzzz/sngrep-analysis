#!/usr/bin/env bash
#
# bench/run_bench.sh - automated sngrep capture-drop benchmark (T1)
#
# Runs the whole rig in one shot: starts sngrep (real TUI, hosted in a detached
# tmux pane so it is scriptable), a SIPp UAS, a per-core CPU/RAM sampler, then a
# staged SIPp UAC call-rate ramp. Everything lands in a timestamped results dir.
#
# Run from the repo root, as root (raw capture needs CAP_NET_RAW):
#   sudo ./bench/run_bench.sh
#
# Override config via env, e.g.:
#   sudo SCENARIO=hold HOLD_MS=8000 ./bench/run_bench.sh
#   sudo SCENARIO=rtp  RATES="100 1000 3000" ./bench/run_bench.sh
#   sudo BUFFER_MB=16  ./bench/run_bench.sh        # sweep the kernel ring buffer (T6)
#
set -u

IFACE=${IFACE:-lo}
SNGREP=${SNGREP:-./src/sngrep}
SCENARIO=${SCENARIO:-signaling}        # signaling | hold | rtp
HOLD_MS=${HOLD_MS:-5000}               # call hold (ms) for hold scenario
RATES=${RATES:-100 500 1000 2000 4000 8000}
STAGE_SEC=${STAGE_SEC:-25}
GAP_SEC=${GAP_SEC:-3}
BUFFER_MB=${BUFFER_MB:-2}              # sngrep -B, the kernel capture ring buffer (default 2)
INTERVAL_MS=${INTERVAL_MS:-250}
PROFILE=${PROFILE:-0}                 # 1 = enable T4 per-stage profiling (profile.csv)
MAX_CALLS=${MAX_CALLS:-2000}          # SIPp -l: cap concurrent calls so hold/rtp don't OOM the VM
UAS_PORT=${UAS_PORT:-5060}
UAC_PORT=${UAC_PORT:-5061}

SYS_PID=""

# epoch milliseconds (portable: some `date` builds ignore %3N and emit full ns)
now_ms() { echo $(( $(date +%s%N) / 1000000 )); }

command -v tmux >/dev/null || { echo "need tmux:  sudo apt install -y tmux"; exit 1; }
command -v sipp >/dev/null || { echo "need sipp:  sudo apt install -y sip-tester"; exit 1; }
command -v python3 >/dev/null || { echo "need python3"; exit 1; }
[ -x "$SNGREP" ] || { echo "sngrep not built at $SNGREP (run make first)"; exit 1; }

SNG_RTP=""
case "$SCENARIO" in
  signaling) UAC_ARGS="-sn uac -d 0" ;;
  hold)      UAC_ARGS="-sn uac -d $HOLD_MS" ;;
  rtp)
    # self-contained RTP: generate the media pcap once, use our custom scenario,
    # and tell sngrep to capture RTP too (-r)
    [ -f bench/media/rtp_pcmu.pcap ] || python3 bench/media/gen_rtp_pcap.py bench/media/rtp_pcmu.pcap
    UAC_ARGS="-sf bench/scenarios/uac_rtp.xml"
    SNG_RTP="-r" ;;
  *) echo "unknown SCENARIO=$SCENARIO (signaling|hold|rtp)"; exit 1 ;;
esac

TS=$(date +%Y%m%d_%H%M%S)
OUT="bench/results/${TS}_${SCENARIO}_B${BUFFER_MB}"
mkdir -p "$OUT"
echo "scenario=$SCENARIO rates='$RATES' stage=${STAGE_SEC}s buffer=${BUFFER_MB}MB iface=$IFACE rtp=${SNG_RTP:-no} profile=$PROFILE" \
  | tee "$OUT/config.txt"

PROF_ENV=""
[ "$PROFILE" = "1" ] && PROF_ENV="SNGREP_PROFILE=1 SNGREP_PROFILE_CSV=$PWD/$OUT/profile.csv"

cleanup() {
  [ -n "$SYS_PID" ] && kill "$SYS_PID" 2>/dev/null
  tmux kill-session -t sng_bench 2>/dev/null
  tmux kill-session -t uas_bench 2>/dev/null
}
trap cleanup EXIT INT TERM

# 1) sngrep in a detached tmux pane (real ncurses workload, but scriptable)
tmux kill-session -t sng_bench 2>/dev/null
tmux new-session -d -s sng_bench -x 220 -y 50 \
  "$PROF_ENV SNGREP_STATS_CSV=$PWD/$OUT/stats.csv SNGREP_STATS_INTERVAL_MS=$INTERVAL_MS $SNGREP -d $IFACE -B $BUFFER_MB -l 5000 -R $SNG_RTP"
sleep 3
[ -f "$OUT/stats.csv" ] || echo "WARN: stats.csv missing - sngrep may have failed. Debug: tmux attach -t sng_bench"

# 2) SIPp UAS in a detached tmux pane
tmux kill-session -t uas_bench 2>/dev/null
tmux new-session -d -s uas_bench "sipp -sn uas -p $UAS_PORT"
sleep 1

# 3) per-core CPU + RAM sampler
python3 bench/sample_sys.py > "$OUT/sys.csv" &
SYS_PID=$!

# 4) staged UAC call-rate ramp
ulimit -n 65535 2>/dev/null
echo "ts_unix_ms,rate_cps" > "$OUT/stages.csv"
for RATE in $RATES; do
  echo "$(now_ms),$RATE" >> "$OUT/stages.csv"
  echo ">>> rate=${RATE}cps for ${STAGE_SEC}s"
  timeout "${STAGE_SEC}s" sipp $UAC_ARGS "127.0.0.1:$UAS_PORT" -p "$UAC_PORT" \
      -r "$RATE" -rp 1000 -l "$MAX_CALLS" -nostdin >/dev/null 2>&1
  sleep "$GAP_SEC"
done
echo "$(now_ms),done" >> "$OUT/stages.csv"

sleep 1
cleanup
trap - EXIT INT TERM

echo
echo "Done. Results: $OUT"
echo "Plot:  python3 bench/plot.py $OUT"
[ "$PROFILE" = "1" ] && echo "Profile: python3 bench/plot_profile.py $OUT"
