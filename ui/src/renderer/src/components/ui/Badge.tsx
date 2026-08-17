import { cls } from '../../lib/cls'

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger'

export function Badge({
  tone = 'neutral',
  dot = false,
  className,
  children
}: {
  tone?: BadgeTone
  dot?: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <span className={cls('badge', `badge-${tone}`, className)}>
      {dot && <span className={cls('badge-dot', `badge-dot-${tone}`)} />}
      <span className="badge-text">{children}</span>
    </span>
  )
}