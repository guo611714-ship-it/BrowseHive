const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { startAgentTeam, stopAgentTeam } = require('./agent-team.cjs');
const { createTray } = require('./tray.cjs');

let mainWindow = null;

const isDev = !app.isPackaged;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Agent Team Dashboard',
    icon: path.join(__dirname, '../assets/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    // 打包后：electron/main.cjs -> ../dist/index.html
    const indexPath = path.join(__dirname, '..', 'dist', 'index.html');
    console.log('Loading:', indexPath);
    mainWindow.loadFile(indexPath);
  }

  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  createTray(mainWindow);
}

app.whenReady().then(async () => {
  try {
    await startAgentTeam();
  } catch (err) {
    console.error('Agent Team startup failed:', err);
  }
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopAgentTeam();
});

ipcMain.on('app-quit', () => {
  app.isQuitting = true;
  app.quit();
});

ipcMain.handle('app-version', () => app.getVersion());
