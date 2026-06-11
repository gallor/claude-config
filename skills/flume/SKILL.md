---
name: flume
description: Run flume (Core log analyzer) on .log files, or extend it with new metrics. Auto-triggered when user asks to analyze, compare, or get performance from log files. Crystallizes ad-hoc rg/Python analysis into fast repeated Rust invocations.
user-invocable: true
argument-hint: "[description of new metric | run <logfiles> | --service <name> <logfiles>]"
allowed-tools: ["Bash", "Read", "Edit", "Write"]
---

# flume

**flume** — Core log analyzer. Sends your logs down the flume; metrics come out the other end.

- **Repo**: `~/git/flume/`
- **Binary**: `~/.local/bin/flume`
- **Build**: `cd ~/git/flume && cargo build --release`

**Arguments:** $ARGUMENTS

## Running

```bash
flume <log1> [log2 ...]                    # auto-detect service
flume --service queso <log1> [log2 ...]    # explicit service
```

Inputs: local files, `-` (stdin), or `host:path` (SSH, key auth required). Remote `.zst`/`.gz` files are auto-decompressed on the remote side. Globs expand on the remote shell.

```bash
flume chhq-supusir81:/sitelogs/bandit/blue/CondaPython/Sirius_CE_BETA_Queso/*.read.20260416*.log
```

Services: `queso`, `whip`, `generic`

Auto-detection peeks at up to 200 lines for identifying logger names and message patterns.

## Module structure

```
src/
  main.rs       — CLI, auto-detection, file loop
  services.rs   — Service enum + from_str
  stats.rs      — UniversalStats + service-specific Stats structs
  parse.rs      — Line parsing: parse_universal() + parse_service() dispatch
  output.rs     — print_report() + per-service print functions
```

**Universal** (all services): versions, errors, camus connections, startup timing
**Queso**: response latency, request types, queue pressure, heartbeats, topic waves
**Whip**: iter_poll timing, concurrency slot usage
**Generic**: response latency only

## Adding a new metric

### 1. Confirm the pattern

```bash
rg '<pattern>' <sample_log> | head -5
rg -c '<pattern>' <sample_log>
```

### 2. Decide: universal or service-specific?

- **Universal**: appears in any Core-logging service → add to `UniversalStats` + `parse_universal()` in `parse.rs`
- **Service-specific**: only in queso/whip/etc. → add to `*Stats` struct + `parse_*()` function in `parse.rs`

### 3. Add the field and parsing

In `stats.rs` (the appropriate struct + `::new()`):
```rust
pub my_metric: u64,   // in struct
my_metric: 0,          // in ::new()
```

In `parse.rs`:
```rust
// Count pattern:
if line.contains("MyPattern") {
    s.my_metric += 1;
}

// Timing pattern:
if line.contains("MyTiming=") {
    if let Some(ms) = extract_ms(line, "MyTiming=") {
        s.my_timings.push(ms);
    }
}
```

In `output.rs`, add to the relevant `print_*()` function:
```rust
if s.my_metric > 0 {
    header("MY SECTION");
    println!("  My metric: {}", s.my_metric);
    println!();
}
```

### 4. Build and verify

```bash
cd ~/git/flume && cargo build --release 2>&1
flume <logfile> | grep -A 3 "MY SECTION"
# Cross-check:
rg -c 'MyPattern' <logfile>
```

### 5. Evaluate rayon

**Not needed** unless files routinely exceed 500MB AND tool takes >2s. Current: ~300MB/s single-threaded, 0.4s on 370K lines. Re-evaluate if workload grows.

## Existing metrics reference

| Section | Trigger pattern | Service |
|---------|----------------|---------|
| STARTUP | "Manifest initial batch size" | Universal |
| CAMUS CONNECTIONS | "(consumer)" + "Login success" | Universal |
| RESPONSE LATENCY | "Responded to request" | Queso, Generic |
| REQUEST TYPES | "Processing 'TRANSACT_" | Queso |
| CONNECTIONS | "WebSocket connection.*open" | Queso |
| TOPIC WAVES | "profile/handle pairs" | Queso |
| HEARTBEAT CYCLES | "Sent and received.*heartbeats.*wall=" | Queso |
| ITER_POLL | "iter_poll.*duration=" | Whip |
| CONCURRENCY SLOTS | "REALTIME" / "HISTORICAL" | Whip |
| EVENT LOOP STALLS | Timestamp gap >200ms after "Processing '" | Universal |
| ERRORS | "|ERROR |" | Universal |

## Adding a new service

1. Add variant to `Service` enum in `services.rs` + `from_str()` match arm
2. Add `*Stats` struct + `::new()` in `stats.rs`
3. Add `ServiceStats::NewService(NewStats)` variant
4. Add `parse_newservice()` function in `parse.rs` + dispatch in `parse_service()`
5. Add `print_newservice()` in `output.rs` + match arm in `print_report()`
6. Add detection patterns to `detect_service()` in `main.rs`

## Rayon (if ever needed)

```toml
# Cargo.toml
rayon = "1"
```

Requires reading into memory + `Stats: Send` + `merge_stats()`. Significant refactor — only if single-threaded is actually the bottleneck.
