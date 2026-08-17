import { motion } from 'framer-motion'
import { Check, Square, Box, Grid3X3, FileCog, Play, Send, BarChart3 } from 'lucide-react'
import { useSimStore } from '../stores/sim'
import { Button } from './ui/Button'
import { cls } from '../lib/cls'
import { elapsed } from '../lib/format'

const STAGES = [
  { key: 'geometry', label: 'Geometry', icon: Box },
  { key: 'mesh', label: 'Mesh', icon: Grid3X3 },
  { key: 'case', label: 'Case', icon: FileCog },
  { key: 'solver', label: 'Solver', icon: Play },
  { key: 'post', label: 'Post', icon: Send },
  { key: 'metrics', label: 'Metrics', icon: BarChart3 }
]

export function ProgressOverlay(): React.JSX.Element | null {
  const job = useSimStore((s) => s.job)
  const running = useSimStore((s) => s.running)
  const mode = useSimStore((s) => s.mode)
  const cancelRun = useSimStore((s) => s.cancelRun)

  if (!running || !job) return null

  const p = job.progress ?? 0
  const cur = job.stage
  const curIdx = Math.max(0, STAGES.findIndex((s) => s.key === cur))

  return (
    <div className="modal-wrap">
      <motion.div
        className="modal-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />
      <motion.div
        className="progress-card"
        initial={{ opacity: 0, y: 14, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      >
        <div className="progress-title">
          {mode === 'preview' ? 'Building geometry preview' : 'Running simulation'}
        </div>

        <div className="progress-stages">
          {STAGES.map((s, i) => {
            const Icon = s.icon
            const isDone = i < curIdx
            const isActive = i === curIdx
            return (
              <div
                key={s.key}
                className={cls(
                  'stage',
                  isDone && 'stage-done',
                  isActive && 'stage-active'
                )}
              >
                <div className="stage-icon">
                  {isDone ? <Check size={13} /> : <Icon size={14} />}
                </div>
                <span className="stage-label">{s.label}</span>
                {i < STAGES.length - 1 && (
                  <span className="stage-line" />
                )}
              </div>
            )
          })}
        </div>

        <div className="progress-track">
          <motion.div
            className="progress-bar"
            animate={{ width: `${Math.round(p * 100)}%` }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          />
        </div>

        <div className="progress-meta">
          <span className="progress-message num">
            {job.message || job.stage}
          </span>
          <span className="progress-elapsed num">
            {elapsed(job.elapsed)}
          </span>
        </div>

        <div className="progress-actions">
          <Button variant="danger" size="sm" icon={<Square size={13} />} onClick={() => void cancelRun()}>
            Cancel
          </Button>
        </div>
      </motion.div>
    </div>
  )
}