import { motion } from 'framer-motion'
import { useMemo } from 'react'
import { fmt } from '../../lib/format'
import { cls } from '../../lib/cls'

const ARC = 0.74

export function Gauge({
  value = 0,
  size = 128,
  label,
  sub,
  color,
  format = (v) => fmt(v * 100, 0),
  className
}: {
  value?: number
  size?: number
  label?: string
  sub?: string
  color?: string
  format?: (v: number) => string
  className?: string
}) {
  const r = size / 2 - 10
  const c = 2 * Math.PI * r
  const drawn = c * ARC
  const frac = useMemo(() => Math.max(0, Math.min(1, value)), [value])

  return (
    <div className={cls('gauge', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <g transform={`rotate(${(1 - ARC) * 180} ${size / 2} ${size / 2})`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={7}
            strokeDasharray={drawn}
            strokeLinecap="round"
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={7}
            strokeLinecap="round"
            strokeDasharray={drawn}
            initial={{ strokeDashoffset: drawn }}
            animate={{ strokeDashoffset: drawn * (1 - frac) }}
            transition={{ type: 'spring', stiffness: 90, damping: 22 }}
            style={{ filter: `drop-shadow(0 0 6px ${color}66)` }}
          />
        </g>
      </svg>
      <div className="gauge-center">
        <motion.div
          className="gauge-value num"
          key={format(frac)}
          initial={{ opacity: 0.4, y: 2 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {format(frac)}
        </motion.div>
        {label && <div className="gauge-label">{label}</div>}
        {sub && <div className="gauge-sub">{sub}</div>}
      </div>
    </div>
  )
}