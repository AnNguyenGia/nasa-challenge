const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
  minimizeWindow: () => ipcRenderer.send('window-minimize'),
  maximizeWindow: () => ipcRenderer.send('window-maximize'),
  closeWindow: () => ipcRenderer.send('window-close'),
  toggleFullscreen: () => ipcRenderer.send('window-toggle-fullscreen'),
  saveTelemetryReport: (content, defaultName) => ipcRenderer.invoke('save-telemetry-dialog', { content, defaultName }),
  exportDemoPdf: () => ipcRenderer.invoke('export-demo-pdf'),
  getSystemMetrics: () => ipcRenderer.invoke('get-system-metrics'),
  playSystemAlert: (type) => ipcRenderer.send('play-system-alert', type)
});
