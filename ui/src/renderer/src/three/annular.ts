import * as THREE from 'three'
import { GpuStreaks, type GpuDeps } from './gpu'
import type { GeometryPayload, Stations } from '../lib/types'
import { passageFromGeo, type Passage } from './passage'

/** Nacelle inner offset (m) — the annular duct sits on this radius. Same R0
 *  used by ``backend/infrastructure/viz.py`` to revolve the channel into the
 *  axisymmetric engine shown in crosssection_vectors.gif. */
export const ANNUAR_R0 = 0.05

const RES = 56
const NOSE_X0 = -0.15

export interface AnnularEngine {
  group: THREE.Group
  /** Static shell + rings only (used to frame the camera). */
  shell: THREE.Group
  dispose: () => void
}

interface Handles {
  geo: THREE.BufferGeometry
  mat: THREE.Material
}

function latheShell(
  profile: Array<[number, number]>,
  color: number,
  opacity: number,
  out: Handles[]
): THREE.Mesh {
  // LatheGeometry revolves Vector2(x=radius, y=height) around its Y axis;
  // profile here is (axial, radius), so swap to (radius, axial).
  const pts = profile.map(([x, r]) => new THREE.Vector2(Math.max(r, 1e-4), x))
  const geo = new THREE.LatheGeometry(pts, RES)
  const mat = new THREE.MeshPhongMaterial({
    color,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    depthWrite: false,
    shininess: 50
  })
  const mesh = new THREE.Mesh(geo, mat)
  // Rotate so the lathe's symmetry axis (originally +Y) aligns with engine X.
  mesh.rotation.z = -Math.PI / 2
  out.push({ geo, mat })
  return mesh
}

function ringMesh(
  x: number,
  radius: number,
  tube: number,
  color: number,
  opacity: number,
  out: Handles[]
): THREE.Mesh {
  const geo = new THREE.TorusGeometry(radius, tube, 12, RES)
  const mat = new THREE.MeshPhongMaterial({
    color,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    shininess: 60
  })
  const mesh = new THREE.Mesh(geo, mat)
  mesh.rotation.y = Math.PI / 2
  mesh.position.set(x, 0, 0)
  out.push({ geo, mat })
  return mesh
}

export function buildAnnularEngine(geo: GeometryPayload): AnnularEngine {
  const passage = passageFromGeo(geo)
  const group = new THREE.Group()
  const shell = new THREE.Group()
  const handles: Handles[] = []
  const lower = passage.lower
  const upper = passage.upper

  // ---- cowl shell (revolved upper wall) -----------------------------------
  const cowl: Array<[number, number]> = upper.map((p) => [p[0], p[1] + ANNUAR_R0])
  shell.add(latheShell(cowl, 0xc8d4de, 0.42, handles))

  // ---- centerbody shell: nose spike (0 -> R0) + revolved lower wall -------
  const cb: Array<[number, number]> = []
  const NSP = 24
  for (let i = 0; i < NSP; i++) {
    const t = i / (NSP - 1)
    cb.push([NOSE_X0 + (0 - NOSE_X0) * t, ANNUAR_R0 * Math.pow(t, 1.75)])
  }
  for (const p of lower) cb.push([p[0], p[1] + ANNUAR_R0])
  shell.add(latheShell(cb, 0xc8d4de, 0.42, handles))

  // ---- nozzle plug + rim ----------------------------------------------------
  const xL = lower[lower.length - 1][0]
  const r0plug = lower[lower.length - 1][1] + ANNUAR_R0
  const plug: Array<[number, number]> = []
  for (let i = 0; i < 24; i++) {
    const t = i / 23
    const xs = xL + 0.004 + t * 0.26
    plug.push([xs, Math.max(r0plug * (1 - Math.pow(t, 1.6)), 0)])
  }
  shell.add(latheShell(plug, 0xaeb9c4, 0.38, handles))
  shell.add(
    ringMesh(xL - 0.02, upper[upper.length - 1][1] + ANNUAR_R0 + 0.02, 0.016, 0xaeb9c4, 0.5, handles)
  )

  // ---- marker rings (same x positions the gif uses, from derived keys) -----
  const d = geo.derived
  const ringX = (x: number): number => interp(upper, x, upper[upper.length - 1][1]) + ANNUAR_R0
  const ringLo = (x: number): number => interp(lower, x, lower[lower.length - 1][1]) + ANNUAR_R0
  shell.add(ringMesh(d.x_inlet_end, ringX(d.x_inlet_end), 0.011, 0xaeb9c4, 0.45, handles))
  shell.add(ringMesh(d.x_strut, ringLo(d.x_strut) - 0.003, 0.013, 0xaeb9c4, 0.45, handles))
  shell.add(ringMesh(d.x_combustor_end, ringX(d.x_combustor_end), 0.011, 0xaeb9c4, 0.45, handles))

  // ---- red inlet ring -------------------------------------------------------
  shell.add(ringMesh(0, upper[0][1] + ANNUAR_R0, 0.014, 0xe63946, 1, handles))

  group.add(shell)

  return {
    group,
    shell,
    dispose: () => {
      for (const h of handles) {
        h.geo.dispose()
        h.mat.dispose()
      }
    }
  }
}

function interp(poly: number[][], x: number, fallback: number): number {
  if (poly.length === 0) return fallback
  if (x <= poly[0][0]) return poly[0][1]
  const last = poly[poly.length - 1]
  if (x >= last[0]) return last[1]
  for (let i = 0; i < poly.length - 1; i++) {
    const a = poly[i]
    const b = poly[i + 1]
    if (x >= a[0] && x <= b[0]) {
      const f = b[0] - a[0] > 1e-12 ? (x - a[0]) / (b[0] - a[0]) : 0
      return a[1] + (b[1] - a[1]) * f
    }
  }
  return fallback
}

/** Annular comet streaks simulated on the GPU (trails generated in the vertex
 *  shader by backward integration, wrapping nozzle->inlet). See GpuStreaks. */
export class VectorStreaks {
  readonly lines: THREE.LineSegments
  readonly heads: THREE.Points
  readonly history: number
  private g: GpuStreaks

  constructor(passage: Passage, deps: GpuDeps) {
    this.g = new GpuStreaks(passage, 5, deps)
    this.lines = this.g.lines
    this.heads = this.g.heads
    this.history = this.g.history
  }

  setState(stations: Stations | null, fallbackVx: number, maxMachOverride?: number): void {
    this.g.setState(stations, fallbackVx, maxMachOverride)
  }

  setVisible(on: boolean): void {
    this.g.setVisible(on)
  }

  update(dt: number): void {
    this.g.update(dt)
  }

  dispose(): void {
    this.g.dispose()
  }
}
