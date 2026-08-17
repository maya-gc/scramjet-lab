import { spawn, type ChildProcess } from 'child_process'
import { EventEmitter } from 'events'
import { existsSync } from 'fs'
import { dirname, join } from 'path'

export type BackendState = 'connecting' | 'online' | 'offline'

export interface BackendInfo {
  state: BackendState
  url: string | null
  repo: string | null
  python: string | null
  accel: { backend: string; gpu: boolean } | null
  error: string | null
}

/** Walk upward from `startDir` looking for a directory that contains both
 *  `backend/` and `configs/` (the scramjet-lab repository root). */
export function findRepoRoot(startDir: string): string | null {
  let dir = startDir
  for (let i = 0; i < 10; i++) {
    if (existsSync(join(dir, 'backend')) && existsSync(join(dir, 'configs'))) {
      return dir
    }
    const parent = dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
  return null
}

const MAX_BODY = 1 << 20

export class BackendProcess extends EventEmitter {
  private proc: ChildProcess | null = null
  private state: BackendState = 'connecting'
  private baseUrl: string | null = null
  private token: string | null = null
  private repoRoot: string | null = null
  private pythonVersion: string | null = null
  private accel: { backend: string; gpu: boolean } | null = null
  private lastError: string | null = null
  private stopping = false
  private lineBuf = ''
  private restartAttempts = 0

  getInfo(): BackendInfo {
    return {
      state: this.state,
      url: this.baseUrl,
      repo: this.repoRoot,
      python: this.pythonVersion,
      accel: this.accel,
      error: this.lastError
    }
  }

  async start(): Promise<void> {
    const repo = process.env.SCRAMJET_HOME || findRepoRoot(process.cwd())
    if (!repo) {
      this.set('offline', 'could not locate the scramjet-lab repository (set SCRAMJET_HOME)')
      return
    }
    this.repoRoot = repo
    this.set('connecting', null)
    this.spawn()
  }

  stop(): void {
    this.stopping = true
    if (this.proc && !this.proc.killed) {
      this.proc.kill()
    }
  }

  private spawn(): void {
    const proc = spawn('python', ['-m', 'backend.interfaces.server'], {
      cwd: this.repoRoot ?? undefined,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true
    })
    this.proc = proc
    this.lineBuf = ''

    proc.stdout.on('data', (chunk: Buffer) => this.onStdout(chunk.toString()))
    proc.stderr.on('data', (chunk: Buffer) => {
      const text = chunk.toString().trim()
      if (text) this.lastError = text.split('\n').slice(0, 4).join(' ')
    })
    proc.on('error', (err) => {
      this.lastError = `failed to start python server: ${err.message}`
      this.set('offline', this.lastError)
    })
    proc.on('exit', (code, signal) => {
      this.proc = null
      this.baseUrl = null
      this.token = null
      if (this.stopping) return
      this.set('offline', `backend exited (${signal ?? code ?? 'unknown'})`)
      this.scheduleRestart()
    })
  }

  private onStdout(text: string): void {
    this.lineBuf += text
    let idx: number
    while ((idx = this.lineBuf.indexOf('\n')) >= 0) {
      const line = this.lineBuf.slice(0, idx).trim()
      this.lineBuf = this.lineBuf.slice(idx + 1)
      if (line.startsWith('SCRAMJET_SERVER_URL=')) {
        this.baseUrl = line.slice('SCRAMJET_SERVER_URL='.length)
      } else if (line.startsWith('SCRAMJET_TOKEN=')) {
        this.token = line.slice('SCRAMJET_TOKEN='.length)
      }
      if (this.baseUrl && this.token && this.state !== 'online') {
        this.restartAttempts = 0
        this.set('online', null)
        this.detectPython()
      }
    }
  }

  private async detectPython(): Promise<void> {
    try {
      const env = (await this.invoke('health', {})) as {
        result?: { python?: string; accel?: { backend?: string; gpu?: boolean } }
      }
      this.pythonVersion = env?.result?.python ?? null
      const a = env?.result?.accel
      this.accel =
        a && typeof a.gpu === 'boolean'
          ? { backend: a.backend ?? 'numpy', gpu: a.gpu }
          : null
    } catch {
      this.pythonVersion = null
      this.accel = null
    }
  }

  private scheduleRestart(): void {
    if (this.stopping || this.state === 'online') return
    const delay = Math.min(15000, 1000 * 2 ** this.restartAttempts)
    this.restartAttempts += 1
    this.set('connecting', `restarting in ${Math.round(delay / 1000)}s`)
    setTimeout(() => {
      if (!this.stopping && !this.proc && this.repoRoot) this.spawn()
    }, delay)
  }

  private set(state: BackendState, error: string | null): void {
    this.state = state
    this.lastError = error ?? this.lastError
    this.emit('status', this.getInfo())
  }

  /** POST a JSON-RPC request to the backend server. Returns the response
   *  envelope `{ ok, result?, error? }` verbatim. */
  async invoke(method: string, params: unknown): Promise<unknown> {
    if (this.state !== 'online' || !this.baseUrl || !this.token) {
      throw new Error('backend is not online')
    }
    const res = await fetch(`${this.baseUrl}/rpc`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`
      },
      body: JSON.stringify({ method, params: params ?? {} }),
      signal: AbortSignal.timeout(30000)
    })
    if (!res.ok) {
      throw new Error(`backend http ${res.status}`)
    }
    const body = await res.text()
    if (body.length > MAX_BODY) {
      throw new Error('backend response too large')
    }
    return JSON.parse(body)
  }
}
