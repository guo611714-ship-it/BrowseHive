const { spawn } = require('child_process');
const { app, dialog } = require('electron');
const path = require('path');

let agentTeamProcess = null;

const PYTHON_PATH = 'C:/Users/lenovo/AppData/Local/Programs/Python/Python311/python.exe';

function getWorkspaceRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath)
    : path.join(__dirname, '../..');
}

async function startAgentTeam() {
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
    const workspaceRoot = getWorkspaceRoot();
    const scriptPath = path.join(workspaceRoot, 'run_sse.py');

    agentTeamProcess = spawn(PYTHON_PATH, [scriptPath], {
      cwd: workspaceRoot,
      stdio: 'ignore',
      detached: true,
    });

    agentTeamProcess.on('error', (err) => {
      console.error('Failed to start Agent Team:', err);
      dialog.showErrorBox(
        'Agent Team 启动失败',
        '无法启动 Agent Team 后端。\n\n请确认 Python 已安装：' + PYTHON_PATH + '\n\n错误：' + err.message
      );
      reject(err);
    });

    agentTeamProcess.on('exit', (code) => {
      console.log('Agent Team exited with code ' + code);
      agentTeamProcess = null;
    });

    setTimeout(resolve, 5000);
  });
}

function stopAgentTeam() {
  if (agentTeamProcess) {
    agentTeamProcess.kill();
    agentTeamProcess = null;
    console.log('Agent Team stopped');
  }
}

module.exports = { startAgentTeam, stopAgentTeam };
