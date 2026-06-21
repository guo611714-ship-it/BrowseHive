/**
 * MCP 全量 Streamable HTTP 启动器
 *
 * 将所有 MCP 服务器从 stdio 转为 Streamable HTTP 共享模式。
 * 端口分配:
 *   8090 - ai-chat (Python)
 *   8091 - codegraph
 *   8092 - context7
 *   8093 - github
 *   8094 - chrome-devtools
 *
 * 用法: node start-all-mcp-http.js
 */

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const WORKSPACE = path.resolve(__dirname, "..");
const CODEGRAPH_CMD = "C:/Users/lenovo/AppData/Roaming/npm/codegraph.cmd";
const PYTHON_CMD = "C:/Users/lenovo/AppData/Local/Programs/Python/Python311/python.exe";

const SERVERS = [
  {
    name: "ai-chat",
    port: 8090,
    type: "python",
    cmd: PYTHON_CMD,
    args: [path.join(__dirname, "start-ai-chat-http.py")],
  },
  {
    name: "codegraph",
    port: 8091,
    type: "env-http",
    cmd: "node",
    args: [path.join(__dirname, "codegraph-src", "dist", "bin", "codegraph.js"), "serve", "--mcp"],
    env: { CODEGRAPH_TRANSPORT: "http", CODEGRAPH_HTTP_PORT: "8091", CODEGRAPH_NO_DAEMON: "1" },
  },
  {
    name: "context7",
    port: 8092,
    type: "native-http",
    cmd: "node",
    args: [path.join(__dirname, "context7-mcp", "dist", "index.js"), "--transport", "http", "--port", "8092"],
  },
  {
    name: "github",
    port: 8093,
    type: "native-http",
    cmd: path.join(__dirname, "github-mcp-server.exe"),
    args: ["http", "--port", "8093"],
    env: { GITHUB_PERSONAL_ACCESS_TOKEN: process.env.GITHUB_PERSONAL_ACCESS_TOKEN || "" },
  },
  {
    name: "chrome-devtools",
    port: 8094,
    type: "env-http",
    cmd: "node",
    args: [path.join(__dirname, "chrome-devtools-mcp", "build", "src", "bin", "chrome-devtools-mcp.js")],
    env: { MCP_TRANSPORT: "http", MCP_PORT: "8094" },
  },
];

const procs = [];

function startServer(srv) {
  let proc;
  if (srv.type === "python") {
    proc = spawn(srv.cmd, srv.args, {
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
      shell: false,
      windowsHide: true,
      cwd: __dirname,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1", ...(srv.env || {}) },
    });
  } else if (srv.type === "native-http") {
    // Native HTTP server (e.g. context7 --transport http)
    proc = spawn(srv.cmd, srv.args, {
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
      shell: false,
      windowsHide: true,
      cwd: WORKSPACE,
      env: srv.env ? { ...process.env, ...srv.env } : process.env,
    });
  } else if (srv.type === "env-http") {
    // HTTP server configured via env vars (e.g. chrome-devtools MCP_TRANSPORT=http)
    proc = spawn(srv.cmd, srv.args, {
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
      shell: false,
      windowsHide: true,
      cwd: WORKSPACE,
      env: { ...process.env, ...srv.env },
    });
  } else {
    throw new Error(`Unknown server type: ${srv.type}`);
  }

  proc.stdout.on("data", (d) => console.log(`[${srv.name}] ${d.toString().trim()}`));
  proc.stderr.on("data", (d) => console.log(`[${srv.name}] ${d.toString().trim()}`));
  proc.on("exit", (code) => console.log(`[${srv.name}] exited with code ${code}`));

  proc.stdout.unref();
  proc.stderr.unref();
  procs.push({ name: srv.name, proc });
  return proc;
}

// Write PID file
const pidFile = path.join(__dirname, "scripts", "mcp-http.pid");
fs.writeFileSync(pidFile, String(process.pid));
console.log(`[launcher] PID ${process.pid}, writing to ${pidFile}`);

console.log("[launcher] Starting all MCP servers as Streamable HTTP...\n");

for (const srv of SERVERS) {
  startServer(srv);
}

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n[launcher] Shutting down...");
  for (const { name, proc } of procs) {
    proc.kill();
    console.log(`[${name}] stopped`);
  }
  process.exit(0);
});

process.on("SIGTERM", () => process.emit("SIGINT"));

console.log(`\n[launcher] ${SERVERS.length} servers starting. Press Ctrl+C to stop.`);
