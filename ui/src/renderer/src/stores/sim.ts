import { create } from 'zustand'
import { api } from '../lib/api'
import type {
  GeometryPayload,
  JobInfo,
  Metrics,
  OutputFile,
  Report,
  RunSummary,
  Stations
} from '../lib/types'
import { useAppStore } from './app'

export type RunMode = 'full' | 'preview'

interface SimState {
  job: JobInfo | null
  running: boolean
  mode: RunMode | null
  workdir: string | null
  startedAt: number | null
  report: Report | null
  geometry: GeometryPayload | null
  stations: Stations | null
  metrics: Metrics | null
  outputs: OutputFile[]
  pastRuns: RunSummary[]
  error: string | null
  _timer: ReturnType<typeof setInterval> | null
  _submitting: boolean
  startRun: (mode: RunMode, overrides: Record<string, unknown>) => Promise<void>
  poll: () => Promise<void>
  cancelRun: () => Promise<void>
  loadResults: (workdir: string) => Promise<void>
  refreshRuns: () => Promise<void>
  clearResults: () => void
}

export const useSimStore = create<SimState>((set, get) => ({
  job: null,
  running: false,
  mode: null,
  workdir: null,
  startedAt: null,
  report: null,
  geometry: null,
  stations: null,
  metrics: null,
  outputs: [],
  pastRuns: [],
  error: null,
  _timer: null,
  _submitting: false,

  startRun: async (mode, overrides) => {
    if (get()._submitting || get().running) return
    set({ _submitting: true, error: null })
    try {
      const caseName = useAppStore.getState().activeCase ?? 'case'
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const workdir = `runs/ui/${ts}_${caseName}`
      const steps =
        mode === 'preview'
          ? ['geometry', 'mesh', 'case']
          : ['geometry', 'mesh', 'case', 'run', 'post', 'metrics']
      const { job_id } = await api.runCase({
        case_path: caseName,
        workdir,
        steps,
        overrides,
        solver_exe: useAppStore.getState().solverExe || undefined
      })
      const job: JobInfo = {
        job_id,
        method: 'run_case',
        status: 'running',
        stage: 'starting',
        message: 'queued',
        progress: 0,
        elapsed: 0,
        error: null
      }
      set({
        job,
        running: true,
        mode,
        workdir,
        startedAt: Date.now(),
        report: null,
        geometry: null,
        stations: null,
        metrics: null,
        outputs: [],
        error: null,
        _submitting: false
      })
      const timer = setInterval(() => void get().poll(), 800)
      set({ _timer: timer })
      void get().poll()
    } catch (err) {
      set({
        _submitting: false,
        error: err instanceof Error ? err.message : String(err)
      })
    }
  },

  poll: async () => {
    const { job } = get()
    if (!job) return
    const stop = (): void => {
      const t = get()._timer
      if (t) clearInterval(t)
    }
    try {
      const info = await api.jobStatus(job.job_id)
      if (info.status === 'done') {
        stop()
        set({ _timer: null, job: info, running: false })
        const wd = get().workdir
        if (wd) await get().loadResults(wd)
        await get().refreshRuns()
      } else if (info.status === 'error') {
        stop()
        set({
          _timer: null,
          job: info,
          running: false,
          error: info.error?.message ?? 'simulation failed'
        })
      } else if (info.status === 'cancelled') {
        stop()
        set({ _timer: null, job: info, running: false })
      } else {
        set({ job: info })
      }
    } catch (err) {
      stop()
      set({
        _timer: null,
        running: false,
        error: err instanceof Error ? err.message : String(err)
      })
    }
  },

  cancelRun: async () => {
    const { job, _timer } = get()
    if (job && (job.status === 'running' || job.status === 'queued')) {
      try {
        await api.jobCancel(job.job_id)
      } catch {
        /* best effort */
      }
    }
    if (_timer) clearInterval(_timer)
    set({ _timer: null, running: false })
  },

  loadResults: async (workdir) => {
    try {
      const [report, geometry, stations, metrics, outputs] = await Promise.all([
        api.loadReport(workdir),
        api.loadGeometry(workdir),
        api.loadStations(workdir),
        api.loadMetrics(workdir),
        api.loadOutputs(workdir)
      ])
      set({
        report,
        geometry,
        stations,
        metrics,
        outputs: outputs ?? []
      })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  refreshRuns: async () => {
    try {
      set({ pastRuns: await api.listRuns('runs', 20) })
    } catch {
      /* non-fatal */
    }
  },

  clearResults: () => {
    const t = get()._timer
    if (t) clearInterval(t)
    set({
      job: null,
      running: false,
      mode: null,
      workdir: null,
      startedAt: null,
      report: null,
      geometry: null,
      stations: null,
      metrics: null,
      outputs: [],
      error: null
    })
  }
}))
