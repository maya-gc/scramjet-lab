import { motion } from 'framer-motion'
import { cls } from '../../lib/cls'

export function Toggle({
  checked,
  onChange,
  label,
  disabled
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={cls('toggle', checked && 'toggle-on')}
      onClick={() => onChange(!checked)}
    >
      <motion.span
        className="toggle-thumb"
        layout
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
    </button>
  )
}