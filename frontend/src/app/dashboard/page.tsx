'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import Link from 'next/link'
import {
  AlertTriangle, CloudRain, Activity, Radio, Map,
  Brain, TrendingUp, Zap, Eye, CheckCircle2,
  ChevronRight, Thermometer, Wind
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  BarChart, Bar, PieChart, Pie, Cell, AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/* ─── Severity Colors ──────────────────────────────────────── */

const SEV = {
  critical: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', ring: 'ring-red-500/20', fill: '#ef4444' },
  high: { bg: 'bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400', ring: 'ring-orange-500/20', fill: '#f97316' },
  medium: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-500/20', fill: '#f59e0b' },
  low: { bg: 'bg-green-500/10', text: 'text-green-600 dark:text-green-400', ring: 'ring-green-500/20', fill: '#22c55e' },
} as const

const DISASTER_COLORS: Record<string, string> = {
  earthquake: '#ef4444', flood: '#3b82f6', hurricane: '#8b5cf6', wildfire: '#f97316',
  tsunami: '#06b6d4', volcano: '#dc2626', drought: '#d97706', tornado: '#6366f1',
  landslide: '#78716c', other: '#94a3b8',
}

/* ─── Data Hooks ───────────────────────────────────────────── */

function useDisasters() {
  return useQuery({ queryKey: ['dashboard-disasters'], queryFn: () => api.getDisasters({ limit: 100 }), refetchInterval: 30_000, staleTime: 15_000 })
}
function useEvents() {
  return useQuery({ queryKey: ['dashboard-events'], queryFn: () => api.getIngestedEvents({ limit: 50 }), refetchInterval: 20_000, staleTime: 10_000 })
}
function useIngestionStatus() {
  return useQuery({
    queryKey: ['dashboard-ingestion'],
    queryFn: async () => { const r = await fetch(`${API}/api/ingestion/status`); if (!r.ok) throw new Error('Failed'); return r.json() },
    refetchInterval: 15_000,
  })
}
function usePredictions() {
  return useQuery({ queryKey: ['dashboard-predictions'], queryFn: () => api.getPredictions({}), refetchInterval: 30_000, staleTime: 15_000 })
}
function useWeatherObs() {
  return useQuery({ queryKey: ['dashboard-weather'], queryFn: () => api.getWeatherObservations(undefined, 20), refetchInterval: 30_000, staleTime: 15_000 })
}

/* ─── Helpers ──────────────────────────────────────────────── */

function StatCard({
  label, value, icon: Icon, color = 'blue', href, sub
}: {
  label: string; value: string | number; icon: any; color?: string; href?: string; sub?: string
}) {
  const colorMap: Record<string, string> = {
    blue: 'from-blue-500 to-blue-600', red: 'from-red-500 to-red-600', amber: 'from-amber-500 to-amber-600',
    green: 'from-green-500 to-green-600', purple: 'from-purple-500 to-purple-600',
  }
  const Wrapper = href ? Link : 'div'
  const props = href ? { href } : {}
  return (
    <Wrapper {...(props as any)} className="group relative overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-slate-300 dark:hover:border-slate-700 transition-all hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
        </div>
        <div className={cn('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center', colorMap[color])}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      {href && <div className="absolute bottom-3 right-4 opacity-0 group-hover:opacity-100 transition-opacity"><ChevronRight className="w-4 h-4 text-slate-400" /></div>}
    </Wrapper>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = SEV[severity as keyof typeof SEV] || SEV.low
  return <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ring-1 ring-inset', s.bg, s.text, s.ring)}>{severity}</span>
}

function EmptyState({ message }: { message: string }) {
  return <div className="flex flex-col items-center justify-center py-8 text-slate-400"><Eye className="w-8 h-8 mb-2 opacity-40" /><p className="text-sm">{message}</p></div>
}

/* ─── Main Dashboard ───────────────────────────────────────── */

export default function DashboardPage() {
  const { data: disasters, isLoading: dLoad } = useDisasters()
  const { data: events, isLoading: eLoad } = useEvents()
  const { data: ingestion, isLoading: iLoad } = useIngestionStatus()
  const { data: predictions, isLoading: pLoad } = usePredictions()
  const { data: weatherObs } = useWeatherObs()

  const disasterList = Array.isArray(disasters) ? disasters : []
  const eventList = Array.isArray(events) ? events : []
  const predictionList = Array.isArray(predictions) ? predictions : []
  const weatherList = Array.isArray(weatherObs) ? weatherObs : []

  const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
  const criticalCount = activeDisasters.filter((d: any) => d.severity === 'critical').length
  const recent24h = eventList.filter((e: any) => { const t = new Date(e.ingested_at || e.created_at).getTime(); return Date.now() - t < 86_400_000 })

  const sources = ingestion?.sources || []
  const orchestratorRunning = ingestion?.orchestrator_running ?? false

  // Charts data
  const typeDistribution = disasterList.reduce((acc: Record<string, number>, d: any) => { acc[d.type || 'other'] = (acc[d.type || 'other'] || 0) + 1; return acc }, {})
  const pieData = Object.entries(typeDistribution).map(([name, value]) => ({ name, value, fill: DISASTER_COLORS[name] || DISASTER_COLORS.other }))

  const sevDist = disasterList.reduce((acc: Record<string, number>, d: any) => { acc[d.severity || 'low'] = (acc[d.severity || 'low'] || 0) + 1; return acc }, {})
  const sevBarData = (['critical', 'high', 'medium', 'low'] as const).map(s => ({ severity: s, count: sevDist[s] || 0, fill: SEV[s].fill }))

  const timelineData = eventList.slice(0, 20).map((e: any) => ({
    time: new Date(e.ingested_at || e.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    events: 1, type: e.event_type,
  })).reverse()

  const isLoading = dLoad && eLoad

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-[1400px] mx-auto">

      {/* ── Top Stats ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Disasters" value={isLoading ? '—' : activeDisasters.length} icon={AlertTriangle} color="red" href="/dashboard/live-map" sub={criticalCount > 0 ? `${criticalCount} critical` : undefined} />
        <StatCard label="Events (24h)" value={isLoading ? '—' : recent24h.length} icon={Radio} color="amber" sub={`${eventList.length} total ingested`} />
        <StatCard label="Predictions" value={pLoad ? '—' : predictionList.length} icon={Brain} color="purple" href="/dashboard/coordinator" sub="severity + spread + impact" />
        <StatCard label="Data Feeds" value={iLoad ? '—' : `${sources.filter((s: any) => s.status === 'success').length}/${sources.length}`} icon={Activity} color={orchestratorRunning ? 'green' : 'blue'} sub={orchestratorRunning ? 'Orchestrator running' : 'Orchestrator stopped'} />
      </div>

      {/* ── Charts Row ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Severity Distribution</h3>
          {sevBarData.some(d => d.count > 0) ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={sevBarData} barSize={28}>
                <XAxis dataKey="severity" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={24} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>{sevBarData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState message="No disasters yet" />}
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Disaster Types</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={3} dataKey="value">
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Pie>
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }} />
                <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <EmptyState message="No data available" />}
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Recent Event Activity</h3>
          {timelineData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={timelineData}>
                <defs><linearGradient id="eventGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} /><stop offset="100%" stopColor="#3b82f6" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="time" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={20} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }} />
                <Area type="monotone" dataKey="events" stroke="#3b82f6" strokeWidth={2} fill="url(#eventGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EmptyState message="Waiting for events" />}
        </div>
      </div>

      {/* ── Active Disasters + Side Panels ─────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
          <div className="flex items-center justify-between p-5 pb-3">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Active Disasters</h3>
            <Link href="/dashboard/live-map" className="text-xs text-blue-500 hover:text-blue-600 font-medium flex items-center gap-1">View Map <ChevronRight className="w-3 h-3" /></Link>
          </div>
          <div className="overflow-x-auto">
            {activeDisasters.length > 0 ? (
              <table className="w-full text-sm">
                <thead><tr className="border-t border-slate-100 dark:border-slate-800">
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Disaster</th>
                  <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Type</th>
                  <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Severity</th>
                  <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Created</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {activeDisasters.slice(0, 8).map((d: any) => (
                    <tr key={d.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                      <td className="px-5 py-3"><p className="font-medium text-slate-900 dark:text-white truncate max-w-[240px]">{d.title || 'Untitled'}</p></td>
                      <td className="px-3 py-3"><span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 capitalize">{d.type}</span></td>
                      <td className="px-3 py-3"><SeverityBadge severity={d.severity} /></td>
                      <td className="px-3 py-3 text-xs text-slate-500">{d.start_date ? new Date(d.start_date).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <EmptyState message={dLoad ? 'Loading disasters…' : 'No active disasters'} />}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {/* Data Feeds */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Data Feeds</h3>
              <div className="flex items-center gap-1.5">
                <span className={cn('w-2 h-2 rounded-full', orchestratorRunning ? 'bg-green-500 animate-pulse' : 'bg-slate-400')} />
                <span className="text-[10px] font-medium text-slate-500">{orchestratorRunning ? 'Live' : 'Offline'}</span>
              </div>
            </div>
            <div className="space-y-2">
              {sources.length > 0 ? sources.map((s: any) => (
                <div key={s.name} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', s.status === 'success' ? 'bg-green-500' : s.status === 'error' ? 'bg-red-500' : 'bg-slate-400')} />
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-300 capitalize truncate">{s.name.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.last_polled && <span className="text-[10px] text-slate-400">{new Date(s.last_polled).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium', s.status === 'success' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400' : s.status === 'error' ? 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500')}>{s.status || 'idle'}</span>
                  </div>
                </div>
              )) : <p className="text-xs text-slate-400 text-center py-4">{iLoad ? 'Loading…' : 'No sources configured'}</p>}
            </div>
          </div>

          {/* Latest Weather */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Latest Weather</h3>
            {weatherList.length > 0 ? (
              <div className="space-y-2.5">
                {weatherList.slice(0, 4).map((w: any, i: number) => (
                  <div key={w.id || i} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <CloudRain className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                      <span className="text-slate-700 dark:text-slate-300 truncate">{w.weather_desc || w.weather_main || 'Unknown'}</span>
                    </div>
                    <div className="flex items-center gap-3 text-slate-500 flex-shrink-0">
                      {w.temperature_c != null && <span className="flex items-center gap-0.5"><Thermometer className="w-3 h-3" />{Math.round(w.temperature_c)}°</span>}
                      {w.wind_speed_ms != null && <span className="flex items-center gap-0.5"><Wind className="w-3 h-3" />{w.wind_speed_ms}m/s</span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-slate-400 text-center py-3">No weather data</p>}
          </div>

          {/* Recent Predictions */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Recent Predictions</h3>
              <Link href="/dashboard/coordinator" className="text-xs text-blue-500 hover:text-blue-600 font-medium flex items-center gap-1">More <ChevronRight className="w-3 h-3" /></Link>
            </div>
            {predictionList.length > 0 ? (
              <div className="space-y-2">
                {predictionList.slice(0, 5).map((p: any) => (
                  <div key={p.id} className="flex items-center justify-between py-1">
                    <div className="flex items-center gap-2">
                      <Zap className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
                      <span className="text-xs text-slate-700 dark:text-slate-300 capitalize">{p.prediction_type}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {p.predicted_severity && <SeverityBadge severity={p.predicted_severity} />}
                      {p.confidence_score != null && <span className="text-[10px] text-slate-400 font-mono">{(p.confidence_score * 100).toFixed(0)}%</span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-slate-400 text-center py-3">{pLoad ? 'Loading…' : 'No predictions yet'}</p>}
          </div>
        </div>
      </div>

      {/* ── Live Event Feed ───────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2"><h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Live Event Feed</h3><span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" /></div>
          <span className="text-[10px] text-slate-400">Auto-refreshes every 20s</span>
        </div>
        {eventList.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {eventList.slice(0, 9).map((e: any) => (
              <div key={e.id} className="flex gap-3 p-3 rounded-xl border border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                <div className="flex-shrink-0 mt-0.5">
                  <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center text-xs',
                    e.severity === 'critical' ? 'bg-red-100 dark:bg-red-500/10' : e.severity === 'high' ? 'bg-orange-100 dark:bg-orange-500/10' : e.severity === 'medium' ? 'bg-amber-100 dark:bg-amber-500/10' : 'bg-green-100 dark:bg-green-500/10'
                  )}>
                    {e.event_type === 'earthquake' ? '🔴' : e.event_type === 'gdacs_alert' ? '🌍' : e.event_type === 'social_sos' ? '📢' : e.event_type === 'fire_hotspot' ? '🔥' : '📡'}
                  </div>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-slate-900 dark:text-white truncate">{e.title || 'Event'}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <SeverityBadge severity={e.severity || 'low'} />
                    <span className="text-[10px] text-slate-400">{e.ingested_at ? new Date(e.ingested_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
                  </div>
                  {e.processed && <div className="flex items-center gap-1 mt-1"><CheckCircle2 className="w-3 h-3 text-green-500" /><span className="text-[10px] text-green-600 dark:text-green-400">Processed</span></div>}
                </div>
              </div>
            ))}
          </div>
        ) : <EmptyState message={eLoad ? 'Loading events…' : 'No events ingested yet — data feeds will appear here'} />}
      </div>

      {/* ── Quick Actions ─────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link href="/dashboard/live-map" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
          <Map className="w-6 h-6 text-blue-500 mb-2" />
          <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Open Live Map</h4>
          <p className="text-xs text-slate-500 mt-1">Real-time disaster events on an interactive map with all data overlays.</p>
          <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ChevronRight className="w-3 h-3" /></div>
        </Link>
        <Link href="/dashboard/coordinator" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
          <Brain className="w-6 h-6 text-purple-500 mb-2" />
          <h4 className="text-sm font-semibold text-slate-900 dark:text-white">AI Coordinator</h4>
          <p className="text-xs text-slate-500 mt-1">Situation reports, anomaly detection, NL queries, and outcome tracking.</p>
          <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ChevronRight className="w-3 h-3" /></div>
        </Link>
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <Activity className="w-6 h-6 text-green-500 mb-2" />
          <h4 className="text-sm font-semibold text-slate-900 dark:text-white">System Health</h4>
          <p className="text-xs text-slate-500 mt-1">
            Backend: <span className="text-green-600 dark:text-green-400 font-medium">Connected</span> ·
            Feeds: <span className={cn('font-medium', orchestratorRunning ? 'text-green-600 dark:text-green-400' : 'text-red-500')}>{orchestratorRunning ? 'Active' : 'Stopped'}</span>
          </p>
          <p className="text-[10px] text-slate-400 mt-2">{sources.filter((s: any) => s.status === 'success').length} of {sources.length} feeds healthy</p>
        </div>
      </div>
    </div>
  )
}
