const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { pathToFileURL } = require('url');

let mainWindow = null;
let fallbackServer = null;
let fallbackUrl = null;
let backendPoll = null;
const BACKEND_URL = 'http://127.0.0.1:8000';

async function backendReady() {
  try {
    const response = await fetch(BACKEND_URL + '/health', { signal: AbortSignal.timeout(1500) });
    return response.ok;
  } catch { return false; }
}

function ensureServer(onReady) {
  backendReady().then(ready => {
    if (ready) { onReady(BACKEND_URL); return; }
    startFallbackServer(onReady);
    backendPoll = setInterval(async () => {
      if (!await backendReady()) return;
      clearInterval(backendPoll);
      backendPoll = null;
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.loadURL(BACKEND_URL).catch(console.error);
    }, 3000);
  });
}

function startFallbackServer(onReady) {
  if (fallbackServer && fallbackUrl) return onReady(fallbackUrl);
  const distDir = path.join(__dirname, 'dist');
  const mimeTypes = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.bin': 'application/octet-stream',
    '.gz': 'application/gzip'
  };
  const server = http.createServer((req, res) => {
    let reqPath = decodeURIComponent(req.url.split('?')[0]);
    if (reqPath === '/' || reqPath === '') reqPath = '/index.html';
    else if (reqPath.endsWith('/')) reqPath += 'index.html';
    const filePath = path.join(distDir, reqPath.replace(/^\//, ''));
    if (!filePath.startsWith(distDir)) { res.statusCode = 403; return res.end('Forbidden'); }
    fs.stat(filePath, (err, stats) => {
      if (err || !stats.isFile()) { res.statusCode = 404; return res.end('Not Found'); }
      const ext = path.extname(filePath).toLowerCase();
      res.setHeader('Content-Type', mimeTypes[ext] || 'application/octet-stream');
      res.setHeader('Access-Control-Allow-Origin', '*');
      fs.createReadStream(filePath).pipe(res);
    });
  });
  server.on('error', () => {
    onReady(pathToFileURL(path.join(distDir, 'index.html')).toString());
  });
  server.listen(0, '127.0.0.1', () => {
    fallbackServer = server;
    fallbackUrl = `http://127.0.0.1:${server.address().port}`;
    onReady(fallbackUrl);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 980,
    minWidth: 768,
    minHeight: 600,
    backgroundColor: '#0e1114',
    title: 'ASTROHEALTH — Bio-Med Avionics Flight Medical Console',
    autoHideMenuBar: true,
    darkTheme: true,
    show: false, // smooth display on ready-to-show
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true
    }
  });

  ensureServer(url => {
    if (mainWindow) mainWindow.loadURL(url);
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Native Mission Control Menu
  const menuTemplate = [
    {
      label: 'Mission Control',
      submenu: [
        {
          label: 'Đồng bộ lại (Reload)',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow.reload()
        },
        {
          label: 'Toàn màn hình HUD (Fullscreen)',
          accelerator: 'F11',
          click: () => {
            mainWindow.setFullScreen(!mainWindow.isFullScreen());
          }
        },
        { type: 'separator' },
        {
          label: 'Công cụ phát triển (DevTools)',
          accelerator: 'CmdOrCtrl+Shift+I',
          click: () => mainWindow.webContents.toggleDevTools()
        },
        { type: 'separator' },
        {
          label: 'Thoát ứng dụng',
          accelerator: 'CmdOrCtrl+Q',
          click: () => app.quit()
        }
      ]
    },
    {
      label: 'Telemetry',
      submenu: [
        {
          label: 'Chỉ số sinh tồn (Vitals)',
          click: () => mainWindow.webContents.executeJavaScript('window.navigateAstro("vitals")')
        },
        {
          label: 'Trợ lý y khoa AI (Aura-Med)',
          click: () => mainWindow.webContents.executeJavaScript('window.navigateAstro("assistant")')
        },
        {
          label: 'Báo cáo EVA',
          click: () => mainWindow.webContents.executeJavaScript('window.navigateAstro("reports")')
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(menuTemplate);
  Menu.setApplicationMenu(menu);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Handlers
ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-toggle-fullscreen', () => {
  if (mainWindow) {
    mainWindow.setFullScreen(!mainWindow.isFullScreen());
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.close();
});

// Save Telemetry Dialog (Native File Saver)
ipcMain.handle('save-telemetry-dialog', async (event, { content, defaultName }) => {
  if (!mainWindow) return { success: false };
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: 'Xuất Báo Cáo Telemetry Y Khoa Quỹ Đạo',
    defaultPath: defaultName || `AstroHealth-Telemetry-${new Date().toISOString().slice(0, 10)}.csv`,
    filters: [
      { name: 'CSV File (*.csv)', extensions: ['csv'] },
      { name: 'All Files (*.*)', extensions: ['*'] }
    ]
  });

  if (canceled || !filePath) {
    return { success: false, canceled: true };
  }

  try {
    fs.writeFileSync(filePath, content, 'utf8');
    return { success: true, filePath };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('export-demo-pdf', async () => {
  if (!mainWindow) return { success: false, error: 'Window unavailable' };
  try {
    const pdf = await mainWindow.webContents.printToPDF({ printBackground: true, pageSize: 'A4', preferCSSPageSize: true });
    const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
      title: 'Lưu báo cáo AstroHealth mô phỏng',
      defaultPath: `AstroHealth-SIMULATED-${new Date().toISOString().slice(0, 10)}.pdf`,
      filters: [{ name: 'PDF File (*.pdf)', extensions: ['pdf'] }]
    });
    if (canceled || !filePath) return { success: false, canceled: true };
    fs.writeFileSync(filePath, pdf);
    return { success: true, filePath };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// Real Machine System Telemetry
ipcMain.handle('get-system-metrics', async () => {
  return {
    cpus: os.cpus().length,
    freeMem: Math.round(os.freemem() / 1024 / 1024),
    totalMem: Math.round(os.totalmem() / 1024 / 1024),
    uptime: Math.round(os.uptime()),
    platform: os.platform(),
    hostname: os.hostname()
  };
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendPoll) clearInterval(backendPoll);
  if (fallbackServer) fallbackServer.close();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
