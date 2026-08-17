import * as THREE from 'three'
import { turbo } from '../lib/colormap'
import { crossingTime, makeInterpolant, type Interpolant } from './interp'
import type { Passage } from './passage'
import type { Stations } from '../lib/types'

/**
 * GPU particle rendering for both 3D flow views.
 *
 * Particle state lives entirely on the GPU: each vertex reads its per-particle
 * parameters (channel fraction / strand angle / phase) from a 1D texture and
 * integrates its own trajectory in the vertex shader (a fixed-step loop over
 * the velocity profile, also a texture). The only per-frame CPU work is
 * advancing a single `uTime` clock — no per-particle loops, no buffer uploads.
 *
 * The sim uses a recycling cycle: a particle spends `uTcross` seconds moving
 * from x=0 to x=xMax, then `mod(uTime, 1)` wraps it back to the inlet, which
 * also lets trails wrap cleanly from the nozzle to the inlet.
 */

export interface GpuDeps {
  renderer: THREE.WebGLRenderer
  camera: THREE.PerspectiveCamera
}

const PASS_RES = 512
const VEL_RES = 256
const TURBO_RES = 64

const VERT_COMMON = /* glsl */ `
uniform float uTime;
uniform float uTcross;
uniform float uScale;
uniform float uXMax;
uniform float uYMax;
uniform float uSpan;
uniform float uR0;
uniform float uVelMax;
uniform float uMaxMach;
uniform float uViewScale;
uniform float uPointSize;
uniform float uTrailDt;
uniform float uTrailSteps;
uniform sampler2D tVel;
uniform sampler2D tMach;
uniform sampler2D tPass;
uniform sampler2D tParticles;
uniform sampler2D tTurbo;

out vec3 vColor;
out float vAlpha;

const int STEPS = 64;

float velX(float x) {
  return texture(tVel, vec2(clamp(x / uXMax, 0.0, 1.0), 0.5)).r * uVelMax;
}
float machX(float x) {
  return texture(tMach, vec2(clamp(x / uXMax, 0.0, 1.0), 0.5)).r * uMaxMach;
}
float chanLo(float x) {
  return texture(tPass, vec2(clamp(x / uXMax, 0.0, 1.0), 0.5)).r * uYMax;
}
float chanHi(float x) {
  return texture(tPass, vec2(clamp(x / uXMax, 0.0, 1.0), 0.5)).g * uYMax;
}

float posOf(float t) {
  float x = 0.0;
  float dt = t / float(STEPS);
  for (int i = 0; i < STEPS; i++) {
    x += max(velX(x), 1.0) * uScale * uTcross * dt;
  }
  return min(x, uXMax);
}

vec3 turboColor(float m) {
  float t = clamp(m / uMaxMach, 0.0, 1.0);
  return texture(tTurbo, vec2(t, 0.5)).rgb;
}
`

const VERT_POINT = /* glsl */ `
${VERT_COMMON}
void main() {
  vec4 pp = texelFetch(tParticles, ivec2(gl_VertexID, 0), 0);
  float frac = pp.r;
  float seed = pp.g;
  float phase = pp.a;
  float tEff = mod(uTime + phase, 1.0);
  float x = posOf(tEff);
  float y = chanLo(x) + frac * (chanHi(x) - chanLo(x));
  float z = (seed * 2.0 - 1.0) * uSpan * 0.5;
  vec3 world = vec3(x, y, z);
  vec4 mv = modelViewMatrix * vec4(world, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uPointSize * uViewScale / max(-mv.z, 0.01);
  float m = machX(x);
  float t = clamp((m - 1.0) / max(uMaxMach - 1.0, 1e-3), 0.0, 1.0) * 0.92;
  vColor = texture(tTurbo, vec2(t, 0.5)).rgb;
  vAlpha = 0.85;
}
`

const VERT_LINES = /* glsl */ `
${VERT_COMMON}
void main() {
  int stride = int(uTrailSteps - 1.0) * 2;
  int pid = gl_VertexID / stride;
  int seg = gl_VertexID - pid * stride;
  int k = (seg >> 1) + (seg & 1);
  vec4 pp = texelFetch(tParticles, ivec2(pid, 0), 0);
  float frac = pp.r;
  float theta = pp.g * 6.28318530718;
  float phase = pp.a;
  float tEff = mod(uTime + phase, 1.0);
  float tk = mod(tEff - float(k) * uTrailDt, 1.0);
  float x = posOf(tk);
  float y = chanLo(x) + frac * (chanHi(x) - chanLo(x));
  float rr = uR0 + y;
  vec3 world = vec3(x, rr * cos(theta), rr * sin(theta));
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
  vColor = turboColor(machX(x));
  vAlpha = 0.95;
}
`

const VERT_HEADS = /* glsl */ `
${VERT_COMMON}
void main() {
  vec4 pp = texelFetch(tParticles, ivec2(gl_VertexID, 0), 0);
  float frac = pp.r;
  float theta = pp.g * 6.28318530718;
  float phase = pp.a;
  float tEff = mod(uTime + phase, 1.0);
  float x = posOf(tEff);
  float y = chanLo(x) + frac * (chanHi(x) - chanLo(x));
  float rr = uR0 + y;
  vec3 world = vec3(x, rr * cos(theta), rr * sin(theta));
  vec4 mv = modelViewMatrix * vec4(world, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uPointSize * uViewScale / max(-mv.z, 0.01);
  vColor = turboColor(machX(x));
  vAlpha = 1.0;
}
`

const FRAG_SPRITE = /* glsl */ `
in vec3 vColor;
in float vAlpha;
out vec4 fragColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.3, d) * vAlpha;
  if (a < 0.02) discard;
  fragColor = vec4(vColor, a);
}
`

const FRAG_LINE = /* glsl */ `
in vec3 vColor;
in float vAlpha;
out vec4 fragColor;
void main() {
  fragColor = vec4(vColor, vAlpha);
}
`

function makeDataTex(
  data: Uint8Array,
  width: number,
  format: THREE.PixelFormat
): THREE.DataTexture {
  const buf = new Uint8Array(data.length)
  buf.set(data)
  const t = new THREE.DataTexture(buf, width, 1, format, THREE.UnsignedByteType)
  t.minFilter = THREE.NearestFilter
  t.magFilter = THREE.NearestFilter
  t.wrapS = THREE.ClampToEdgeWrapping
  t.wrapT = THREE.ClampToEdgeWrapping
  t.needsUpdate = true
  return t
}

function bakePassage(passage: Passage, xMax: number): THREE.DataTexture {
  const data = new Uint8Array(PASS_RES * 2)
  const yMax = Math.max(passage.yMax, 1e-3)
  for (let i = 0; i < PASS_RES; i++) {
    const x = (xMax * i) / (PASS_RES - 1)
    const [lo, hi] = passage.sampleY(x)
    data[i * 2] = Math.max(0, Math.min(255, Math.round((lo / yMax) * 255)))
    data[i * 2 + 1] = Math.max(0, Math.min(255, Math.round((hi / yMax) * 255)))
  }
  return makeDataTex(data, PASS_RES, THREE.RGFormat)
}

function bakeVelMach(
  vel: Interpolant,
  mach: Interpolant,
  xMax: number,
  maxMach: number
): { velTex: THREE.DataTexture; machTex: THREE.DataTexture; velMax: number } {
  const vData = new Uint8Array(VEL_RES)
  const mData = new Uint8Array(VEL_RES)
  let velMax = 1
  for (let i = 0; i < VEL_RES; i++) {
    const x = (xMax * i) / (VEL_RES - 1)
    velMax = Math.max(velMax, Math.max(vel.eval(x), 1))
  }
  for (let i = 0; i < VEL_RES; i++) {
    const x = (xMax * i) / (VEL_RES - 1)
    vData[i] = Math.max(0, Math.min(255, Math.round((Math.max(vel.eval(x), 1) / velMax) * 255)))
    const m = mach.eval(x)
    mData[i] = Math.max(0, Math.min(255, Math.round((Math.max(m, 0) / maxMach) * 255)))
  }
  return {
    velTex: makeDataTex(vData, VEL_RES, THREE.RedFormat),
    machTex: makeDataTex(mData, VEL_RES, THREE.RedFormat),
    velMax
  }
}

function bakeParticles(
  count: number,
  fn: (i: number) => [number, number, number, number]
): THREE.DataTexture {
  const data = new Uint8Array(count * 4)
  for (let i = 0; i < count; i++) {
    const [a, b, c, d] = fn(i)
    data[i * 4] = Math.max(0, Math.min(255, Math.round(a * 255)))
    data[i * 4 + 1] = Math.max(0, Math.min(255, Math.round(b * 255)))
    data[i * 4 + 2] = Math.max(0, Math.min(255, Math.round(c * 255)))
    data[i * 4 + 3] = Math.max(0, Math.min(255, Math.round(d * 255)))
  }
  return makeDataTex(data, count, THREE.RGBAFormat)
}

function bakeTurbo(): THREE.DataTexture {
  const data = new Uint8Array(TURBO_RES * 4)
  for (let i = 0; i < TURBO_RES; i++) {
    const [r, g, b] = turbo(i / (TURBO_RES - 1))
    data[i * 4] = Math.round(r * 255)
    data[i * 4 + 1] = Math.round(g * 255)
    data[i * 4 + 2] = Math.round(b * 255)
    data[i * 4 + 3] = 255
  }
  return makeDataTex(data, TURBO_RES, THREE.RGBAFormat)
}

function viewScale(deps: GpuDeps): number {
  const h = deps.renderer.domElement.height || 1
  return h / (2 * Math.tan((deps.camera.fov * Math.PI) / 360))
}

function buildInterpolants(
  stations: Stations | null,
  fallbackVx: number
): { vel: Interpolant; mach: Interpolant } {
  const xs: number[] = []
  const vs: number[] = []
  const ms: number[] = []
  if (stations) {
    for (const s of Object.values(stations)) {
      if (s && s.x != null && Number.isFinite(s.M_massavg)) {
        xs.push(s.x)
        vs.push(s.Vx_massavg || 0)
        ms.push(s.M_massavg)
      }
    }
  }
  if (xs.length === 0) {
    const m0 = fallbackVx > 0 ? fallbackVx / 340 : 0
    return {
      vel: makeInterpolant([0, 1], [fallbackVx, fallbackVx]),
      mach: makeInterpolant([0, 1], [m0, m0])
    }
  }
  const sorted = xs.map((x, i) => ({ x, v: vs[i], m: ms[i] })).sort((a, b) => a.x - b.x)
  return {
    vel: makeInterpolant(sorted.map((s) => s.x), sorted.map((s) => s.v)),
    mach: makeInterpolant(sorted.map((s) => s.x), sorted.map((s) => s.m))
  }
}

// ---- extruded duct flow (point sprites) -----------------------------------

export class GpuFlowPoints {
  readonly points: THREE.Points
  private geometry: THREE.BufferGeometry
  private material: THREE.ShaderMaterial
  private vel: Interpolant
  private mach: Interpolant
  private maxMach = 4
  private enabled = true
  private simTime = 0
  private deps: GpuDeps
  private xMax: number
  private scale: number
  private tcross = 1
  private velTex: THREE.DataTexture | null = null
  private machTex: THREE.DataTexture | null = null

  constructor(passage: Passage, scale: number, deps: GpuDeps) {
    this.deps = deps
    this.xMax = passage.xMax
    this.scale = scale
    this.vel = makeInterpolant([0, 1], [0, 0])
    this.mach = makeInterpolant([0, 1], [0, 0])

    const count = 16000
    const uniforms: Record<string, THREE.IUniform> = {
      uTime: { value: 0 },
      uTcross: { value: 1 },
      uScale: { value: scale },
      uXMax: { value: passage.xMax },
      uYMax: { value: passage.yMax },
      uSpan: { value: passage.span },
      uR0: { value: 0 },
      uVelMax: { value: 1 },
      uMaxMach: { value: this.maxMach },
      uViewScale: { value: 900 },
      uPointSize: { value: 0.08 },
      uTrailDt: { value: 0 },
      uTrailSteps: { value: 1 },
      tVel: { value: null },
      tMach: { value: null },
      tPass: { value: bakePassage(passage, passage.xMax) },
      tParticles: {
        value: bakeParticles(count, () => [
          Math.random(),
          Math.random(),
          Math.random(),
          Math.random()
        ])
      },
      tTurbo: { value: bakeTurbo() }
    }
    this.material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader: VERT_POINT,
      fragmentShader: FRAG_SPRITE,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      glslVersion: THREE.GLSL3
    })
    this.geometry = new THREE.BufferGeometry()
    this.geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(count * 3), 3)
    )
    this.points = new THREE.Points(this.geometry, this.material)
    this.points.frustumCulled = false
    this.points.renderOrder = 2
  }

  setState(stations: Stations | null, fallbackVx: number, maxMachOverride?: number): void {
    const { vel, mach } = buildInterpolants(stations, fallbackVx)
    this.vel = vel
    this.mach = mach
    this.maxMach = maxMachOverride ?? this.machMaxSeen()
    this.rebake()
  }

  private machMaxSeen(): number {
    let m = 4
    for (const v of this.mach.y) m = Math.max(m, v)
    return Math.max(1.6, m)
  }

  private rebake(): void {
    const { velTex, machTex, velMax } = bakeVelMach(this.vel, this.mach, this.xMax, this.maxMach)
    this.velTex?.dispose()
    this.machTex?.dispose()
    this.velTex = velTex
    this.machTex = machTex
    this.tcross = crossingTime(this.vel, this.xMax, this.scale)
    const u = this.material.uniforms
    u.tVel.value = velTex
    u.tMach.value = machTex
    u.uVelMax.value = velMax
    u.uMaxMach.value = this.maxMach
    u.uTcross.value = this.tcross
  }

  setEnabled(on: boolean): void {
    this.enabled = on
    this.points.visible = on
  }

  update(dt: number): void {
    if (!this.enabled) return
    this.simTime += dt
    const u = this.material.uniforms
    u.uTime.value = this.simTime % 1
    u.uViewScale.value = viewScale(this.deps)
  }

  dispose(): void {
    this.geometry.dispose()
    this.material.dispose()
    this.velTex?.dispose()
    this.machTex?.dispose()
    ;(this.material.uniforms.tPass.value as THREE.DataTexture)?.dispose()
    ;(this.material.uniforms.tParticles.value as THREE.DataTexture)?.dispose()
    ;(this.material.uniforms.tTurbo.value as THREE.DataTexture)?.dispose()
  }
}

// ---- annular streaks (comet trails generated on the GPU) -------------------

export interface GpuStreaksOptions {
  strands?: number
  history?: number
  perStrand?: number
  trailCycle?: number
}

export class GpuStreaks {
  readonly lines: THREE.LineSegments
  readonly heads: THREE.Points
  private linesGeo: THREE.BufferGeometry
  private headsGeo: THREE.BufferGeometry
  private linesMat: THREE.ShaderMaterial
  private headsMat: THREE.ShaderMaterial
  private vel: Interpolant
  private mach: Interpolant
  private maxMach = 4
  private enabled = true
  private simTime = 0
  private deps: GpuDeps
  private xMax: number
  private scale: number
  private tcross = 1
  private velTex: THREE.DataTexture | null = null
  private machTex: THREE.DataTexture | null = null

  readonly history: number

  constructor(passage: Passage, scale: number, deps: GpuDeps, opts: GpuStreaksOptions = {}) {
    const strands = opts.strands ?? 9
    const history = opts.history ?? 96
    const perStrand = opts.perStrand ?? 52
    const trailCycle = opts.trailCycle ?? 0.25
    this.history = history
    const count = strands * perStrand

    this.deps = deps
    this.xMax = passage.xMax
    this.scale = scale
    this.vel = makeInterpolant([0, 1], [0, 0])
    this.mach = makeInterpolant([0, 1], [0, 0])

    const particles = bakeParticles(count, (i) => {
      const theta = (2 * Math.PI * (i % strands)) / strands / (2 * Math.PI)
      return [Math.random(), theta, Math.random(), Math.random()]
    })
    const passTex = bakePassage(passage, passage.xMax)
    const turboTex = bakeTurbo()

    const makeUniforms = (): Record<string, THREE.IUniform> => ({
      uTime: { value: 0 },
      uTcross: { value: 1 },
      uScale: { value: scale },
      uXMax: { value: passage.xMax },
      uYMax: { value: passage.yMax },
      uSpan: { value: passage.span },
      uR0: { value: 0.05 },
      uVelMax: { value: 1 },
      uMaxMach: { value: this.maxMach },
      uViewScale: { value: 900 },
      uPointSize: { value: 0.1 },
      uTrailDt: { value: trailCycle / history },
      uTrailSteps: { value: history },
      tVel: { value: null },
      tMach: { value: null },
      tPass: { value: passTex },
      tParticles: { value: particles },
      tTurbo: { value: turboTex }
    })

    const lineCount = count * (history - 1) * 2
    this.linesMat = new THREE.ShaderMaterial({
      uniforms: makeUniforms(),
      vertexShader: VERT_LINES,
      fragmentShader: FRAG_LINE,
      transparent: true,
      depthWrite: false,
      glslVersion: THREE.GLSL3
    })
    this.linesGeo = new THREE.BufferGeometry()
    this.linesGeo.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(lineCount * 3), 3)
    )
    this.lines = new THREE.LineSegments(this.linesGeo, this.linesMat)
    this.lines.frustumCulled = false
    this.lines.renderOrder = 2

    this.headsMat = new THREE.ShaderMaterial({
      uniforms: makeUniforms(),
      vertexShader: VERT_HEADS,
      fragmentShader: FRAG_SPRITE,
      transparent: true,
      depthWrite: false,
      glslVersion: THREE.GLSL3
    })
    this.headsGeo = new THREE.BufferGeometry()
    this.headsGeo.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(count * 3), 3)
    )
    this.heads = new THREE.Points(this.headsGeo, this.headsMat)
    this.heads.frustumCulled = false
    this.heads.renderOrder = 2

    this._sharedTex = { pass: passTex, particles, turbo: turboTex }
  }

  private _sharedTex!: { pass: THREE.DataTexture; particles: THREE.DataTexture; turbo: THREE.DataTexture }

  setState(stations: Stations | null, fallbackVx: number, maxMachOverride?: number): void {
    const { vel, mach } = buildInterpolants(stations, fallbackVx)
    this.vel = vel
    this.mach = mach
    let m = 4
    for (const v of this.mach.y) m = Math.max(m, v)
    this.maxMach = maxMachOverride ?? Math.max(1.6, m)
    const { velTex, machTex, velMax } = bakeVelMach(this.vel, this.mach, this.xMax, this.maxMach)
    this.velTex?.dispose()
    this.machTex?.dispose()
    this.velTex = velTex
    this.machTex = machTex
    this.tcross = crossingTime(this.vel, this.xMax, this.scale)
    const uL = this.linesMat.uniforms
    const uH = this.headsMat.uniforms
    for (const u of [uL, uH]) {
      u.tVel.value = velTex
      u.tMach.value = machTex
      u.uVelMax.value = velMax
      u.uMaxMach.value = this.maxMach
      u.uTcross.value = this.tcross
    }
  }

  setVisible(on: boolean): void {
    this.enabled = on
    this.lines.visible = on
    this.heads.visible = on
  }

  update(dt: number): void {
    if (!this.enabled) return
    this.simTime += dt
    const t = this.simTime % 1
    const vs = viewScale(this.deps)
    this.linesMat.uniforms.uTime.value = t
    this.linesMat.uniforms.uViewScale.value = vs
    this.headsMat.uniforms.uTime.value = t
    this.headsMat.uniforms.uViewScale.value = vs
  }

  dispose(): void {
    this.linesGeo.dispose()
    this.headsGeo.dispose()
    this.linesMat.dispose()
    this.headsMat.dispose()
    this.velTex?.dispose()
    this.machTex?.dispose()
    this._sharedTex.pass.dispose()
    this._sharedTex.particles.dispose()
    this._sharedTex.turbo.dispose()
  }
}
