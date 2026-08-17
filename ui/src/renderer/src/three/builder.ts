import * as THREE from 'three'
import type { GeometryPayload } from '../lib/types'
import type { RegionId } from '../stores/ui'
import { passageFromGeo, type Passage } from './passage'

export const REGION_COLORS: Record<RegionId, string> = {
  inlet: '#38bdf8',
  isolator: '#818cf8',
  combustor: '#fb923c',
  nozzle: '#34d399',
  strut: '#f43f5e'
}

export const REGION_ORDER: RegionId[] = [
  'inlet',
  'isolator',
  'combustor',
  'nozzle'
]

export interface RegionTable {
  group: THREE.Group
  regions: Record<RegionId, THREE.Mesh | undefined>
  strutMesh: THREE.Mesh | null
  dispose: () => void
}

function scaledSamples(
  passage: Passage,
  x0: number,
  x1: number,
  n: number
): number[][] {
  const out: number[][] = []
  for (let i = 0; i < n; i++) {
    const x = x0 + ((x1 - x0) * i) / (n - 1)
    const [yl, yu] = passage.sampleY(x)
    out.push([x, yl, yu])
  }
  return out
}

function shapeFromPlanks(planks: number[][]): THREE.Shape {
  const shape = new THREE.Shape()
  const n = planks.length
  shape.moveTo(planks[0][0], planks[0][1])
  for (let i = 1; i < n; i++) shape.lineTo(planks[i][0], planks[i][1])
  for (let i = n - 1; i >= 0; i--) shape.lineTo(planks[i][0], planks[i][2])
  shape.closePath()
  return shape
}

function extrudeMesh(shape: THREE.Shape, depth: number, material: THREE.Material): THREE.Mesh {
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: false
  })
  const mesh = new THREE.Mesh(geo, material)
  mesh.position.z = -depth / 2
  return mesh
}

export function buildEngine(geo: GeometryPayload): RegionTable {
  const passage = passageFromGeo(geo)
  const group = new THREE.Group()
  const disposables: Array<THREE.BufferGeometry | THREE.Material> = []
  const material = <T extends THREE.Material>(m: T): T => {
    disposables.push(m)
    return m
  }
  const geometry = <T extends THREE.BufferGeometry>(g: T): T => {
    disposables.push(g)
    return g
  }

  const depth = passage.span

  // ---- glass duct shell ---------------------------------------------------
  const shellPoints: THREE.Vector2[] = []
  for (const p of passage.lower) shellPoints.push(new THREE.Vector2(p[0], p[1]))
  for (let i = passage.upper.length - 1; i >= 0; i--) {
    const p = passage.upper[i]
    shellPoints.push(new THREE.Vector2(p[0], p[1]))
  }
  const shellShape = new THREE.Shape(shellPoints)
  const shellMat = material(
    new THREE.MeshPhongMaterial({
      color: 0x141a22,
      transparent: true,
      opacity: 0.2,
      side: THREE.DoubleSide,
      depthWrite: false,
      emissive: 0x0a1017,
      emissiveIntensity: 0.6,
      shininess: 90
    })
  )
  const shell = extrudeMesh(shellShape, depth, shellMat)
  group.add(shell)

  // ---- region bands --------------------------------------------------------
  const regions: Record<RegionId, THREE.Mesh | undefined> = {
    inlet: undefined,
    isolator: undefined,
    combustor: undefined,
    nozzle: undefined,
    strut: undefined
  }
  const d = geo.derived
  const bounds = [
    [0, d.x_inlet_end],
    [d.x_inlet_end, d.x_isolator_end],
    [d.x_isolator_end, d.x_combustor_end],
    [d.x_combustor_end, d.x_total]
  ]
  bounds.forEach(([x0, x1], i) => {
    const id = REGION_ORDER[i]
    const planks = scaledSamples(passage, x0, x1, 26)
    const shape = shapeFromPlanks(planks)
    const mat = material(
      new THREE.MeshPhongMaterial({
        color: REGION_COLORS[id],
        transparent: true,
        opacity: 0.16,
        side: THREE.DoubleSide,
        depthWrite: false,
        emissive: new THREE.Color(REGION_COLORS[id]),
        emissiveIntensity: 0.25
      })
    )
    regions[id] = extrudeMesh(shape, depth, mat)
    group.add(regions[id] as THREE.Mesh)
  })

  // ---- strut ---------------------------------------------------------------
  if (passage.strut) {
    const pts: THREE.Vector2[] = passage.strut.map((p) => new THREE.Vector2(p[0], p[1]))
    const sp = new THREE.Shape(pts)
    const matv = material(
      new THREE.MeshPhongMaterial({
        color: 0xf43f5e,
        transparent: true,
        opacity: 0.4,
        side: THREE.DoubleSide,
        emissive: 0x7f1d2d,
        emissiveIntensity: 0.5
      })
    )
    regions.strut = extrudeMesh(sp, depth, matv)
    group.add(regions.strut)
  }

  // ---- edge lines ----------------------------------------------------------
  const lineMat = (color: number, opacity: number): THREE.LineBasicMaterial =>
    material(new THREE.LineBasicMaterial({ color, transparent: true, opacity }))

  const edgePoints = (pts: number[][]): THREE.Vector3[] =>
    pts.map((p) => new THREE.Vector3(p[0], p[1], 0))

  const body = geometry(
    new THREE.BufferGeometry().setFromPoints(edgePoints(passage.lower))
  )
  const bodyLine = new THREE.Line(body, lineMat(0x7dd3fc, 0.9))
  group.add(bodyLine)

  const cowl = geometry(
    new THREE.BufferGeometry().setFromPoints(edgePoints(passage.upper))
  )
  const cowlLine = new THREE.Line(cowl, lineMat(0x94a3b8, 0.7))
  group.add(cowlLine)

  if (passage.strut) {
    const sp = geometry(
      new THREE.BufferGeometry().setFromPoints(edgePoints(passage.strut))
    )
    group.add(new THREE.Line(sp, lineMat(0xfda4af, 0.85)))
  }

  // ---- station slice planes ------------------------------------------------
  for (let i = 0; i < 6; i++) {
    const frac = i / 5
    const x = frac * passage.xMax
    const [yl, yu] = passage.sampleY(x)
    if (yu - yl < 1e-4) continue
    const plane = new THREE.Mesh(
      geometry(new THREE.PlaneGeometry(depth, yu - yl)),
      material(
        new THREE.MeshBasicMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.06,
          side: THREE.DoubleSide,
          depthWrite: false
        })
      )
    )
    plane.rotation.y = Math.PI / 2
    plane.position.set(x, (yl + yu) / 2, 0)
    group.add(plane)
  }

  // ---- freestream arrow -----------------------------------------------------
  const arrow = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(-0.25, (passage.yMax + passage.upperY(0)) / 2, 0),
    passage.yMax * 0.22,
    0x22d3ee,
    0.12 * passage.yMax,
    0.06 * passage.yMax
  )
  group.add(arrow)

  return {
    group,
    regions,
    strutMesh: regions.strut ?? null,
    dispose: () => {
      for (const g of disposables) g.dispose()
      group.traverse((obj) => {
        const m = obj as THREE.Mesh
        if (m.isMesh && m.geometry) m.geometry.dispose()
      })
    }
  }
}