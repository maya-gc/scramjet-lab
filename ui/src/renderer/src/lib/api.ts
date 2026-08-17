import type {
  CaseSummary,
  DescribeResponse,
  GeometryPayload,
  Groups,
  JobInfo,
  Metrics,
  OutputFile,
  Report,
  RpcEnvelope,
  RunSummary,
  Stations,
  ValidateResponse
} from './types'

const bridge = window.scramjet

export class BackendError extends Error {
  constructor(
    public readonly code: string,
    message: string
  ) {
    super(message)
    this.name = 'BackendError'
  }
}

async function rpc<T>(method: string, params?: Record<string, unknown>): Promise<T> {
  const envelope = (await bridge.invoke(method, params)) as RpcEnvelope<T>
  if (!envelope?.ok) {
    const err = envelope?.error ?? { type: 'Error', message: 'unknown backend error' }
    throw new BackendError(err.type, err.message)
  }
  return envelope.result as T
}

export const api = {
  health: () => rpc<{ ok: boolean; python: string }>('health'),
  listCases: () => rpc<CaseSummary[]>('list_cases'),
  describe: (casePath: string) => rpc<DescribeResponse>('describe_case', { case_path: casePath }),
  validate: (casePath: string, overrides: Record<string, unknown>) =>
    rpc<ValidateResponse>('validate', { case_path: casePath, overrides }),
  listRuns: (runsDir = 'runs', limit = 30) =>
    rpc<RunSummary[]>('list_runs', { runs_dir: runsDir, limit }),
  scoreMetrics: (metrics: Metrics) => rpc<number>('score_metrics', { metrics }),

  runCase: (params: {
    case_path: string
    workdir: string
    steps?: string[]
    overrides?: Record<string, unknown>
    solver_exe?: string
  }) => rpc<{ job_id: string }>('run_case', params),
  jobStatus: (jobId: string) => rpc<JobInfo>('job_status', { job_id: jobId }),
  jobCancel: (jobId: string) => rpc<boolean>('job_cancel', { job_id: jobId }),
  jobList: () => rpc<JobInfo[]>('job_list'),

  loadReport: (workdir: string) => rpc<Report | null>('load_report', { workdir }),
  loadGeometry: (workdir: string) => rpc<GeometryPayload | null>('load_geometry', { workdir }),
  loadStations: (workdir: string) => rpc<Stations | null>('load_stations', { workdir }),
  loadMetrics: (workdir: string) => rpc<Metrics | null>('load_metrics', { workdir }),
  loadOutputs: (workdir: string) => rpc<OutputFile[]>('load_outputs', { workdir })
}

/** Overrides dict built from every editable group (backend re-coerces). */
export function overridesFromGroups(groups: Groups): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [group, fields] of Object.entries(groups)) {
    for (const [key, value] of Object.entries(fields)) {
      out[`${group}.${key}`] = value
    }
  }
  return out
}

export function groupFromDescribe(describe: DescribeResponse): Groups {
  return describe.groups
}
