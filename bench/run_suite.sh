#!/usr/bin/env bash
#
# bench/run_suite.sh - OFAT sweep (one factor at a time from a baseline).
#
# Runs the meaningful single-dimension variations back to back, with a cooldown
# between runs so a thermally-limited laptop does not drift. NOT a full factorial
# (no multiplying dimensions together).
#
# From the repo root, as root:
#   sudo ./bench/run_suite.sh
#
# Tunable:
#   sudo COOLDOWN=60 ./bench/run_suite.sh
#
set -u

COOLDOWN=${COOLDOWN:-45}   # seconds between runs (thermal relief)

run() {
  echo
  echo "================ RUN: $* ================"
  env "$@" ./bench/run_bench.sh
  echo "---------------- cooldown ${COOLDOWN}s ----------------"
  sleep "$COOLDOWN"
}

# --- baseline: SIP signaling, default ring buffer (B2), full ramp ---
run SCENARIO=signaling

# --- ring-buffer sweep (T6): does just enlarging the kernel buffer fix it? ---
run SCENARIO=signaling BUFFER_MB=16
run SCENARIO=signaling BUFFER_MB=64

# --- RTP media: lower rates (media dominates pps; high cps would explode) ---
run SCENARIO=rtp RATES="100 300 600 1000"

# --- call hold duration: lower rates (concurrent calls grow with hold) ---
run SCENARIO=hold HOLD_MS=30000 RATES="100 300 600 1000"
run SCENARIO=hold HOLD_MS=60000 RATES="100 300 600 1000"

echo
echo "================ ALL RUNS DONE ================"

# plot every run + hand ownership back to the invoking user
if command -v python3 >/dev/null && python3 -c 'import matplotlib' 2>/dev/null; then
  for d in bench/results/*/; do
    [ -f "$d/stats.csv" ] && python3 bench/plot.py "$d"
  done
fi
[ -n "${SUDO_USER:-}" ] && chown -R "$SUDO_USER":"$SUDO_USER" bench/results 2>/dev/null

echo
echo "Results + report.png under bench/results/:"
ls -1 bench/results/
