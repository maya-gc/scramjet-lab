import { cls } from '../../lib/cls'

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
  size = 'md'
}: {
  options: Array<{ value: T; label: string }>
  value: T
  onChange: (v: T) => void
  className?: string
  size?: 'sm' | 'md'
}) {
  return (
    <div className={cls('seg', `seg-${size}`, className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          className={cls('seg-item', o.value === value && 'seg-item-active')}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}