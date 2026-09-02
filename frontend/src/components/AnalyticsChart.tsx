import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface Point {
  date: string
  engagement: number
}

export function AnalyticsChart({ series }: { series: Point[] }) {
  if (!series.length) return null

  return (
    <div className="desk-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series}>
          <XAxis dataKey="date" tickFormatter={(v) => String(v).slice(5, 10)} />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="engagement" stroke="#8B7355" strokeWidth={2} dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
