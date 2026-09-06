# RS-P0-001A Specification Audit and Decision Freeze

**Base document:** `docs/RS-P0-001-specification.md`  
**Scope:** Design audit only; no implementation activity

## Issues Found and Specification Changes

| ID | Issue found | Severity | Specification change made |
|---|---|---|---|
| A1 | Dedicated `--shell` created an unnecessary parsing/platform branch. | Major | Removed it; P0 is direct exec only and users explicitly invoke a shell. |
| A2 | Root zero was terminal even with known live descendants. | Critical | Added deterministic `ROOT_EXITED_WAITING_DESCENDANTS`; complete only after known descendants end. |
| A3 | Root-recursive discovery would fail after descendant reparenting. | Critical | Retain descendant PID/create-time identities and sample them individually after root exit. |
| A4 | Child-crash wording could make child failure appear terminal. | Major | Defined child disappearance/zombie as warning-only unless root lifecycle fails. |
| A5 | No-watch and temporary-metric state cases were underspecified. | Major | Defined applicable channels and seven explicit case outcomes; incomplete evidence cannot stall. |
| A6 | JSONL crash boundary, disk-full, and final-summary failure lacked precise semantics. | Major | Defined line/flush policy, tolerated final partial line, and nonfatal sink failure. |
| A7 | Stream design lacked explicit binary, Unicode, partial-line, and starvation rules. | Major | Defined two fixed-size binary drains, no decoding/line parsing/output retention. |
| A8 | OOM wording implied too much certainty. | Minor | Replaced rough prediction language with bounded `POSSIBLE_OOM_RISK`. |
| A9 | Completion ETA wording left an ambiguous future path. | Major | Froze job ETA to null in P0; disk ETA is separately constrained. |
| A10 | Synthetic matrix did not list prohibited states and failure criteria. | Major | Reworked each scenario with sequence, forbidden states, warnings, outcome, failure condition. |
| A11 | PTY was open rather than a P0 boundary. | Minor | Explicitly excluded PTY and documented TTY limitations. |

## Remaining Consciously Accepted Limitations

- Daemonized, reparented-before-sample, and inaccessible descendants can escape observation.
- psutil commonly cannot provide child exit status, including for zombie observations.
- Root zero with known descendants may keep RunSentry active indefinitely; P0 never kills or times them out.
- Pipe output is not TTY-equivalent; TTY-sensitive programs may change behavior, and RunSentry crash may close pipes.
- A blocked inherited terminal/output destination can throttle forwarding; P0 avoids internal buffering/deadlocks but cannot make that destination writable.
- An abrupt crash can leave one incomplete final JSONL line; prior complete records remain valid.
- Recursive directory watches are portable but potentially expensive and not event-complete.
- Job completion ETA is deliberately absent; disk projections cover only known watched-filesystem growth.
- Memory warnings describe pressure/trends, never deterministic OOM prediction.

## Final Frozen P0 Decisions

1. **Shell mode:** no `--shell`; direct execution only. Users directly invoke shells and own quoting/platform semantics.
2. **Health configuration:** centralized conservative internal constants; no P0 health-tuning option surface.
3. **Root exit with descendants:** root success is not complete while known descendants live. Root failure is immediately failed; descendants are never killed.
4. **PTY:** out of scope. Use two bounded binary stdout/stderr drains, one reader per stream.
5. **Job completion ETA:** always null/unknown. Throughput trend and disk exhaustion ETA are distinct evidence-limited outputs.

## Audit Outcome

Critical issues found: **2**  
Major issues found: **7**  
Minor issues found: **2**

Files modified/created:

- `docs/RS-P0-001-specification.md` — revised
- `docs/RS-P0-001A-audit.md` — created

Confirmation: **zero implementation code was written.**

SPEC_STATUS =
    READY_FOR_IMPLEMENTATION

