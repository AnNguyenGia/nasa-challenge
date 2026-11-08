const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const dev = process.argv.includes('--dev');
const origin = 'http://127.0.0.1:5173';
const entry = pathToFileURL(path.join(__dirname, '../dist/index.html')).href;
const token = process.env.EDGE_API_TOKEN;
if (!app.requestSingleInstanceLock()) app.quit();
let win;
const allowed = new Set(['GET /api/readings', 'GET /api/status', 'POST /api/readings', 'POST /api/agent']);
ipcMain.handle('edge:request', async (event, method, route, body) => {
  const sender = event.senderFrame?.url;
  if (event.sender !== win?.webContents || sender !== (dev ? origin + '/' : entry)) {
    throw new Error('Untrusted sender');
  }
  if (!allowed.has(`${method} ${route}`)) throw new Error('Unsupported route');
  if (!token || token.length < 24) return {ok:false, status:401, error:'Cần EDGE_API_TOKEN khi mở ứng dụng.'};
  const serialized = body == null ? undefined : JSON.stringify(body);
  if (serialized && serialized.length > 10000) throw new Error('Payload too large');
  try {
    const response = await fetch('http://127.0.0.1:8000' + route, {
      method, headers: {'Content-Type':'application/json', Authorization:`Bearer ${token}`},
      body: serialized, signal: AbortSignal.timeout(route === '/api/agent' ? 50000 : 8000)
    });
    const data = await response.json();
    return {ok:response.ok, status:response.status, data};
  } catch {
    return {ok:false, status:0, error:'Edge chưa kết nối. Dữ liệu vẫn được giữ tại máy.'};
  }
});
app.whenReady().then(() => {
  win = new BrowserWindow({width:1240, height:860, minWidth:900, minHeight:650,
    webPreferences: {preload:path.join(__dirname,'preload.cjs'), sandbox:true,
      contextIsolation:true, nodeIntegration:false}});
  win.webContents.setWindowOpenHandler(() => ({action:'deny'}));
  win.webContents.on('will-navigate', (event) => event.preventDefault());
  win.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  if (dev) win.loadURL(origin); else win.loadFile(path.join(__dirname,'../dist/index.html'));
});
app.on('window-all-closed', () => app.quit());
