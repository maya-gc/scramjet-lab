import {
  AlertTriangle,
  CheckCircle2,
  Gauge as GaugeIcon,
  Info
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useSimStore } from '../stores/sim'
import { Gauge } from './ui/Gauge'
import { Badge } from './ui/Badge'
import { Select } from './ui/Select'
import { cls } from '../lib/cls'
import { fmt, fmtK, fmtPct } from '../lib/format'
import type { Metrics } from '../lib/types'

export function ResultsPanel(): React.JSX.Element {
  const metrics = useSimStore((s) => s.metrics)
  const geometry = useSimStore((s) => s.geometry)
  const report = useSimStore((s) => s.report)
  const pastRuns = useSimStore((s) => s.pastRuns)
  const running = useSimStore((s) => s.running)
  const mode = useSimStore((s) => s.mode)

  if (!metrics && !geometry) {
    return (
      <div className="empty-rail">
        <GaugeIcon size={20} />
        <span>no results yet — run a case to populate this view</span>
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="empty-rail">
        <Info size={20} />
        <span>
          {geometry
            ? 'geometry preview computed — solver results appear after a full run'
            : 'no results yet'}
        </span>
      </div>
    )
  }

  return <ResultsBody metrics={metrics} report={report} pastRuns={pastRuns} running={running} mode={mode} />
}

function ResultsBody({
  metrics,
  report,
  pastRuns,
  running,
  mode
}: {
  metrics: Metrics
  report: unknown
  pastRuns: { workdir: string; case: string; metrics?: Partial<Metrics> }[]
  running: boolean
  mode: string | null
}): React.JSX.Element {
  void report
  const [compare, setCompare] = useState<string | null>(null)
  const compared = useMemo(
    () => pastRuns.find((r) => r.workdir === compare) ?? null,
    [pastRuns, compare]
  )

  const warnings: string[] = []
  if (metrics.separated) warnings.push('flow separation detected in the isolator/combustor')
  if ((metrics.unstart_risk ?? 0) > 0.5)
    warnings.push('high unstart risk — operating margin is thin')
  if (Math.abs(metrics.continuity_error) > 0.01)
    warnings.push(`mass continuity error ${fmtPct(metrics.continuity_error)}`)

  const compareRows: Array<{ key: string; label: string; fmt: (m: Metrics) => string }> = [
    { key: 'score', label: 'Score', fmt: (m) => fmt(m.score, 3) },
    { key: 'pressure_recovery', label: 'Pressure recovery', fmt: (m) => fmtPct(m.pressure_recovery) },
    { key: 'thrust_proxy', label: 'Thrust proxy', fmt: (m) => `${fmtK(m.thrust_proxy, 1)} N` },
    { key: 'continuity_error', label: 'Continuity', fmt: (m) => fmtPct(m.continuity_error) },
    { key: 'M_exit', label: 'Exit Mach', fmt: (m) => fmt(m.M_exit, 2) },
    { key: 'unstart_risk', label: 'Unstart risk', fmt: (m) => fmtPct(m.unstart_risk, 0) }
  ]

  return (
    <div className="results">
      <div className="results-badge-row">
        <Badge tone={metrics.valid ? 'success' : 'warning'} dot>
          {metrics.valid ? 'valid solution' : 'invalid solution'}
        </Badge>
        {running && mode === 'full' && (
          <Badge tone="accent" dot>
            running full case
          </Badge>
        )}
      </div>

      <AnimatePresence>
        {warnings.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="warn-stack"
          >
            {warnings.map((w) => (
              <div className="warn-row" key={w}>
                <AlertTriangle size={14} />
                <span>{w}</span>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="gauge-row">
        <Gauge
          value={metrics.score}
          label="score"
          sub="composite"
          color="var(--accent)"
          format={(v) => fmt(v, 2)}
        />
        <Gauge
          value={metrics.pressure_recovery}
          label="recovery"
          sub="p0 retention"
          color="#3ddc97"
          format={(v) => fmtPct(v, 1)}
        />
        <Gauge
          value={metrics.nozzle_momentum_eff}
          label="nozzle η"
          sub="momentum"
          color="#a78bfa"
          format={(v) => fmtPct(v, 1)}
        />
        <Gauge
          value={metrics.unstart_risk}
          label="unstart"
          sub="risk (inverted)"
          color={metrics.unstart_risk > 0.5 ? 'var(--danger)' : 'var(--success)'}
          format={(v) => fmtPct(v, 1)}
        />
      </div>

      <div className="metric-grid">
        <MetricCard label="Thrust proxy" value={`${fmtK(metrics.thrust_proxy, 1)} N`} sub="net axial force on fluid" />
        <MetricCard label="Specific thrust" value={`${fmtK(metrics.specific_thrust, 2)} N·s/kg`} sub="per captured air" accent />
        <MetricCard label="Net axial force" value={`${fmtK(metrics.net_axial_force_on_fluid, 1)} N`} sub="momentum balance" />
        <MetricCard label="Continuity error" value={fmtPct(metrics.continuity_error, 2)} sub="mass conservation" tone={Math.abs(metrics.continuity_error) > 0.01 ? 'bad' : 'ok'} />
        <MetricCard label="M combustor out" value={fmt(metrics.M_combustor_out, 2)} sub="combustor exit Mach" />
        <MetricCard label="M isolator out" value={fmt(metrics.M_isolator_out, 2)} sub="isolator exit Mach" />
        <MetricCard label="Exit Mach" value={fmt(metrics.M_exit, 2)} sub="nozzle exit" />
        <MetricCard label="Separation fraction" value={fmtPct(metrics.sep_fraction, 1)} sub="wall separated cells" tone={metrics.separated ? 'bad' : 'ok'} />
        <MetricCard label="Operating margin" value={fmtPct(metrics.operating_margin, 1)} sub="back-pressure headroom" />
        <MetricCard label="Static p rise" value={`${fmtK(metrics.static_pressure_rise, 1)} Pa`} sub="relative to freestream" />
      </div>

      {pastRuns.length > 0 && (
        <div className="compare">
          <div className="compare-head">
            <span className="compare-title">Compare</span>
            <div className="compare-controls">
              <Select
                size="sm"
                value={compare ?? ''}
                onChange={setCompare}
                options={[
                  { value: '', label: '— versus —' },
                  ...pastRuns.map((r) => ({
                    value: r.workdir,
                    label: r.case
                  }))
                ]}
              />
            </div>
          </div>
          {compared && (
            <table className="compare-table">
              <thead>
                <tr>
                  <th />
                  <th>current</th>
                  <th>{compared.case}</th>
                </tr>
              </thead>
              <tbody>
                {compareRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td className="num">{row.fmt(metrics)}</td>
                    <td className="num">
                      {compared.metrics && row.key in compared.metrics && compared.metrics[row.key] != null
                        ? row.fmt(compared.metrics as Metrics)
                        : '\u2013'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function MetricCard({
  label,
  value,
  sub,
  accent,
  tone = 'normal'
}: {
  label: string
  value: string
  sub?: string
  accent?: boolean
  tone?: 'normal' | 'ok' | 'bad'
}): React.JSX.Element {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.16, ease: 'easeOut' }}
      className={cls(
        'metric-card',
        accent && 'metric-card-accent',
        tone === 'bad' && 'metric-card-bad'
      )}
    >
      <div className="metric-card-value num">{value}</div>
      <div className="metric-card-label">{label}</div>
      {sub && <div className="metric-card-sub">{sub}</div>}
      {tone === 'ok' && <CheckCircle2 className="metric-card-icon" size={12} />}
    </motion.div>
  )
}