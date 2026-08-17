import { motion } from 'framer-motion'
import { useState } from 'react'
import { Cpu, Flame, Play, RotateCcw, Zap } from 'lucide-react'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Select } from './ui/Select'
import { useAppStore } from '../stores/app'
import { useParamsStore } from '../stores/params'
import { useSimStore } from '../stores/sim'
import type { RunMode } from '../stores/sim'

export function Header(): React.JSX.Element {
  const cases = useAppStore((s) => s.cases)
  const activeCase = useAppStore((s) => s.activeCase)
  const selectCase = useAppStore((s) => s.selectCase)
  const describe = useAppStore((s) => s.describe)
  const backend = useAppStore((s) => s.backend)
  const error = useAppStore((s) => s.error)
  const solverExe = useAppStore((s) => s.solverExe)
  const setSolverExe = useAppStore((s) => s.setSolverExe)

  const groups = useParamsStore((s) => s.groups)
  const validation = useParamsStore((s) => s.validation)
  const dirty = useParamsStore((s) => s.dirty)
  const isDefault = useParamsStore((s) => s.isDefault)
  const reset = useParamsStore((s) => s.reset)
  const overrides = useParamsStore((s) => s.overrides)
  const validateNow = useParamsStore((s) => s.validateNow)

  const running = useSimStore((s) => s.running)
  const submitting = useSimStore((s) => s._submitting)
  const startRun = useSimStore((s) => s.startRun)
  const mode = useSimStore((s) => s.mode)

  const [errorBanner, setErrorBanner] = useState<string | null>(null)

  const online = backend?.state === 'online'
  const canRun =
    !!online &&
    !running &&
    !!groups &&
    !submitting &&
    (validation ? validation.valid : true)

  const handleRun = async (m: RunMode): Promise<void> => {
    setErrorBanner(null)
    const v = await validateNow()
    if (!v?.valid) {
      setErrorBanner(v?.errors[0] ?? 'parameters fail validation')
      return
    }
    try {
      await startRun(m, overrides())
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <header className="header">
      <div className="header-left">
        <div className="brand">
          <motion.div
            className="brand-mark"
            whileHover={{ rotate: 12, scale: 1.06 }}
            transition={{ type: 'spring', stiffness: 400, damping: 18 }}
          >
            <Flame size={18} strokeWidth={2.4} />
          </motion.div>
          <div className="brand-text">
            <span className="brand-name">SCRAMJET LAB</span>
            <span className="brand-sub">hypersonic propulsive flow</span>
          </div>
        </div>

        <div className="header-divider" />

        <div className="case-picker">
          <span className="case-picker-label">Case</span>
          <Select
            value={activeCase ?? ''}
            onChange={(v) => void selectCase(v)}
            options={cases.map((c) => ({ value: c.name, label: c.name }))}
            size="md"
          />
          <Badge tone={describe?.case.dimension === 3 ? 'accent' : 'neutral'}>
            {describe?.case.dimension === 3 ? '3D' : '2D'}
          </Badge>
        </div>
      </div>

      <div className="header-right">
        {errorBanner && (
          <motion.div
            className="header-error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            {errorBanner}
          </motion.div>
        )}

        {dirty && (
          <motion.div
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            className="header-dirty"
          >
            <span className="header-dirty-dot" />
            unsaved parameters
          </motion.div>
        )}

        {!online ? (
          <Badge tone={backend?.state === 'connecting' ? 'warning' : 'danger'} dot>
            {backend?.state === 'connecting' ? 'connecting' : 'offline'}
          </Badge>
        ) : (
          <Badge tone="success" dot>
            backend online
          </Badge>
        )}

        {online && (
          <Badge tone={backend?.accel?.gpu ? 'accent' : 'neutral'}>
            <Cpu size={13} style={{ verticalAlign: '-2px', marginRight: 5 }} />
            {backend?.accel?.gpu ? 'GPU cuPy' : 'CPU numpy'}
          </Badge>
        )}

        <input
          className="header-solver"
          type="text"
          placeholder="SU2 solver exe (CUDA build)"
          value={solverExe}
          onChange={(e) => setSolverExe(e.target.value)}
          spellCheck={false}
        />

        <Button
          variant="ghost"
          size="md"
          icon={<RotateCcw size={15} />}
          disabled={isDefault() || running}
          onClick={reset}
        >
          Reset
        </Button>

        <Button
          variant="soft"
          size="md"
          icon={<Zap size={15} />}
          disabled={!canRun}
          title="Geometry + mesh + case files only (no solver)"
          onClick={() => void handleRun('preview')}
        >
          Preview
        </Button>

        <Button
          variant="primary"
          size="md"
          icon={running ? undefined : <Play size={15} fill="currentColor" />}
          loading={running || submitting}
          disabled={!canRun}
          onClick={() => void handleRun('full')}
        >
          {running
            ? `Running${mode === 'preview' ? ' preview' : ''}…`
            : dirty
              ? 'Run simulation'
              : 'Run'}
        </Button>

        {error && !online && (
          <Badge tone="danger" dot>
            backend error
          </Badge>
        )}
      </div>
    </header>
  )
}