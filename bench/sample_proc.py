#!/usr/bin/env python3
"""Sample per-process CPU for sngrep and SIPp once per second to CSV (stdout).

Reads /proc/<pid>/stat directly, so there is no dependency on pidstat/sysstat.
Processes are grouped by command name (sngrep, sipp), so the short-lived UAC
that restarts each rate stage is still summed under "sipp".

CPU is reported as % of the whole machine (0-100), the same scale as
sample_sys.py's cpu_all_pct, so the columns are directly comparable:
sngrep + sipp + idle/others should track cpu_all.

Columns: ts_unix_ms, sngrep_pct, sipp_pct
"""
import os
import time
import sys

CLK_TCK = os.sysconf('SC_CLK_TCK')
NCPU = os.cpu_count() or 1
GROUPS = ('sngrep', 'sipp')


def read_jiffies():
    """Return {group: total utime+stime jiffies} summed over matching pids."""
    out = {g: 0 for g in GROUPS}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/%s/stat' % pid) as f:
                content = f.read()
        except (IOError, OSError):
            continue  # process vanished
        rp = content.rfind(')')
        if rp < 0:
            continue
        comm = content[content.find('(') + 1:rp]
        for g in GROUPS:
            if g in comm:
                fields = content[rp + 2:].split()
                # fields after comm: state is index 0 (stat field 3);
                # utime is stat field 14 -> index 11, stime field 15 -> index 12
                out[g] += int(fields[11]) + int(fields[12])
                break
    return out


def main():
    print('ts_unix_ms,' + ','.join(g + '_pct' for g in GROUPS))
    sys.stdout.flush()
    prev = read_jiffies()
    prev_t = time.time()
    while True:
        time.sleep(1)
        cur = read_jiffies()
        cur_t = time.time()
        dt = cur_t - prev_t
        row = [str(int(cur_t * 1000))]
        for g in GROUPS:
            dj = cur[g] - prev[g]
            pct = 100.0 * (dj / CLK_TCK) / (dt * NCPU) if dt > 0 else 0.0
            row.append('%.1f' % pct)
        print(','.join(row))
        sys.stdout.flush()
        prev, prev_t = cur, cur_t


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
