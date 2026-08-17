import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'

export interface BackendInfoPayload {
  state: 'connecting' | 'online' | 'offline'
  url: string | null
  repo: string | null
  python: string | null
  accel: { backend: string; gpu: boolean } | null
  error: string | null
}

const api = {
  info: (): Promise<BackendInfoPayload> => ipcRenderer.invoke('scramjet:info'),
  invoke: (method: string, params?: Record<string, unknown>): Promise<unknown> =>
    ipcRenderer.invoke('scramjet:invoke', { method, params }),
  onBackendStatus: (cb: (info: BackendInfoPayload) => void): (() => void) => {
    const listener = (_e: IpcRendererEvent, info: BackendInfoPayload): void => cb(info)
    ipcRenderer.on('scramjet:backend-status', listener)
    return () => ipcRenderer.removeListener('scramjet:backend-status', listener)
  }
}

contextBridge.exposeInMainWorld('scramjet', api)

export type ScramjetApi = typeof api