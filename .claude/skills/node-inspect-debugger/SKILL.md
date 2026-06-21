---
name: node-inspect-debugger
description: Debug Node.js with node inspect, --inspect, breakpoints, CDP, heap, and CPU profiles.
metadata: { "openclaw": { "emoji": "🪲", "requires": { "bins": ["node"] } } }
---

# Node Inspect Debugger

Use for Node.js debugging that needs inspector access: hidden locals, async hangs, flaky tests, child processes, startup races, memory growth, or CPU hot paths.

Default to `node inspect` first. Use Chrome DevTools Protocol only when you need scripted breakpoints, automated state capture, heap snapshots, or CPU profiles.

Quick start

- Pause on entry: `node inspect path/to/script.js`
- TypeScript: `node --inspect-brk --import tsx path/to/script.ts`
- Existing PID: `kill -SIGUSR1 <pid>` then `node inspect -p <pid>`
- Inspect target list: `curl -s http://127.0.0.1:9229/json/list | jq`
- OpenClaw CLI path: `node --inspect-brk openclaw.mjs ...`
- OpenClaw test path: `OPENCLAW_VITEST_MAX_WORKERS=1 node --inspect-brk scripts/run-vitest.mjs <file>`

Debugger REPL

- Continue/step: `cont`, `next`, `step`, `out`, `pause`
- Breakpoints: `sb('file.js', 42)`, `sb(42)`, `sb('functionName')`, `breakpoints`, `cb('file.js', 42)`
- Inspect: `bt`, `list(8)`, `watch('expr')`, `exec expr`
- Current scope: `repl`, then evaluate locals directly; `Ctrl+C` exits repl mode.
- Exit safely: `cont` before quitting if the process should continue; otherwise `kill`.

OpenClaw tips

- Prefer `127.0.0.1` inspector binds. Do not expose `--inspect=0.0.0.0` unless the network is isolated.
- For Vitest, debug one file with one worker. Avoid worker pools while stepping.
- For TS source breakpoints, use `--enable-source-maps` when useful; `node inspect` can still show emitted paths.
- For child processes, `NODE_OPTIONS=--inspect-brk` can propagate the inspector, but each child needs its own port.
- For long-lived gateway or dev processes, attach by PID after confirming the target with `/json/list`.

Programmatic CDP

Install tooling outside the repo unless the project already depends on it:

```bash
mkdir -p /tmp/cdp-tools
npm --prefix /tmp/cdp-tools i chrome-remote-interface
NODE_PATH=/tmp/cdp-tools/node_modules node /tmp/cdp-debug.cjs
```

Minimal driver:

```js
const CDP = require("chrome-remote-interface");

(async () => {
  const client = await CDP({ port: 9229 });
  const { Debugger, Runtime } = client;

  Debugger.paused(async ({ callFrames, reason }) => {
    const top = callFrames[0];
    console.log("paused", reason, top.url, top.location.lineNumber + 1);
    const { result } = await Debugger.evaluateOnCallFrame({
      callFrameId: top.callFrameId,
      expression: "JSON.stringify({ pid: process.pid })",
    });
    console.log(result.value ?? result.description);
    await Debugger.resume();
  });

  await Runtime.enable();
  await Debugger.enable();
  await Debugger.setBreakpointByUrl({ urlRegex: ".*target\\.js$", lineNumber: 41 });
  await Runtime.runIfWaitingForDebugger();
})();
```

Profiles

- CPU: enable `Profiler`, `start`, wait, `stop`, write `/tmp/profile.cpuprofile`, open in Chrome DevTools.
- Heap: enable `HeapProfiler`, collect `addHeapSnapshotChunk`, call `takeHeapSnapshot`, write `/tmp/heap.heapsnapshot`.

Pitfalls

- `--inspect` does not pause; use `--inspect-brk` when setup must happen before code runs.
- Default port is `9229`; use `--inspect=0` or a unique port for parallel targets.
- If a breakpoint misses, confirm file path, source map behavior, and whether execution already passed the line.
- If the process appears frozen after detaching, it may still be paused in the debugger.


## Parallel Fix (并行修复)

当任务涉及多个独立修改时，**不要逐个串行执行**。
调用 `submit_fix_manifest` 工具，由 ParallelFixEngine 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "<skill_name>": {"verdict": "Improve", "reason": "<描述>", "path": "<文件路径>"}
      }
    },
    "strategy": "auto",
    "filter_actionable": true
  }
}
```

- 引擎自动处理分片、冲突预测、并行调度
- 等待返回结果后，检查 conflicts 列表
