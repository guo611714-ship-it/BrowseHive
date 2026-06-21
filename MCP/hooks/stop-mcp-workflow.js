#!/usr/bin/env node
'use strict';

/**
 * Stop MCP Workflow
 * 停止整套MCP工作流
 */

const { execSync } = require('child_process');

function log(msg) {
  process.stderr.write(`[mcp-workflow] ${msg}\n`);
}

function killProcessOnPort(port) {
  try {
    const result = execSync(`netstat -ano | findstr :${port} | findstr LISTENING`, {
      encoding: 'utf8', timeout: 3000
    });
    if (result.trim()) {
      const pid = result.trim().split(/\s+/).pop();
      execSync(`taskkill /PID ${pid} /F`, { timeout: 3000 });
      log(`Killed process on port ${port} (PID: ${pid})`);
    }
  } catch {}
}

// ─── 停止服务 ─────────────────────────────────────────────
log('=== Stopping MCP Workflow ===');

// 停止NVIDIA API
killProcessOnPort(8080);
log('NVIDIA API stopped');

// 停止Model Router
killProcessOnPort(8081);
log('Model Router stopped');

// 注意：不关闭浏览器，保持登录状态
log('Browser kept running to preserve login states');

log('=== MCP Workflow Stopped ===');
log('To restart, restart Claude Code or run:');
log('  node C:/Users/lenovo/.claude/hooks/auto-start-mcp-workflow.js');
