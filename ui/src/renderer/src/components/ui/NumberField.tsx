import { ChevronUp, ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cls } from '../../lib/cls'

function formatNum(v: number, decimals: number): string {
  return v.toLocaleString('en-US', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: 0
  })
}

export function NumberField({
  value,
  onCommit,
  step,
  decimals = 3,
  min,
  max,
  disabled,
  className
}: {
  value: number
  onCommit: (v: number) => void
  step: number
  decimals?: number
  min?: number
  max?: number
  disabled?: boolean
  className?: string
}) {
  const [text, setText] = useState<string | null>(null)
  const shown = text ?? formatNum(value, decimals)

  useEffect(() => {
    setText(null)
  }, [value, decimals])

  const clamp = (n: number): number => {
    if (min != null) n = Math.max(min, n)
    if (max != null) n = Math.min(max, n)
    return n
  }

  const commit = (n: number): void => {
    if (Number.isFinite(n)) onCommit(clamp(n))
    setText(null)
  }

  const nudge = (dir: 1 | -1): void => {
    const next = clamp(value + dir * step)
    onCommit(next)
    setText(null)
  }

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      flush()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      nudge(1)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      nudge(-1)
    } else if (e.key === 'Escape') {
      setText(null)
    }
  }

  const flush = (): void => {
    const t = (text ?? '').trim().replace(',', '.')
    if (t === '') {
      setText(null)
      return
    }
    const n = Number(t)
    if (!Number.isFinite(n)) {
      setText(null)
      return
    }
    commit(n)
  }

  return (
    <div className={cls('nfield', disabled && 'nfield-disabled', className)}>
      <input
        className="nfield-input num"
        value={shown}
        inputMode="decimal"
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={flush}
        onKeyDown={handleKey}
        aria-label="numeric input"
      />
      <div className="nfield-steps">
        <button type="button" className="nfield-step" onClick={() => nudge(1)} disabled={disabled}>
          <ChevronUp size={11} strokeWidth={2.6} />
        </button>
        <button
          type="button"
          className="nfield-step"
          onClick={() => nudge(-1)}
          disabled={disabled}
        >
          <ChevronDown size={11} strokeWidth={2.6} />
        </button>
      </div>
    </div>
  )
}