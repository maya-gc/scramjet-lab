import { ChevronDown } from 'lucide-react'
import { cls } from '../../lib/cls'

export function Select<T extends string | number>({
  value,
  onChange,
  options,
  className,
  size = 'md'
}: {
  value: T
  onChange: (v: T) => void
  options: Array<{ value: T; label: string; disabled?: boolean }>
  className?: string
  size?: 'sm' | 'md'
}) {
  return (
    <span className={cls('select-wrap', `select-${size}`, className)}>
      <select
        className="select-input"
        value={value}
        onChange={(e) => {
          const raw: string = e.target.value
          const match = options.find((o) => String(o.value) === raw)
          if (match) onChange(match.value)
        }}
      >
        {options.map((o) => (
          <option key={String(o.value)} value={String(o.value)} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="select-chevron" size={14} />
    </span>
  )
}