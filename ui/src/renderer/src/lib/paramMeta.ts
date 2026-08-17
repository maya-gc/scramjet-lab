import type { GroupKey } from './types'

export interface ParamMeta {
  key: string
  label: string
  group: GroupKey
  kind: 'number' | 'toggle'
  unit?: string
  /** SI -> display multiplier (e.g. 1000 for mm, 0.001 for kPa). */
  scale: number
  decimals: number
  step: number
  /** Fixed display-unit range for the slider when supplied. */
  range?: [number, number]
  /** Slider range as multiples of the case default when no fixed range. */
  rangeFactor?: [number, number]
  hint?: string
}

export interface GroupMeta {
  key: GroupKey
  title: string
  blurb: string
  params: ParamMeta[]
}

function num(
  group: GroupKey,
  key: string,
  label: string,
  opts: Partial<ParamMeta> = {}
): ParamMeta {
  return {
    key,
    label,
    group,
    kind: 'number',
    scale: 1,
    decimals: 3,
    step: null as unknown as number,
    ...opts
  } as ParamMeta
}

function togg(group: GroupKey, key: string, label: string): ParamMeta {
  return { key, label, group, kind: 'toggle', scale: 1, decimals: 0, step: 1 }
}

export const PARAM_GROUPS: GroupMeta[] = [
  {
    key: 'flow',
    title: 'Freestream',
    blurb: 'Inlet conditions at the capture plane',
    params: [
      num('flow', 'mach', 'Mach number', { decimals: 2, step: 0.1, rangeFactor: [0.6, 1.5], range: [1.05, 12] }),
      num('flow', 'p_inf', 'Static pressure', { unit: 'kPa', scale: 0.001, decimals: 1, step: 50, range: [0.1, 100] }),
      num('flow', 't_inf', 'Static temperature', { unit: 'K', decimals: 1, step: 10, rangeFactor: [0.5, 2] }),
      num('flow', 'gamma', 'Specific heat ratio', { decimals: 3, step: 0.01, range: [1.05, 1.67] }),
      num('flow', 'R', 'Gas constant', { unit: 'J/kg·K', decimals: 1, step: 5, range: [200, 400] }),
      num('flow', 'turbulence_intensity', 'Turbulence intensity', { decimals: 4, step: 0.0002, rangeFactor: [0.5, 4] }),
      num('flow', 'turbulence_length_scale', 'Turb. length scale', { unit: 'mm', scale: 1000, decimals: 3, step: 0.0005, rangeFactor: [0.5, 4] })
    ]
  },
  {
    key: 'geometry',
    title: 'Engine geometry',
    blurb: '2D channel profile, extruded across the span',
    params: [
      num('geometry', 'capture_height', 'Capture height', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [3, 30] }),
      num('geometry', 'span', 'Span / depth', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [2, 50] }),
      num('geometry', 'contraction_ratio', 'Contraction ratio', { decimals: 2, step: 0.05, range: [1.05, 4] }),
      num('geometry', 'intake_angle_deg', 'Intake ramp angle', { unit: 'deg', decimals: 1, step: 0.5, range: [1.5, 16] }),
      num('geometry', 'isolator_length', 'Isolator length', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [5, 120] }),
      num('geometry', 'combustor_length', 'Combustor length', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [5, 80] }),
      num('geometry', 'combustor_divergence_deg', 'Combustor divergence', { unit: 'deg', decimals: 1, step: 0.1, range: [0, 5] }),
      num('geometry', 'nozzle_length', 'Nozzle length', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [10, 150] }),
      num('geometry', 'nozzle_expansion_ratio', 'Nozzle expansion ratio', { decimals: 2, step: 0.05, range: [1, 5] }),
      togg('geometry', 'strut_enabled', 'Strut injector'),
      num('geometry', 'strut_length', 'Strut length', { unit: 'cm', scale: 100, decimals: 1, step: 1, range: [1, 40] }),
      num('geometry', 'strut_height', 'Strut height', { unit: 'mm', scale: 1000, decimals: 1, step: 1, range: [2, 40] }),
      num('geometry', 'strut_pos_frac', 'Strut position (frac.)', { decimals: 2, step: 0.01, range: [0.05, 0.95] })
    ]
  },
  {
    key: 'mesh',
    title: 'Mesh',
    blurb: 'Target cell size per region',
    params: [
      num('mesh', 'h_far', 'Farfield', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, rangeFactor: [0.5, 3] }),
      num('mesh', 'h_inlet', 'Inlet', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, rangeFactor: [0.5, 3] }),
      num('mesh', 'h_isolator', 'Isolator', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, rangeFactor: [0.5, 3] }),
      num('mesh', 'h_combustor', 'Combustor', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, rangeFactor: [0.5, 3] }),
      num('mesh', 'h_nozzle', 'Nozzle', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, rangeFactor: [0.5, 3] }),
      num('mesh', 'h_wall_n', 'Wall normal', { unit: 'µm', scale: 1e6, decimals: 0, step: 1, rangeFactor: [0.3, 5] }),
      num('mesh', 'bl_thickness', 'B.L. thickness', { unit: 'mm', scale: 1000, decimals: 2, step: 0.25, range: [0, 20] }),
      num('mesh', 'bl_ratio', 'B.L. stretch ratio', { decimals: 2, step: 0.01, range: [1.01, 1.4] })
    ]
  },
  {
    key: 'solver',
    title: 'Solver',
    blurb: 'SU2 numerical settings',
    params: [
      num('solver', 'cfl', 'CFL number', { decimals: 2, step: 0.05, range: [0.1, 5] }),
      num('solver', 'max_iter', 'Max iterations', { decimals: 0, step: 250, range: [200, 20000] }),
      togg('solver', 'euler_init', 'Euler warm start'),
      num('solver', 'residual_target', 'Residual target', { decimals: 2, step: 0.5, range: [1e-12, 1e-2], unit: 'log₁₀' }),
      num('solver', 'linear_solver_error', 'Lin. solver error', { decimals: 5, step: 0.0005, range: [1e-6, 1e-2] })
    ]
  }
]

const BY_GROUP: Record<string, Map<string, ParamMeta>> = {}
for (const g of PARAM_GROUPS) {
  const m = new Map<string, ParamMeta>()
  for (const p of g.params) m.set(p.key, p)
  BY_GROUP[g.key] = m
}

export function findMeta(group: string, key: string): ParamMeta | undefined {
  return BY_GROUP[group]?.get(key)
}

export function metaForParam(group: string, key: string): ParamMeta {
  const m = findMeta(group, key)
  if (!m) {
    return {
      key,
      label: key.replace(/_/g, ' '),
      group: group as GroupKey,
      kind: 'number',
      scale: 1,
      decimals: 4,
      step: 0.1,
      rangeFactor: [0.5, 2]
    }
  }
  return m
}

/** SI value -> display-unit value. */
export function toDisplay(raw: number | boolean, meta: ParamMeta): number {
  if (typeof raw === 'boolean') return raw ? 1 : 0
  return raw * meta.scale
}

/** Display-unit value -> SI value. */
export function fromDisplay(disp: number, meta: ParamMeta): number {
  return disp / meta.scale
}