import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { buildEngine, REGION_COLORS, REGION_ORDER } from './builder'
import { FlowField } from './flow'
import { buildAnnularEngine, VectorStreaks } from './annular'
import { passageFromGeo } from './passage'
import type { GeometryPayload, Stations } from '../lib/types'
import type { RegionId, SceneView } from '../stores/ui'

const SPEED_SCALE = 5

const BG_EXTRUDED = 0x0a0a0c
const BG_ANNUAR = 0xeef2f5

const BASE_BAND_OPACITY = 0.16
const HIGHLIGHT_OPACITY = 0.5
const DIM_BAND_OPACITY = 0.08

export class ScramjetScene {
  private container: HTMLElement
  private renderer: THREE.WebGLRenderer
  private scene: THREE.Scene
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private raf = 0
  private last = 0
  private resizeObserver: ResizeObserver
  private disposed = false

  private root = new THREE.Group()
  private model!: ReturnType<typeof buildEngine>
  private flow: FlowField | null = null
  private annular!: ReturnType<typeof buildAnnularEngine>
  private streaks: VectorStreaks | null = null
  private annularLights = new THREE.Group()
  private grid: THREE.GridHelper
  private fallbackVx = 1200
  private maxMachSeen = 4
  private targetOpacities = new Map<RegionId, number>()
  private highlightId: RegionId | null = null
  private view: SceneView = 'extruded'
  private showParticles = true
  private showGrid = true
  private webgl2 = true

  constructor(container: HTMLElement) {
    this.container = container

    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setClearColor(BG_EXTRUDED, 1)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    container.appendChild(this.renderer.domElement)
    // GPU particles need WebGL2 (GLSL3 vertex-shader textures). Without it we
    // fall back to the static geometry only — no particles, no trails.
    this.webgl2 = this.renderer.capabilities.isWebGL2

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(BG_EXTRUDED)

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.02, 100)
    this.camera.position.set(2.4, 1.1, 2.2)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.target.set(0.6, 0.1, 0)
    this.controls.minDistance = 0.4
    this.controls.maxDistance = 60

    const ambient = new THREE.AmbientLight(0x3f4a63, 1.1)
    const key = new THREE.DirectionalLight(0xcfe6ff, 1.7)
    key.position.set(1.4, 2.2, 1.6)
    const fill = new THREE.DirectionalLight(0x6c7a99, 0.6)
    fill.position.set(-1.5, 0.2, -1.2)
    this.scene.add(ambient, key, fill)

    // Neutral lighting for the annular (light-background) mode.
    this.annularLights.add(new THREE.AmbientLight(0xffffff, 1.35))
    const aKey = new THREE.DirectionalLight(0xffffff, 1.7)
    aKey.position.set(1.6, 2.4, 1.8)
    const aFill = new THREE.DirectionalLight(0xffffff, 0.55)
    aFill.position.set(-1.2, 0.3, -1.1)
    this.annularLights.add(aKey, aFill)
    this.annularLights.visible = false
    this.scene.add(this.annularLights)

    this.grid = new THREE.GridHelper(4, 14, 0x1c2a3a, 0x151a22)
    ;(this.grid.material as THREE.Material).transparent = true
    ;(this.grid.material as THREE.Material).opacity = 0.35
    this.grid.position.y = -0.02
    this.scene.add(this.grid)

    this.root.scale.setScalar(SPEED_SCALE)
    this.scene.add(this.root)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(container)
    this.resize()

    this.loop = this.loop.bind(this)
    this.last = performance.now()
    this.loop()
  }

  // ---- public API ----------------------------------------------------------
  setGeometry(geo: GeometryPayload | null): void {
    if (this.model) {
      this.model.dispose()
      this.root.remove(this.model.group)
      this.flow?.dispose()
      this.root.remove(this.flow?.points as THREE.Object3D)
    }
    if (this.annular) {
      this.annular.dispose()
      this.streaks?.dispose()
      this.root.remove(this.annular.group)
    }
    if (!geo) return
    this.model = buildEngine(geo)
    this.root.add(this.model.group)

    this.targetOpacities.clear()
    const all: RegionId[] = [...REGION_ORDER, 'strut']
    for (const id of all) {
      this.targetOpacities.set(id, BASE_BAND_OPACITY)
    }

    this.annular = buildAnnularEngine(geo)
    this.root.add(this.annular.group)

    if (this.webgl2) {
      this.flow = new FlowField(passageFromGeo(geo), SPEED_SCALE, {
        renderer: this.renderer,
        camera: this.camera
      })
      this.flow.points.renderOrder = 2
      this.root.add(this.flow.points)

      this.streaks = new VectorStreaks(passageFromGeo(geo), {
        renderer: this.renderer,
        camera: this.camera
      })
      this.annular.group.add(this.streaks.lines, this.streaks.heads)
    }

    this.syncView()
    this.frameAdaptive()
  }

  setFlow(stations: Stations | null, fallbackVx: number): void {
    if (fallbackVx > 0) this.fallbackVx = fallbackVx
    if (stations) {
      const ms = Object.values(stations)
        .filter((s): s is NonNullable<typeof s> => s != null)
        .map((s) => s.M_massavg)
        .filter((m) => Number.isFinite(m))
      if (ms.length) this.maxMachSeen = Math.max(1.6, ...ms)
    }
    this.flow?.setState(stations, this.fallbackVx, this.maxMachSeen)
    this.streaks?.setState(stations, this.fallbackVx, this.maxMachSeen)
  }

  setVisuals(v: { particles?: boolean; bands?: boolean; grid?: boolean }): void {
    if (v.particles != null) this.showParticles = v.particles
    if (v.bands != null && this.model) {
      const all: RegionId[] = [...REGION_ORDER, 'strut']
      for (const id of all) {
        const mesh = this.model.regions[id]
        if (mesh) mesh.visible = v.bands
      }
    }
    if (v.grid != null) this.showGrid = v.grid
    this.syncParticles()
    this.syncGrid()
  }

  setView(view: SceneView): void {
    if (view === this.view) return
    this.view = view
    this.syncView()
    this.frameAdaptive()
  }

  setHighlight(id: RegionId | null): void {
    this.highlightId = id
  }

  private viewIndex = 0

  flipView(): void {
    const box = this.activeBox()
    if (!box) return
    const center = box.getCenter(new THREE.Vector3())
    const dist = this.viewDist(box)
    if (this.view === 'annular') {
      const azs = [0.61, 1.45, -0.65]
      const v = azs[this.viewIndex++ % azs.length]
      this.placeIsoCam(center, dist, v)
      this.controls.target.copy(center)
      this.controls.update()
      return
    }
    const views = [
      { az: -0.85, el: 0.6 },
      { az: 1.05, el: 0.85 },
      { az: 0.15, el: 1.22 }
    ]
    const v = views[this.viewIndex++ % views.length]
    this.camera.position.set(
      center.x + dist * Math.sin(v.el) * Math.sin(v.az),
      center.y + dist * Math.cos(v.el),
      center.z + dist * Math.sin(v.el) * Math.cos(v.az)
    )
    this.controls.target.copy(center)
    this.controls.update()
  }

  frameCamera(): void {
    this.frameAdaptive()
  }

  /** Iso camera with gif-style azimuth rotation (same math as the backend
   *  "iso" + az=35° framing used by crosssection_vectors.gif). */
  private placeIsoCam(center: THREE.Vector3, dist: number, az: number): void {
    const ca = Math.cos(az)
    const sa = Math.sin(az)
    const i3 = 1 / Math.sqrt(3)
    this.camera.position.set(
      center.x + dist * (ca * i3 - sa * i3),
      center.y + dist * (sa * i3 + ca * i3),
      center.z + dist * i3
    )
  }

  private activeBox(): THREE.Box3 | null {
    if (this.view === 'annular') {
      return this.annular
        ? new THREE.Box3().setFromObject(this.annular.shell)
        : null
    }
    return this.model ? new THREE.Box3().setFromObject(this.model.group) : null
  }

  /** Camera distance that frames the whole engine. The annular engine is a
   *  long slender tube, so its framing is driven by the axial span (like the
   *  gif, where the whole nacelle fits in frame). */
  private viewDist(box: THREE.Box3): number {
    if (this.view === 'annular') {
      const xs = box.max.x - box.min.x
      return Math.max(xs * 1.15, 6)
    }
    const size = box.getSize(new THREE.Vector3()).length()
    return Math.max(size / 2 * 2.6, 1.2)
  }

  private frameAdaptive(): void {
    const box = this.activeBox()
    if (!box) {
      this.controls.target.set(0.6, 0.1, 0)
      return
    }
    const center = box.getCenter(new THREE.Vector3())
    const dist = this.viewDist(box)
    if (this.view === 'annular') {
      this.placeIsoCam(center, dist, 0.61)
    } else {
      this.camera.position.set(
        center.x + dist * Math.sin(0.62) * Math.sin(-0.85),
        center.y + dist * Math.cos(0.62),
        center.z + dist * Math.sin(0.62) * Math.cos(-0.85)
      )
    }
    this.controls.target.copy(center)
    this.controls.update()
  }

  // ---- internals -----------------------------------------------------------
  private syncView(): void {
    const annular = this.view === 'annular'
    if (this.model) this.model.group.visible = !annular
    if (this.annular) this.annular.group.visible = annular
    this.annularLights.visible = annular
    this.scene.background = new THREE.Color(annular ? BG_ANNUAR : BG_EXTRUDED)
    this.renderer.setClearColor(annular ? BG_ANNUAR : BG_EXTRUDED, 1)
    this.syncParticles()
    this.syncGrid()
  }

  private syncParticles(): void {
    const annular = this.view === 'annular'
    this.flow?.setEnabled(this.showParticles && !annular)
    this.streaks?.setVisible(this.showParticles && annular)
  }

  private syncGrid(): void {
    this.grid.visible = this.showGrid && this.view !== 'annular'
  }

  private resize(): void {
    const w = this.container.clientWidth
    const h = this.container.clientHeight
    if (w === 0 || h === 0) return
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  private loop(): void {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    const now = performance.now()
    const dt = Math.min((now - this.last) / 1000, 0.05)
    this.last = now

    this.controls.update()
    this.updateHighlights(dt)
    this.flow?.update(dt)
    this.streaks?.update(dt)
    this.renderer.render(this.scene, this.camera)
  }

  private updateHighlights(dt: number): void {
    if (!this.model) return
    const dimAll = this.highlightId != null
    const all: RegionId[] = [...REGION_ORDER, 'strut']
    for (const id of all) {
      const mesh = this.model.regions[id]
      if (!mesh) continue
      const m = mesh.material as THREE.MeshPhongMaterial
      const target = this.highlightId === id
        ? HIGHLIGHT_OPACITY
        : dimAll
          ? DIM_BAND_OPACITY
          : BASE_BAND_OPACITY
      const cur = m.opacity
      const next = cur + (target - cur) * Math.min(1, dt * 8)
      m.opacity = next
      m.emissiveIntensity = this.highlightId === id ? 0.55 : 0.18
    }
  }

  dispose(): void {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.resizeObserver.disconnect()
    this.model?.dispose()
    this.flow?.dispose()
    this.annular?.dispose()
    this.streaks?.dispose()
    this.controls.dispose()
    this.renderer.dispose()
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement)
    }
  }
}

export { REGION_COLORS }