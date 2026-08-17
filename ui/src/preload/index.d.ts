import type { BackendInfoPayload } from './index'

declare global {
  interface Window {
    scramjet: {
      info(): Promise<BackendInfoPayload>
      invoke(method: string, params?: Record<string, unknown>): Promise<unknown>
      onBackendStatus(cb: (info: BackendInfoPayload) => void): () => void
    }
  }
}

export {}