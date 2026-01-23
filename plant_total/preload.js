const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    onUpdateData: (callback) => ipcRenderer.on('update-data', (_event, value) => callback(value))
});
