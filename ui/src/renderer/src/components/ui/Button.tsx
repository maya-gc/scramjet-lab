import { motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'
import { cls } from '../../lib/cls'

interface ButtonProps extends ComponentProps<'button'> {
  variant?: 'primary' | 'soft' | 'ghost' | 'outline' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
  children?: ReactNode
}

export function Button({
  variant = 'soft',
  size = 'md',
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: loading || disabled ? 1 : 0.972 }}
      whileHover={loading || disabled ? undefined : { scale: 1.015 }}
      transition={{ duration: 0.16, ease: 'easeOut' }}
      className={cls('btn', `btn-${variant}`, `btn-${size}`, className)}
      disabled={disabled || loading}
      {...(rest as object)}
    >
      {loading ? (
        <Loader2 className="btn-spinner" size={15} strokeWidth={2.2} />
      ) : (
        icon
      )}
      {children != null && <span className="btn-label">{children}</span>}
    </motion.button>
  )
}

export function IconButton({
  variant = 'ghost',
  size = 'md',
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.14, ease: 'easeOut' }}
      className={cls('btn', 'btn-icon', `btn-${variant}`, `btn-${size}`, className)}
      {...(rest as object)}
    >
      {children}
    </motion.button>
  )
}