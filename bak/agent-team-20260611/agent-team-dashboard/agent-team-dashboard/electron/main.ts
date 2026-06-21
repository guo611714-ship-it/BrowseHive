import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'path';
import { startAgentTeam, stopAgentTeam } from './agent-team.js';
import { createTray } from './tray.js';

let mainWindow: BrowserWindow | null = null;

const isDev = !app.isPackaged;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Agent Team Dashboard',
    icon: path.join(__dirname, '../assets/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('close', (e) => {
    if (!(app as any).isQuitting) {
      e.preventDefault();
      mainWindow?.hide();
    }
  });

  createTray(mainWindow);
}

app.whenReady().then(async () => {
  await startAgentTeam();
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  (app as any).isQuitting = true;
  stopAgentTeam();
});

ipcMain.on('app-quit', () => {
  (app as any).isQuitting = true;
  app.quit();
});

ipcMain.handle('app-version', () => app.getVersion());
