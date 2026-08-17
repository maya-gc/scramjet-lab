import * as THREE from 'three'
import { GpuFlowPoints, type GpuDeps } from './gpu'
import type { Passage } from './passage'
import type { Stations } from '../lib/types'

/** Extruded-duct flow particles, fully simulated on the GPU (16k particles,
 *  no per-frame CPU work). See GpuFlowPoints. */
export class FlowField {
  readonly points: THREE.Points
  private g: GpuFlowPoints

  constructor(passage: Passage, speedScale: number, deps: GpuDeps) {
    this.g = new GpuFlowPoints(passage, speedScale, deps)
    this.points = this.g.points
  }

  setState(stations: Stations | null, fallbackVx: number, maxMachOverride?: number): void {
    this.g.setState(stations, fallbackVx, maxMachOverride)
  }

  setEnabled(on: boolean): void {
    this.g.setEnabled(on)
  }

  update(dt: number): void {
    this.g.update(dt)
  }

  dispose(): void {
    this.g.dispose()
  }
}
