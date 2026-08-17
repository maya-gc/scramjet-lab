import type { ReactNode } from 'react'
import { cls } from '../../lib/cls'

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  padded = true,
  flush
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
  flush?: boolean
}) {
  return (
    <section className={cls('panel', flush && 'panel-flush', className)}>
      {(title != null || actions != null) && (
        <header className="panel-head">
          <div>
            {title != null && <h3 className="panel-title">{title}</h3>}
            {subtitle != null && <p className="panel-subtitle">{subtitle}</p>}
          </div>
          {actions != null && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'panel-body' : undefined}>{children}</div>
    </section>
  )
}