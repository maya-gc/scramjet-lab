import { ipcMain } from 'electron'
import type { BackendProcess } from './backend'

const METHODS = new Set([
  'health', 'describe_case', 'list_cases', 'validate',
  'load_report', 'load_geometry', 'load_stations', 'load_metrics',
  'load_outputs', 'list_runs', 'score_metrics',
  'job_status', 'job_list', 'job_cancel',
  'run_case', 'render_schematic', 'render_engine3d', 'render_vehicle',
  'render_ramjet3d', 'render_crosssection', 'render_anim3d', 'render_all'
])

export function registerIpc(backend: BackendProcess): void {
  ipcMain.handle('scramjet:info', () => backend.getInfo())

  ipcMain.handle('scramjet:invoke', async (_event, payload) => {
    const method = payload?.method
    const params = payload?.params ?? {}
    if (typeof method !== 'string' || !METHODS.has(method)) {
      return { ok: false, error: { type: 'UnknownMethod', message: String(method) } }
    }
    try {
      return await backend.invoke(method, params)
    } catch (err) {
      return {
        ok: false,
        error: {
          type: 'TransportError',
          message: err instanceof Error ? err.message : String(err)
        }
      }
    }
  })
}
