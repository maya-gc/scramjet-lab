import { create } from 'zustand'
import { api } from '../lib/api'
import type { BackendInfoPayload } from '../../../preload'
import type { CaseSummary, DescribeResponse } from '../lib/types'
import { useParamsStore } from './params'
import { useSimStore } from './sim'

interface AppState {
  backend: BackendInfoPayload | null
  cases: CaseSummary[]
  activeCase: string | null
  describe: DescribeResponse | null
  solverExe: string
  error: string | null
  setBackend: (info: BackendInfoPayload) => void
  setSolverExe: (exe: string) => void
  init: () => Promise<void>
  selectCase: (name: string) => Promise<void>
  refreshCases: () => Promise<void>
}

const SOLVER_EXE_KEY = 'scramjet.solverExe'

function loadSolverExe(): string {
  try {
    return localStorage.getItem(SOLVER_EXE_KEY) ?? ''
  } catch {
    return ''
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  backend: null,
  cases: [],
  activeCase: null,
  describe: null,
  solverExe: loadSolverExe(),
  error: null,

  setBackend: (info) => set({ backend: info, error: null }),

  setSolverExe: (exe) => {
    try {
      if (exe) localStorage.setItem(SOLVER_EXE_KEY, exe)
      else localStorage.removeItem(SOLVER_EXE_KEY)
    } catch {
      /* storage unavailable */
    }
    set({ solverExe: exe })
  },

  init: async () => {
    try {
      const backend = (await window.scramjet.info()) as BackendInfoPayload
      set({ backend })
      if (backend.state !== 'online') {
        set({ error: backend.error ?? 'backend offline' })
        return
      }
      const cases = await api.listCases()
      set({ cases })
      const first = cases[0]?.name
      if (first && !get().activeCase) {
        await get().selectCase(first)
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  selectCase: async (name) => {
    set({ activeCase: name, error: null })
    try {
      const describe = await api.describe(name)
      set({ describe })
      useParamsStore.getState().setDescribe(describe)
      useSimStore.getState().clearResults()
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  refreshCases: async () => {
    try {
      set({ cases: await api.listCases() })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  }
}))