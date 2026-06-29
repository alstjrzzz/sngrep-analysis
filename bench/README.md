# bench/ — sngrep capture-drop measurement harness

Automated rig for T1: does sngrep drop packets under load, where (kernel capture
ring buffer `ps_drop` vs NIC `ps_ifdrop`), and is the host CPU/RAM the limiter.

The drop numbers come from the `pcap_stats` sampler thread compiled into this fork
(`src/capture.c`); it writes a per-source CSV. This harness drives load against it
and records CPU/RAM on the same time axis.

## Dependencies (Ubuntu)

```bash
sudo apt install -y tmux sip-tester python3-matplotlib
# sngrep itself must be built first:  ./bootstrap.sh && ./configure && make -j$(nproc)
```

## Run

From the repo root, as root (raw capture needs privileges):

```bash
sudo ./bench/run_bench.sh
```

It starts everything (sngrep in a detached tmux pane, SIPp UAS, CPU/RAM sampler,
SIPp UAC ramp), runs the staged ramp, and drops results into
`bench/results/<timestamp>_<scenario>_B<buffer>/`.

Then plot:

```bash
python3 bench/plot.py bench/results/<that_dir>
# writes report.png in the same dir
```

### Config (env vars)

| var | default | meaning |
|-----|---------|---------|
| `SCENARIO` | `signaling` | `signaling` (connect+immediate BYE, no media), `hold` (hold then BYE), `rtp` (RTP media + sngrep `-r`) |
| `HOLD_MS` | `5000` | call hold for `hold` scenario |
| `RATES` | `100 500 1000 2000 4000 8000` | call-rate stages (cps); ~7 SIP msgs/call so pps ≈ cps×7 |
| `STAGE_SEC` | `25` | seconds per stage |
| `BUFFER_MB` | `2` | sngrep `-B`, the kernel ring buffer size (sweep this for T6) |
| `INTERVAL_MS` | `250` | drop-sampler interval |

Examples:

```bash
sudo SCENARIO=hold HOLD_MS=8000 ./bench/run_bench.sh
sudo SCENARIO=rtp  RATES="100 1000 3000" ./bench/run_bench.sh
sudo BUFFER_MB=16  ./bench/run_bench.sh        # ring-buffer sweep
```

## Output files (per run dir)

- `stats.csv` — drop sampler: `ts_unix_ms,elapsed_ms,source,recv,drop,ifdrop,d_recv,d_drop,d_ifdrop,drop_pct`
- `sys.csv` — per-core CPU% + RAM (MB) once/sec
- `stages.csv` — timestamp → call rate, for aligning stages
- `config.txt` — the run parameters
- `report.png` — the plot

## Reading the result

- **`d_drop` goes positive** at some stage → that pps is the collapse onset.
- **`ifdrop` stays 0** → drop is at the capture ring buffer, i.e. sngrep userspace
  too slow (the document's ②), not the NIC.
- **CPU panel**: one core pegged at 100% while total stays low → single-thread
  sngrep limit (clean). All cores pegged → CPU contention influenced the result.
- **RAM panel**: flat/bounded → memory was not the limiter.

## Notes / caveats

- The `rtp` scenario uses SIPp's embedded `uac_pcap`, which needs media pcap files;
  if RTP does not flow, that scenario needs the SIPp media files wired up — report it.
- sngrep runs the real TUI (inside tmux) so display contention is included. For a
  display-free variant, run sngrep with `-N` separately.
- Results dirs are git-ignored.
