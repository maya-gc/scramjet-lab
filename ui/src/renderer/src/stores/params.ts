import { create } from 'zustand'
import { api, overridesFromGroups } from '../lib/api'
import type { DescribeResponse, FlowDerived, GroupKey, Groups } from '../lib/types'

export interface ValidationState {
  valid: boolean
  errors: string[]
}

interface ParamsState {
  caseName: string
  groups: Groups | null
  defaults: Groups | null
  flowDerived: FlowDerived | null
  validation: ValidationState | null
  validating: boolean
  dirty: boolean
  setDescribe: (d: DescribeResponse) => void
  setParam: (group: GroupKey, key: string, value: number | boolean) => void
  validateNow: () => Promise<ValidationState | null>
  reset: () => void
  overrides: () => Record<string, unknown>
  isDefault: () => boolean
}

export const useParamsStore = create<ParamsState>((set, get) => ({
  caseName: '',
  groups: null,
  defaults: null,
  flowDerived: null,
  validation: null,
  validating: false,
  dirty: false,

  setDescribe: (d) => {
    set({
      caseName: d.case.name,
      groups: structuredClone(d.groups),
      defaults: structuredClone(d.groups),
      flowDerived: d.flow_derived,
      validation: null,
      dirty: false
    })
  },

  setParam: (group, key, value) => {
    const groups = get().groups
    if (!groups) return
    const next: Groups = structuredClone(groups)
    next[group][key] = value
    set({ groups: next, dirty: true })
  },

  validateNow: async () => {
    const { caseName, groups } = get()
    if (!caseName || !groups) return null
    set({ validating: true })
    try {
      const res = await api.validate(caseName, overridesFromGroups(groups))
      const state: ValidationState = { valid: res.valid, errors: res.errors }
      set({
        validation: state,
        groups: res.groups ?? groups,
        flowDerived: res.flow_derived ?? get().flowDerived,
        validating: false
      })
      return state
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      set({
        validating: false,
        validation: { valid: false, errors: [message] }
      })
      return { valid: false, errors: [message] }
    }
  },

  reset: () => {
    const defaults = get().defaults
    if (!defaults) return
    set({ groups: structuredClone(defaults), dirty: false, validation: null })
  },

  overrides: () => {
    const groups = get().groups
    return groups ? overridesFromGroups(groups) : {}
  },

  isDefault: () => {
    const { groups, defaults } = get()
    if (!groups || !defaults) return true
    return JSON.stringify(groups) === JSON.stringify(defaults)
  }
}))