# RunSentry Share Copy

## A. GitHub / Hacker News style

Title:

Show HN: RunSentry — a local observer for long-running commands

Copy:

RunSentry is a small Python CLI that wraps a command after `--`, tees stdout/stderr,
records local process/resource and watched-path facts, and writes JSONL telemetry plus
`summary.json`. It is intentionally conservative: no SaaS, no auto-kill, no recovery,
no ETA, no OOM/disk prediction.

- Local-only telemetry; no network upload.
- stdout/stderr content is not stored, only activity counters.
- Health states are conservative: `STARTING`, `HEALTHY`, `QUIET`, `SUSPECTED_STALL`,
  `FAILED`, `COMPLETE`.

Feedback wanted: does install work, does the health state match your judgment, and is
`summary.json` useful after a real long-running job?

## B. Reddit / developer community style

I built a small public-alpha tool called RunSentry for a practical annoyance: you start
a long Python job or shell command, it goes quiet, and you keep wondering whether it is
fine, stuck, or about to fail.

RunSentry wraps a command after `--`, keeps stdout/stderr visible, records local facts
about output activity, process/resource usage, watched file or directory growth, and
writes `.runsentry/runs/<run_id>/summary.json`.

It is deliberately not a supervisor or orchestration framework. It will not kill,
restart, recover, upload telemetry, predict OOM, predict disk exhaustion, or invent a
job ETA.

If you run long local scripts, I would value feedback on install friction, whether the
health state matches your own judgment, and whether the summary file is actually useful.

## C. LinkedIn style

I released the first public alpha of RunSentry, a lightweight local observer for
long-running commands and Python jobs.

The goal is simple: wrap a command, keep output visible, record local telemetry, and
provide conservative health states without changing the workload. RunSentry stores
stdout/stderr activity counters rather than output content, writes local JSONL telemetry
and `summary.json`, and does not upload data.

This alpha is intentionally scoped: no dashboard, no SaaS, no automatic recovery, no
OOM/disk prediction, and no job ETA. I am looking for early feedback from developers
who run long local jobs and want better evidence about whether they are still active.

## D. Direct message to developer

I released a small public alpha called RunSentry:
https://github.com/zhangchao102282-dot/runsentry

It wraps long-running local commands, keeps stdout/stderr visible, records local
telemetry, and writes a `summary.json` with conservative health states.

If you have one safe long-running Python/shell job, could you try it and tell me:
did install work, did the health state match your judgment, and was the summary useful?
No money ask; I am validating whether this is useful outside my own workflow.

## E. Chinese version

我发布了 RunSentry 的第一个 public alpha：
https://github.com/zhangchao102282-dot/runsentry

它解决的是一个很实际的问题：本地跑长时间 Python 脚本、数据处理脚本或 agent 任务时，
程序突然很安静，你不确定它是在正常等待、还在工作、已经卡住，还是已经失败。

RunSentry 会包一层命令：

```bash
runsentry run --name demo -- python3 job.py
```

它会保持 stdout/stderr 正常显示，同时记录本地 telemetry 和 `summary.json`，包括输出
活跃度、进程/资源事实、被 watch 的文件或目录是否增长，以及保守的健康状态。

它不是调度系统，也不是 SaaS，不会自动 kill/restart，不上传 telemetry，不预测 OOM、
磁盘耗尽或任务 ETA。

如果你经常跑长时间本地脚本，欢迎试一下。最有价值的反馈是：安装是否顺利、健康状态
是否符合你的人工判断、`summary.json` 是否真的有用、还缺什么事实信息。

