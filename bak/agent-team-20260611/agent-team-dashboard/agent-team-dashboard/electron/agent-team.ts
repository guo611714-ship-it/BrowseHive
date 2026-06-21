import { ChildProcess, spawn } from 'child_process';
import { dialog } from 'electron';
import path from 'path';

let agentTeamProcess: ChildProcess | null = null;

const PYTHON_PATH = 'C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe';
const WORKSPACE_ROOT = path.join(__dirname, '../..');

export async function startAgentTeam(): Promise<void> {
  try {
    const res = await fetch('http://127.0.0.1:8772/api/health');
    if (res.ok) {
      console.log('Agent Team already running');
      return;
    }
  } catch {
    // 未运行，继续启动
  }

  return new Promise((resolve, reject) => {
    const scriptPath = path.join(WORKSPACE_ROOT, 'run_sse.py');

    agentTeamProcess = spawn(PYTHON_PATH, [scriptPath], {
      cwd: WORKSPACE_ROOT,
      stdio: 'ignore',
      detached: true,
    });

    agentTeamProcess.on('error', (err) => {
      console.error('Failed to start Agent Team:', err);
      dialog.showErrorBox(
        'Agent Team 启动失败',
        `无法启动 Agent Team 后端。\n\n请确认 Python 已安装：${PYTHON_PATH}\n\n错误：${err.message}`
      );
      reject(err);
    });

    agentTeamProcess.on('exit', (code) => {
      console.log(`Agent Team exited with code ${code}`);
      agentTeamProcess = null;
    });

    setTimeout(resolve, 5000);
  });
}

export function stopAgentTeam(): void {
  if (agentTeamProcess) {
    agentTeamProcess.kill();
    agentTeamProcess = null;
    console.log('Agent Team stopped');
  }
}
