export function fmt(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '\u2013'
  return v.toLocaleString('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  })
}

/** Compact engineering format: 2.5k / 1.24M / 0.0034 m */
export function fmtK(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '\u2013'
  const a = Math.abs(v)
  const sign = v < 0 ? '\u2212' : ''
  if (a >= 1e9) return `${sign}${fmt(v / 1e9, digits)}G`
  if (a >= 1e6) return `${sign}${fmt(v / 1e6, digits)}M`
  if (a >= 1e3) return `${sign}${fmt(v / 1e3, digits)}k`
  return fmt(v, Math.max(digits, 2))
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return '\u2013'
  return `${(v * 100).toLocaleString('en-US', { maximumFractionDigits: digits })}%`
}

export function fmtExp(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '\u2013'
  if (v === 0) return '0'
  return v.toExponential(2)
}

export function elapsed(sec: number | null | undefined): string {
  if (sec == null || sec < 0) return '\u2013'
  const s = Math.floor(sec)
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m === 0) return `${s}s`
  return `${m}m ${r.toString().padStart(2, '0')}s`
}

export function timeAgo(epoch: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epoch))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}