import { useEffect } from 'react'
import { Header } from './components/Header'
import { StatusBar } from './components/StatusBar'
import { ScenePanel } from './components/ScenePanel'
import { RightRail } from './components/RightRail'
import { ProgressOverlay } from './components/ProgressOverlay'
import { useAppStore } from './stores/app'
import { useUIStore } from './stores/ui'

export function App(): React.JSX.Element {
  const init = useAppStore((s) => s.init)
  const setBackend = useAppStore((s) => s.setBackend)
  const railOpen = useUIStore((s) => s.railOpen)
  const railWidth = useUIStore((s) => s.railWidth)

  useEffect(() => {
    void init()
  }, [init])

  useEffect(() => {
    const off = window.scramjet.onBackendStatus((info) => setBackend(info))
    return off
  }, [setBackend])

  return (
    <div className="app">
      <Header />
      <div className="workspace">
        <div className="scene-area">
          <ScenePanel />
        </div>
        {railOpen && (
          <>
            <RailResizeHandle />
            <aside className="rail" style={{ width: railWidth }}>
              <RightRail />
            </aside>
          </>
        )}
      </div>
      <StatusBar />
      <ProgressOverlay />
    </div>
  )
}

function RailResizeHandle(): React.JSX.Element {
  const setRailWidth = useUIStore((s) => s.setRailWidth)
  const open = useUIStore((s) => s.railOpen)
  const setOpen = useUIStore((s) => s.setRailOpen)
  const width = useUIStore((s) => s.railWidth)

  return (
    <div
      className="rail-handle no-drag"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        const startX = e.clientX
        const startW = width
        const move = (ev: PointerEvent): void => {
          if (open) setRailWidth(startW - (ev.clientX - startX))
        }
        const up = (): void => {
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
          setOpen(true)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
      }}
      title="Drag to resize — click to collapse"
    >
      <span className="rail-handle-dot" />
    </div>
  )
}