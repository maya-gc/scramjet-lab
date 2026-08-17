import { cls } from '../../lib/cls'

export function Slider({
  min,
  max,
  step,
  value,
  onChange,
  disabled,
  className
}: {
  min: number
  max: number
  step: number
  value: number
  onChange: (v: number) => void
  disabled?: boolean
  className?: string
}) {
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0
  return (
    <input
      type="range"
      className={cls('slider', disabled && 'slider-disabled', className)}
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ ['--pct' as string]: `${pct}%` }}
      aria-label="slider"
    />
  )
}