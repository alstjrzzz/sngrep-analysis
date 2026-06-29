#!/usr/bin/env python3
"""Sample per-core CPU utilization and memory once per second to CSV (stdout).

Reads /proc/stat and /proc/meminfo so there is no dependency on mpstat/sysstat.
Columns: ts_unix_ms, cpu_all_pct, cpu0_pct, cpu1_pct, ..., mem_used_mb, mem_avail_mb
"""
import time
import sys


def read_stat():
    cpus = {}
    with open('/proc/stat') as f:
        for line in f:
            if not line.startswith('cpu'):
                continue
            parts = line.split()
            name = parts[0]
            vals = list(map(int, parts[1:]))
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
            total = sum(vals)
            cpus[name] = (total, idle)
    return cpus


def read_mem():
    info = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, _, rest = line.partition(':')
            info[k] = int(rest.strip().split()[0])  # value in kB
    total = info.get('MemTotal', 0)
    avail = info.get('MemAvailable', 0)
    return (total - avail) // 1024, avail // 1024  # MB


def main():
    prev = read_stat()
    cores = sorted((c for c in prev if c != 'cpu'), key=lambda x: int(x[3:]))
    header = ['ts_unix_ms', 'cpu_all_pct'] + [c + '_pct' for c in cores] \
        + ['mem_used_mb', 'mem_avail_mb']
    print(','.join(header))
    sys.stdout.flush()

    while True:
        time.sleep(1)
        cur = read_stat()
        row = [str(int(time.time() * 1000))]
        for name in ['cpu'] + cores:
            t0, i0 = prev[name]
            t1, i1 = cur[name]
            dt, di = t1 - t0, i1 - i0
            busy = 100.0 * (dt - di) / dt if dt > 0 else 0.0
            row.append('%.1f' % busy)
        mu, ma = read_mem()
        row += [str(mu), str(ma)]
        print(','.join(row))
        sys.stdout.flush()
        prev = cur


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
