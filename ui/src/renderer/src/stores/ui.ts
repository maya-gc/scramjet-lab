import { create } from 'zustand'

export type RailTab = 'params' | 'results' | 'charts'

export type RegionId = 'inlet' | 'isolator' | 'combustor' | 'nozzle' | 'strut'

export type SceneView = 'extruded' | 'annular'

interface UIState {
  railTab: RailTab
  railOpen: boolean
  railWidth: number
  sceneView: SceneView
  showParticles: boolean
  showBands: boolean
  showGrid: boolean
  showVeins: boolean
  highlight: RegionId | null
  camFlip: number
  setRailTab: (t: RailTab) => void
  setRailOpen: (open: boolean) => void
  setRailWidth: (w: number) => void
  setSceneView: (v: SceneView) => void
  setShowParticles: (v: boolean) => void
  setShowBands: (v: boolean) => void
  setShowGrid: (v: boolean) => void
  setShowVeins: (v: boolean) => void
  setHighlight: (r: RegionId | null) => void
  flipCamera: () => void
}

export const useUIStore = create<UIState>((set) => ({
  railTab: 'params',
  railOpen: true,
  railWidth: 400,
  sceneView: 'extruded',
  showParticles: true,
  showBands: true,
  showGrid: true,
  showVeins: true,
  highlight: null,
  camFlip: 0,
  setRailTab: (railTab) => set({ railTab, railOpen: true }),
  setRailOpen: (railOpen) => set({ railOpen }),
  setRailWidth: (railWidth) => set({ railWidth: Math.max(320, Math.min(560, railWidth)) }),
  setSceneView: (sceneView) => set({ sceneView }),
  setShowParticles: (showParticles) => set({ showParticles }),
  setShowBands: (showBands) => set({ showBands }),
  setShowGrid: (showGrid) => set({ showGrid }),
  setShowVeins: (showVeins) => set({ showVeins }),
  setHighlight: (highlight) => set({ highlight }),
  flipCamera: () => set((s) => ({ camFlip: s.camFlip + 1 }))
}))