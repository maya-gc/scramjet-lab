import { PanelRightClose } from 'lucide-react'
import { useUIStore } from '../stores/ui'
import { useSimStore } from '../stores/sim'
import { IconButton } from './ui/Button'
import { ParamsPanel } from './ParamsPanel'
import { ResultsPanel } from './ResultsPanel'
import { ChartsPanel } from './ChartsPanel'

const TABS = [
  { value: 'params', label: 'Parameters' },
  { value: 'results', label: 'Results' },
  { value: 'charts', label: 'Charts' }
] as const

export function RightRail(): React.JSX.Element {
  const railTab = useUIStore((s) => s.railTab)
  const setRailTab = useUIStore((s) => s.setRailTab)
  const setRailOpen = useUIStore((s) => s.setRailOpen)
  const hasMetrics = useSimStore((s) => s.metrics != null)

  return (
    <div className="rail-inner">
      <div className="rail-bar">
        <div className="rail-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.value}
              role="tab"
              aria-selected={railTab === t.value}
              className={railTab === t.value ? 'rail-tab rail-tab-active' : 'rail-tab'}
              onClick={() => setRailTab(t.value)}
            >
              {t.label}
              {t.value === 'results' && hasMetrics && <span className="rail-tab-dot" />}
            </button>
          ))}
        </div>
        <IconButton size="sm" onClick={() => setRailOpen(false)} title="Collapse panel">
          <PanelRightClose size={15} />
        </IconButton>
      </div>
      <div className="rail-content">
        {railTab === 'params' && <ParamsPanel />}
        {railTab === 'results' && <ResultsPanel />}
        {railTab === 'charts' && <ChartsPanel />}
      </div>
    </div>
  )
}