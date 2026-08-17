import { Box, Crosshair, Grid3X3, Layers, Rotate3d, Wind } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ScramjetScene } from '../three/engine'
import { REGION_COLORS } from '../three/builder'
import { useAppStore } from '../stores/app'
import { useParamsStore } from '../stores/params'
import { useSimStore } from '../stores/sim'
import { useUIStore, type RegionId, type SceneView } from '../stores/ui'
import { cls } from '../lib/cls'
import { fmt } from '../lib/format'

const REGIONS: Array<{ id: RegionId; label: string }> = [
  { id: 'inlet', label: 'Inlet' },
  { id: 'isolator', label: 'Isolator' },
  { id: 'combustor', label: 'Combustor' },
  { id: 'nozzle', label: 'Nozzle' },
  { id: 'strut', label: 'Strut' }
]

const VIEWS: Array<{ id: SceneView; label: string }> = [
  { id: 'extruded', label: 'Ducto' },
  { id: 'annular', label: 'Anular' }
]

export function ScenePanel(): React.JSX.Element {
  const mount = useRef<HTMLDivElement>(null)
  const engine = useRef<ScramjetScene | null>(null)

  const geometry = useSimStore((s) => s.geometry)
  const stations = useSimStore((s) => s.stations)
  const flowDerived = useParamsStore((s) => s.flowDerived)
  const backend = useAppStore((s) => s.backend)
  const running = useSimStore((s) => s.running)
  const mode = useSimStore((s) => s.mode)

  const sceneView = useUIStore((s) => s.sceneView)
  const showParticles = useUIStore((s) => s.showParticles)
  const showBands = useUIStore((s) => s.showBands)
  const showGrid = useUIStore((s) => s.showGrid)
  const highlight = useUIStore((s) => s.highlight)
  const camFlip = useUIStore((s) => s.camFlip)
  const setSceneView = useUIStore((s) => s.setSceneView)
  const setHighlight = useUIStore((s) => s.setHighlight)
  const setShowParticles = useUIStore((s) => s.setShowParticles)
  const setShowBands = useUIStore((s) => s.setShowBands)
  const setShowGrid = useUIStore((s) => s.setShowGrid)
  const flipCamera = useUIStore((s) => s.flipCamera)

  useEffect(() => {
    if (!mount.current) return
    const scene = new ScramjetScene(mount.current)
    engine.current = scene
    return () => {
      scene.dispose()
      engine.current = null
    }
  }, [])

  useEffect(() => {
    engine.current?.setGeometry(geometry)
    if (geometry) {
      engine.current?.setFlow(stations, flowDerived?.v_inf ?? 0)
    }
  }, [geometry, stations, flowDerived])

  useEffect(() => {
    engine.current?.setView(sceneView)
  }, [sceneView])

  useEffect(() => {
    engine.current?.setVisuals({
      particles: showParticles,
      bands: showBands,
      grid: showGrid
    })
  }, [showParticles, showBands, showGrid])

  useEffect(() => {
    engine.current?.setHighlight(highlight)
  }, [highlight])

  useEffect(() => {
    if (camFlip > 0) engine.current?.flipView()
  }, [camFlip])

  const online = backend?.state === 'online'
  const derived = geometry?.derived
  const annular = sceneView === 'annular'

  return (
    <div className="scene relative fill">
      <div ref={mount} className="scene-mount" />

      {/* top-left: view label */}
      <div className="scene-caption">
        <div className="scene-caption-title">
          {annular ? 'ANULAR · CROSS-SECTION VECTORS' : 'ENGINE GEOMETRY'} {derived ? '· LIVE' : ''}
        </div>
        <div className="scene-caption-sub">
          {derived
            ? annular
              ? `R_nacelle = 50 mm · H = ${fmt(derived.H_capture * 100, 1)} cm · anel vermelho = entrada`
              : `L = ${fmt(derived.L_total * 100, 1)} cm · H = ${fmt(derived.H_capture * 100, 1)} cm · B = ${fmt(derived.B * 100, 1)} cm`
            : 'no geometry yet'}
        </div>
      </div>

      {/* top-right: view modes + visual toggles */}
      <div className="scene-tools">
        <div className="scene-view-mode">
          {VIEWS.map((v) => (
            <ToolBtn
              key={v.id}
              active={sceneView === v.id}
              onClick={() => setSceneView(v.id)}
              title={v.id === 'annular' ? 'Axisymmetric engine, same structure as crosssection_vectors.gif' : 'Extruded duct view'}
            >
              {v.label}
            </ToolBtn>
          ))}
        </div>
        <ToolBtn
          active={showParticles}
          onClick={() => setShowParticles(!showParticles)}
          title="Flow particles"
        >
          <Wind size={15} />
          Flow
        </ToolBtn>
        {!annular && (
          <ToolBtn active={showBands} onClick={() => setShowBands(!showBands)} title="Region bands">
            <Layers size={15} />
            Regions
          </ToolBtn>
        )}
        {!annular && (
          <ToolBtn active={showGrid} onClick={() => setShowGrid(!showGrid)} title="Reference grid">
            <Grid3X3 size={15} />
            Grid
          </ToolBtn>
        )}
        <ToolBtn onClick={flipCamera} title="Cycle camera view">
          <Rotate3d size={15} />
          View
        </ToolBtn>
      </div>

      {/* bottom-left: region pills (extruded only) */}
      {derived && !annular && (
        <div className="scene-regions">
          {REGIONS.map((r) => {
            const visible = geometry?.strut != null || r.id !== 'strut'
            if (!visible) return null
            const active = highlight === r.id
            return (
              <button
                key={r.id}
                className={cls('region-pill', active && 'region-pill-active')}
                style={{ ['--rc' as string]: REGION_COLORS[r.id] }}
                onClick={() => setHighlight(active ? null : r.id)}
              >
                <span className="region-pill-dot" style={{ background: REGION_COLORS[r.id] }} />
                {r.label}
              </button>
            )
          })}
        </div>
      )}

      {/* bottom-right hint */}
      <div className="scene-hint">
        <Crosshair size={12} />
        drag to orbit · scroll to zoom
      </div>

      {/* empty state / busy state */}
      <AnimatePresence>
        {!geometry && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="scene-empty"
          >
            <div className="scene-empty-card">
              <Box size={26} className="scene-empty-icon" />
              {!online ? (
                <>
                  <strong>{backend?.state === 'connecting' ? 'connecting to backend…' : 'backend offline'}</strong>
                  <span>{backend?.error ?? 'waiting for the simulation server'}</span>
                </>
              ) : (
                <>
                  <strong>{running && mode === 'preview' ? 'building geometry…' : 'no geometry in scene'}</strong>
                  <span>
                    {running ? 'mesh & case files are being prepared' : 'press Run or Preview to compute the engine'}
                  </span>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {showParticles && (
        <div className="scene-legend">
          <span className="scene-legend-swatch" style={{ background: 'linear-gradient(90deg,#0c0c2e,#1d4dd8,#2ec7d0,#46e07f,#e0b43c,#e0582e)' }} />
          <span className="scene-legend-label">{annular ? 'Mach · cometa (estrutura do gif)' : 'Mach (colored flow)'}</span>
        </div>
      )}
    </div>
  )
}

function ToolBtn({
  active,
  onClick,
  title,
  children
}: {
  active?: boolean
  onClick: () => void
  title: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      className={cls('tool-btn', active && 'tool-btn-active')}
      onClick={onClick}
      title={title}
    >
      {children}
    </motion.button>
  )
}