---
name: memleak
description: Diagnose memory leaks and GC stalls on a running CPython process. Prefers memray when available; falls back to gdb+tracemalloc injection. Includes analysis script for snapshot diffing.
user-invocable: true
argument-hint: "<PID> [host] [--gc-only] | analyze <snapshot_files> | inject-script [output_dir] [--gc-only]"
allowed-tools: ["Bash", "Read", "Write", "Agent"]
---

# memleak

Diagnose memory leaks and GC stalls on running CPython processes without restart.

**Arguments:** $ARGUMENTS

## Modes

| Input | Action |
|-------|--------|
| `<PID>` | Generate diagnostic commands for a local process |
| `<PID> <host>` | Generate commands for a remote process (scp/ssh) |
| `<PID> [host] --gc-only` | Inject only gc.callbacks (near-zero overhead, no tracemalloc) |
| `analyze <files>` | Diff tracemalloc `.pkl` snapshots or point to memray `.bin` files |
| `inject-script [dir]` | Write the injection script to a directory (default `/tmp`) |
| `inject-script [dir] --gc-only` | Write gc.callbacks-only script (no tracemalloc) |

## Which tool to use

| Situation | Use | Why |
|-----------|-----|-----|
| Can restart the process | `memray run` | Best output (flamegraphs, temporal, native stacks), lowest overhead |
| Process already running, `memray` in env | `memray attach --aggregate` | Attaches live, produces `.bin` for analysis |
| Process already running, no `memray` in env | gdb + tracemalloc injection | Only needs stdlib (`gc`, `tracemalloc`) + gdb |
| GC stall diagnosis (any situation) | gdb + `gc.callbacks` injection | `memray` tracks allocations, not GC pause duration |
| Just need call stacks during a stall | `py-spy --nonblocking` | Read-only, confirms GC frames (`gc_collect_main`) |

**`gc.callbacks` is always useful** even when using memray, because memray doesn't report GC pause timing. Inject it alongside memray for stall correlation.

## Workflow

### Phase 1: Confirm the leak

Before injecting anything, confirm RSS is actually growing:

```bash
# Local
while true; do awk '/VmRSS/{printf "%s %s KB\n", strftime("%H:%M:%S"), $2}' /proc/<PID>/status; sleep 60; done

# Remote
ssh <host> 'while true; do echo "$(date +%H:%M:%S) $(awk "/VmRSS/{print \$2}" /proc/<PID>/status) KB"; sleep 60; done'
```

Look for linear growth. ~1MB/min = ~1.4GB/day. If RSS is flat, there's no leak.

### Phase 2: Choose approach and inject

#### Option A: memray (preferred when available)

Check if memray is installed in the target env:
```bash
# Remote
ssh <host> '<conda_env>/bin/python -c "import memray"'
```

If available:
```bash
# Attach to running process (produces .bin file)
memray attach <PID> --aggregate --output /tmp/memleak_memray.bin

# Or if you can restart:
memray run --output /tmp/memleak_memray.bin <command>
```

Analyze:
```bash
memray flamegraph /tmp/memleak_memray.bin -o /tmp/flamegraph.html
memray stats /tmp/memleak_memray.bin
memray tree /tmp/memleak_memray.bin
```

For temporal analysis (seeing growth over time):
```bash
memray flamegraph /tmp/memleak_memray.bin --temporal -o /tmp/temporal.html
```

#### Option B: gdb + tracemalloc (when memray is unavailable)

Write the injection script (`/tmp/memleak_diag.py`) with two components:

**gc.callbacks** -- confirms whether event loop stalls are GC:

```python
import gc, time

def _gc_cb(phase, info):
    if phase == "stop":
        gen = info["generation"]
        collected = info.get("collected", "?")
        uncollectable = info.get("uncollectable", 0)
        elapsed = time.perf_counter() - _gc_cb._start
        if elapsed > 0.01 or gen == 2:
            ts = time.strftime("%Y%m%d %H:%M:%S")
            print(f"{ts} GC gen={gen} collected={collected} uncollectable={uncollectable} {elapsed*1000:.1f}ms", flush=True)
    else:
        _gc_cb._start = time.perf_counter()
_gc_cb._start = 0
gc.callbacks.append(_gc_cb)
```

Key signals:
- `collected=0, uncollectable=0` with high elapsed: objects are reachable, not cycles. Look for growing dicts/caches.
- `uncollectable>0`: reference cycles with `__del__` methods. These are true leaks.
- `collected>0` with high elapsed: healthy GC but large heap. Consider `gc.freeze()` after startup.

**tracemalloc snapshots** -- periodic snapshots to disk for offline analysis:

```python
import tracemalloc, threading, pickle, time

tracemalloc.start(10)  # 10 frames deep

def _snap_loop():
    n = 0
    while True:
        time.sleep(300)  # 5 minutes
        snap = tracemalloc.take_snapshot()
        path = f"/tmp/memleak_snap_{n}.pkl"
        with open(path, "wb") as f:
            pickle.dump(snap, f)
        print(f"\n=== tracemalloc snapshot {n} ({path}) ===", flush=True)
        for s in snap.statistics("lineno")[:10]:
            print(f"  {s}", flush=True)
        n += 1

threading.Thread(target=_snap_loop, daemon=True).start()
print("Diagnostics injected: gc.callbacks + tracemalloc (5min snapshots)", flush=True)
```

**Injection command:**

```bash
# Same-uid ptrace works with ptrace_scope=1 (no sudo needed)
gdb -p <PID> -batch \
  -ex 'call (int)PyGILState_Ensure()' \
  -ex 'call (int)PyRun_SimpleString("exec(open(\"/tmp/memleak_diag.py\").read())")' \
  -ex 'call PyGILState_Release($1)'
```

Expected output: `[Inferior 1 (process <PID>) detached]`. DWARF version warnings are cosmetic (Python 3.13+ uses DWARF 5; older gdb warns but still works).

Output goes to wherever the process's stdout is redirected:
```bash
ls -la /proc/<PID>/fd/1  # shows stdout destination
```

#### Option C: gc.callbacks only (`--gc-only`)

When `--gc-only` is passed (or when the goal is just confirming GC stalls without finding the leak source), write and inject only the `gc.callbacks` script. Skip tracemalloc entirely.

**Overhead:** near-zero. One Python function call per GC cycle (~every few seconds). No per-allocation tracking, no memory overhead, no snapshot pauses. Safe for production during trading hours.

**When to use:** First step for any stall investigation. Confirms whether stalls are GC, which generation, duration, and collected count. If `gc.callbacks` shows growing gen-2 stall times, escalate to full tracemalloc injection (Option B) during a quieter period.

Write `/tmp/memleak_gc_only.py` with just the gc.callbacks code from Option B, then inject:
```bash
gdb -p <PID> -batch \
  -ex 'call (int)PyGILState_Ensure()' \
  -ex 'call (int)PyRun_SimpleString("exec(open(\"/tmp/memleak_gc_only.py\").read())")' \
  -ex 'call PyGILState_Release($1)'
```

### Phase 3: Analyze snapshots

Wait for 2+ snapshots (10+ minutes), then retrieve them:

```bash
scp <host>:/tmp/memleak_snap_*.pkl ./
```

Run the analysis script:

```bash
python3 ~/.claude/skills/memleak/analyze_snapshots.py snap_0.pkl snap_1.pkl snap_2.pkl snap_3.pkl
```

The script reports:
- **Top growers by size and count** for each consecutive pair
- **Full tracebacks** for allocations growing >50KB
- **Trend analysis** across all snapshots: `GROWING` (linear increase, leak confirmed) vs `PLATEAU` (stabilized, not a leak)
- **Summary** with estimated growth rate (MB/min, MB/day)

For memray `.bin` files, the script redirects to the appropriate `memray` commands.

### Phase 4: Verify the fix

After deploying a fix, re-run Phase 1 (RSS polling) to confirm growth stops. If RSS stabilizes but GC stalls persist, consider `gc.freeze()` after startup to exempt long-lived gen-2 objects from scanning.

## Permissions

| Requirement | Why |
|-------------|-----|
| Same-uid as process | `ptrace_scope=1` allows same-uid ptrace without `CAP_SYS_PTRACE` |
| Write to /tmp | Injection script and snapshots |
| gdb installed | For `PyRun_SimpleString` injection (Option B only) |

`py-spy --nonblocking` is an alternative for call-stack profiling. It confirms GC stalls (look for `gc_collect_main` frames) but doesn't identify the leak source. Needs same-uid or `CAP_SYS_PTRACE`.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file |
| `analyze_snapshots.py` | Diff tracemalloc `.pkl` snapshots, trend analysis, growth rate |

## Proven on

- queso CE BETA (PR #414): identified ~1MB/min leak in internal topic log event buffer via 4 snapshots over 20 minutes. gen-2 GC confirmed as stall cause (794ms, collected=0). Root cause: `LogEventBuffer` prune task never started for internal topic subscriber.
