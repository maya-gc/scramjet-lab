export interface CaseInfo {
  name: string
  dimension: number
  domain: string
  description: string
}

export interface FlowDerived {
  mach: number
  p_inf: number
  t_inf: number
  gamma: number
  R: number
  a_inf: number
  v_inf: number
  rho_inf: number
}

export type GroupKey = 'flow' | 'geometry' | 'mesh' | 'solver'

export type ParamValue = number | boolean

export type Groups = Record<GroupKey, Record<string, ParamValue>>

export interface DescribeResponse {
  case: CaseInfo
  groups: Groups
  flow_derived: FlowDerived
  flat: Record<string, unknown>
}

export interface CaseSummary {
  name: string
  file: string
}

export interface ValidateResponse {
  valid: boolean
  errors: string[]
  groups: Groups | null
  flow_derived: FlowDerived | null
}

export interface GeometryDerived {
  H_capture: number
  H_isolator: number
  y_isolator: number
  L_inlet: number
  x_inlet_end: number
  x_isolator_end: number
  x_combustor_end: number
  x_total: number
  H_combustor_exit: number
  H_nozzle_exit: number
  x_strut: number
  L_total: number
  B: number
  A_capture: number
  A_isolator: number
  A_combustor_exit: number
  A_nozzle_exit: number
  [k: string]: number
}

export interface GeometryPayload {
  lower: number[][]
  upper: number[][]
  strut: number[][] | null
  derived: GeometryDerived
}

export type StationGroupKeys =
  | 'capture'
  | 'isolator_in'
  | 'isolator_out'
  | 'combustor_in'
  | 'combustor_out'
  | 'nozzle_exit'

export interface StationData {
  x: number
  mass_flow: number
  p_massavg: number
  T_massavg: number
  M_massavg: number
  p0_massavg: number
  Vx_massavg: number
  height: number
  area: number
  n_cells: number
}

export type Stations = Record<StationGroupKeys, StationData | null>

export interface Metrics {
  valid: boolean
  mass_capture_per_m: number
  continuity_error: number
  pressure_recovery: number
  static_pressure_rise: number
  net_axial_force_on_fluid: number
  thrust_proxy: number
  specific_thrust: number
  thrust_normalized: number
  nozzle_momentum_eff: number
  mixing_uniformity: number
  M_combustor_out: number
  sep_fraction: number
  separated: boolean
  sep_xmin: number
  sep_xmax: number
  M_isolator_out: number
  operating_margin: number
  unstart_risk: number
  M_exit: number
  p_exit: number
  score: number
  [k: string]: unknown
}

export interface Report {
  case: string
  workdir: string
  metrics?: Metrics
  geometry_summary?: unknown
  mesh?: unknown
  run?: unknown
  post?: unknown
  [k: string]: unknown
}

export interface RunSummary {
  workdir: string
  case: string
  has_report: boolean
  metrics?: Partial<Metrics>
}

export type JobStatusName =
  | 'queued'
  | 'running'
  | 'done'
  | 'error'
  | 'cancelled'

export interface JobInfo {
  job_id: string
  method: string
  status: JobStatusName
  stage: string
  message: string
  progress: number | null
  elapsed: number
  error: { type: string; message: string } | null
}

export interface RpcEnvelope<T = unknown> {
  ok: boolean
  result?: T
  error?: { type: string; message: string }
}

export interface OutputFile {
  path: string
  size: number
}