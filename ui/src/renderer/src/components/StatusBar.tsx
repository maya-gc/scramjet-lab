import { Server, FolderOpen } from 'lucide-react'
import { useAppStore } from '../stores/app'
import { useSimStore } from '../stores/sim'
import { Badge } from './ui/Badge'
import { elapsed } from '../lib/format'

export function StatusBar(): React.JSX.Element {
  const backend = useAppStore((s) => s.backend)
  const error = useAppStore((s) => s.error)
  const job = useSimStore((s) => s.job)
  const workdir = useSimStore((s) => s.workdir)
  const errorMsg = useSimStore((s) => s.error)
  const pastRuns = useSimStore((s) => s.pastRuns)

  const running = job?.status === 'running'
  const doneRuns = pastRuns.filter((r) => r.has_report).length

  return (
    <footer className="statusbar">
      <div className="statusbar-left">
        {backend?.state === 'online' ? (
          <Badge tone="success" dot>
            backend online
          </Badge>
        ) : (
          <Badge tone={backend?.state === 'connecting' ? 'warning' : 'danger'} dot>
            {backend?.state === 'connecting' ? 'connecting' : 'offline'}
          </Badge>
        )}
        {backend?.python && (
          <span className="statusbar-item">
            <Server size={12} />
            python {backend.python}
          </span>
        )}
        {backend?.repo && (
          <span className="statusbar-item statusbar-repo" title={backend.repo}>
            <FolderOpen size={12} />
            {backend.repo}
          </span>
        )}
      </div>

      <div className="statusbar-right">
        {running && (
          <span className="statusbar-item statusbar-running">
            <span className="statusbar-pulse" />
            {job.stage === 'solver'
              ? job.message || 'solving'
              : `${job.stage} ${job.message ? `· ${job.message}` : ''}`}
            {job.elapsed ? ` · ${elapsed(job.elapsed)}` : ''}
          </span>
        )}
        {errorMsg && (
          <span className="statusbar-error" title={errorMsg}>
            {errorMsg.slice(0, 90)}
          </span>
        )}
        {!running && error === null && backend?.state === 'online' && (
          <>
            {workdir && <span className="statusbar-item">{workdir}</span>}
            <span className="statusbar-item">{doneRuns} completed runs in session</span>
          </>
        )}
      </div>
    </footer>
  )
}