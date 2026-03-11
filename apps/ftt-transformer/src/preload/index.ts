import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("ftt", {
  selectFiles: () => ipcRenderer.invoke("ftt:select-files"),
  selectFolder: () => ipcRenderer.invoke("ftt:select-folder"),
  convertFiles: (payload: { requestId: string; files: string[] }) =>
    ipcRenderer.invoke("ftt:convert-files", payload),
  onConvertProgress: (handler: (event: unknown, payload: unknown) => void) =>
    ipcRenderer.on("ftt:convert-progress", handler),
  offConvertProgress: (handler: (event: unknown, payload: unknown) => void) =>
    ipcRenderer.removeListener("ftt:convert-progress", handler),
  saveProject: (payload: { project: Record<string, unknown>; targetDir: string; includeUploads: boolean }) =>
    ipcRenderer.invoke("ftt:save-project", payload),
  exportProject: (payload: {
    project: Record<string, unknown>;
    regions: Array<{ pen: string; name: string; dataUrl: string }>;
    targetZip: string;
  }) => ipcRenderer.invoke("ftt:export-project", payload),
});

export {};
