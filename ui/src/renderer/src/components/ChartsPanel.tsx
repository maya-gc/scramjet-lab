import { TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'
import { useSimStore } from '../stores/sim'
import { Segmented } from './ui/Segmented'
import { axialProfile, combustorRange } from '../lib/axial'
import { fmt, fmtK } from '../lib/format'

type Variable = 'M' | 'p' | 'T' | 'p0' | 'velocity'

const VARIABLES: Array<{ value: Variable; label: string }> = [
  { value: 'M', label: 'Mach' },
  { value: 'p', label: 'Pressure' },
  { value: 'T', label: 'Temperature' },
  { value: 'p0', label: 'Stagnation' },
  { value: 'velocity', label: 'Velocity' }
]

export function ChartsPanel(): React.JSX.Element {
  const stations = useSimStore((s) => s.stations)
  const geometry = useSimStore((s) => s.geometry)
  const [variable, setVariable] = useState<Variable>('M')

  const data = useMemo(() => (stations ? axialProfile(stations) : []), [stations])
  const combustor = useMemo(
    () => combustorRange(geometry?.derived) ?? undefined,
    [geometry]
  )

  if (data.length === 0) {
    return (
      <div className="empty-rail">
        <TrendingUp size={20} />
        <span>station data appears after a full solver run</span>
      </div>
    )
  }

  const yKey: Record<Variable, string> = {
    M: 'M',
    p: 'p',
    T: 'T',
    p0: 'p0',
    velocity: 'velocity'
  }
  const yLabel: Record<Variable, string> = {
    M: 'Mach',
    p: 'Static pressure [Pa]',
    T: 'Temperature [K]',
    p0: 'Stagnation pressure [Pa]',
    velocity: 'Axial velocity [m/s]'
  }
  const yFmt: Record<Variable, (v: unknown) => string> = {
    M: (v) => fmt(Number(v), 2),
    p: (v) => fmtK(Number(v), 0),
    T: (v) => fmt(Number(v), 0),
    p0: (v) => fmtK(Number(v), 0),
    velocity: (v) => fmt(Number(v), 0)
  }

  return (
    <div className="charts">
      <div className="charts-toolbar">
        <Segmented
          value={variable}
          onChange={setVariable}
          options={VARIABLES}
          size="sm"
        />
      </div>

      <div className="chart-box">
        <ResponsiveContainer width="100%" height={280} minWidth={0} minHeight={0}>
          <LineChart data={data} margin={{ top: 12, right: 14, bottom: 2, left: 2 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="x"
              tick={{ fill: '#71717a', fontSize: 10.5 }}
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)} cm`}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
              label={{ value: 'axial position', position: 'insideBottom', offset: -2, fill: '#71717a', fontSize: 10.5 }}
            />
            <YAxis
              tick={{ fill: '#71717a', fontSize: 10.5 }}
              tickFormatter={yFmt[variable]}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
              width={64}
            />
            <Tooltip
              contentStyle={{
                background: '#17171b',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 8,
                fontSize: 11.5
              }}
              labelFormatter={(l) => `x = ${(Number(l) * 100).toFixed(1)} cm`}
              formatter={(value: number, _name: string) => [
                yFmt[variable](value),
                yLabel[variable]
              ]}
            />
            {combustor && (
              <ReferenceArea
                x1={combustor.start}
                x2={combustor.end}
                fill="rgba(34,211,238,0.06)"
                stroke="rgba(34,211,238,0.25)"
                strokeDasharray="2 4"
              />
            )}
            <Line
              type="monotone"
              dataKey={yKey[variable]}
              stroke="#22d3ee"
              strokeWidth={2.2}
              dot={{ r: 3.5, fill: '#22d3ee', strokeWidth: 0 }}
              activeDot={{ r: 5.5, fill: '#22d3ee', stroke: '#0a0a0c', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="legend">
        {data.map((d) => (
          <span key={d.station} className="legend-chip">
            <span className="legend-x num">{fmt(d.x * 100, 1)} cm</span>
            <span className="legend-name">{d.station}</span>
          </span>
        ))}
      </div>
    </div>
  )
}