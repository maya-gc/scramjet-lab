import { AlertTriangle, Check, Info } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useParamsStore } from '../stores/params'
import { PARAM_GROUPS, fromDisplay, metaForParam, toDisplay } from '../lib/paramMeta'
import { NumberField } from './ui/NumberField'
import { Slider } from './ui/Slider'
import { Toggle } from './ui/Toggle'
import { Spinner } from './ui/Spinner'
import { cls } from '../lib/cls'
import { fmt, fmtK } from '../lib/format'

export function ParamsPanel(): React.JSX.Element {
  const groups = useParamsStore((s) => s.groups)
  const defaults = useParamsStore((s) => s.defaults)
  const validation = useParamsStore((s) => s.validation)
  const validating = useParamsStore((s) => s.validating)
  const dirty = useParamsStore((s) => s.dirty)
  const flowDerived = useParamsStore((s) => s.flowDerived)
  const validateNow = useParamsStore((s) => s.validateNow)
  const setParam = useParamsStore((s) => s.setParam)

  useEffect(() => {
    if (!dirty) return
    const t = setTimeout(() => void validateNow(), 450)
    return () => clearTimeout(t)
  }, [groups, dirty, validateNow])

  if (!groups || !defaults) {
    return (
      <div className="empty-rail">
        <Spinner size={20} />
        <span>waiting for case…</span>
      </div>
    )
  }

  return (
    <div className="params">
      {validation && (
        <div
          className={cls(
            'validation',
            validation.valid ? 'validation-ok' : 'validation-bad'
          )}
        >
          {validating ? (
            <Spinner size={14} />
          ) : validation.valid ? (
            <Check size={14} />
          ) : (
            <AlertTriangle size={14} />
          )}
          <span>
            {validation.valid
              ? 'geometry & flow parameters check out'
              : validation.errors.join(' · ')}
          </span>
        </div>
      )}

      {flowDerived && <FlowReadout d={flowDerived} />}

      {PARAM_GROUPS.map((g) => (
        <section className="param-group" key={g.key}>
          <header className="param-group-head">
            <div>
              <h3 className="param-group-title">{g.title}</h3>
              <p className="param-group-blurb">{g.blurb}</p>
            </div>
          </header>
          {g.params.map((meta) => {
            const raw = groups[g.key][meta.key]
            if (meta.kind === 'toggle') {
              return (
                <div className="field-toggle-row" key={meta.key}>
                  <span className="field-label">
                    <span className="field-label-text">{meta.label}</span>
                  </span>
                  <Toggle
                    checked={Boolean(raw)}
                    onChange={(v) => void setParam(g.key, meta.key, v)}
                  />
                </div>
              )
            }
            const def = defaults[g.key][meta.key] as number
            const isDirty = Math.abs((raw as number) - def) > 1e-12
            return (
              <ParamField
                key={meta.key}
                group={g.key}
                keyName={meta.key}
                label={meta.label}
                unit={meta.unit}
                raw={raw as number}
                def={def}
                isDirty={isDirty}
                onCommit={(v) => void setParam(g.key, meta.key, v)}
              />
            )
          })}
        </section>
      ))}
    </div>
  )
}

function ParamField({
  group,
  keyName,
  label,
  unit,
  raw,
  def,
  isDirty,
  onCommit
}: {
  group: string
  keyName: string
  label: string
  unit?: string
  raw: number
  def: number
  isDirty: boolean
  onCommit: (v: number) => void
}): React.JSX.Element {
  const meta = metaForParam(group, keyName)
  const disp = toDisplay(raw, meta)

  const [min, max] = useMemo(() => {
    if (meta.range) return meta.range
    const factor = meta.rangeFactor ?? [0.5, 2]
    const d = toDisplay(def, meta)
    return [d * factor[0], d * factor[1]]
  }, [meta, def])

  return (
    <div className={cls('field', 'focus-ring')}>
      <div className="field-label">
        <span className={cls('field-label-text', isDirty && 'field-dirty')}>
          {label}
        </span>
        {unit && <span className="field-unit">{unit}</span>}
        {isDirty && (
          <motion.span
            className="field-dirty-dot"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
          />
        )}
      </div>
      <div className="field-controls">
        <NumberField
          value={disp}
          step={meta.step}
          decimals={meta.decimals}
          onCommit={(d) => onCommit(fromDisplay(d, meta))}
        />
      </div>
      <div className="field-slider-row">
        <Slider
          min={min}
          max={max}
          step={Math.max(meta.step, Math.abs(max - min) / 200)}
          value={disp}
          onChange={(d) => onCommit(fromDisplay(d, meta))}
        />
      </div>
    </div>
  )
}

function FlowReadout({
  d
}: {
  d: { mach: number; p_inf: number; rho_inf: number; v_inf: number; a_inf: number; t_inf: number }
}): React.JSX.Element {
  const items = [
    { k: 'Mach', v: fmt(d.mach, 2) },
    { k: 'p', v: `${fmtK(d.p_inf / 1000, 2)} kPa` },
    { k: 'T', v: `${fmt(d.t_inf, 1)} K` },
    { k: 'ρ', v: `${fmtK(d.rho_inf, 3)} kg/m³` },
    { k: 'V∞', v: `${fmt(d.v_inf, 0)} m/s` },
    { k: 'a', v: `${fmt(d.a_inf, 0)} m/s` }
  ]
  return (
    <div className="flow-readout">
      <div className="flow-readout-head">
        <Info size={13} />
        <span>derived inlet state</span>
      </div>
      <div className="flow-readout-grid">
        {items.map((it) => (
          <div className="flow-readout-item" key={it.k}>
            <span className="flow-readout-k">{it.k}</span>
            <span className="flow-readout-v num">{it.v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}