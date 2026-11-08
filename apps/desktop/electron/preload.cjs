const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('edge', {
  request: (method, route, body) => ipcRenderer.invoke('edge:request', method, route, body)
});
