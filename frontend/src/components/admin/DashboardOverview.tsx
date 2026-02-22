'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import {
    Loader2, AlertTriangle, Users, Radio, Activity,
    ArrowRight, Brain, Map, CheckCircle2, TrendingUp,
    ChevronRight, Zap, BarChart3, Shield
} from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const SEV: Record<string, { bg: string; text: string; ring: string }> = {
    critical: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', ring: 'ring-red-500/20' },
    high: { bg: 'bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400', ring: 'ring-orange-500/20' },
    medium: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-500/20' },
    low: { bg: 'bg-green-500/10', text: 'text-green-600 dark:text-green-400', ring: 'ring-green-500/20' },
}

function SeverityBadge({ severity }: { severity: string }) {
    const s = SEV[severity] || SEV.low
    return <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ring-1 ring-inset', s.bg, s.text, s.ring)}>{severity}</span>
}

export function AdminDashboardOverview() {
    const { profile } = useAuth()

    const { data: disasters, isLoading: dLoad } = useQuery({
        queryKey: ['admin-disasters'],
        queryFn: () => api.getDisasters({ limit: 100 }),
        refetchInterval: 30000,
    })

    const { data: events, isLoading: eLoad } = useQuery({
        queryKey: ['admin-events'],
        queryFn: () => api.getIngestedEvents({ limit: 50 }),
        refetchInterval: 20000,
    })

    const { data: ingestion, isLoading: iLoad } = useQuery({
        queryKey: ['admin-ingestion'],
        queryFn: async () => { const r = await fetch(`${API}/api/ingestion/status`); if (!r.ok) throw new Error('Failed'); return r.json() },
        refetchInterval: 15000,
    })

    const { data: predictions, isLoading: pLoad } = useQuery({
        queryKey: ['admin-predictions'],
        queryFn: () => api.getPredictions({}),
        refetchInterval: 30000,
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const eventList = Array.isArray(events) ? events : []
    const predictionList = Array.isArray(predictions) ? predictions : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const criticalCount = activeDisasters.filter((d: any) => d.severity === 'critical').length
    const recent24h = eventList.filter((e: any) => { const t = new Date(e.ingested_at || e.created_at).getTime(); return Date.now() - t < 86_400_000 })
    const sources = ingestion?.sources || []
    const orchestratorRunning = ingestion?.orchestrator_running ?? false

    const isLoading = dLoad && eLoad

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">System Overview</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Full administrative control over the disaster management platform.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <span className={cn('w-2 h-2 rounded-full', orchestratorRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500')} />
                    <span className="text-xs font-medium text-slate-500">{orchestratorRunning ? 'System Online' : 'System Offline'}</span>
                </div>
            </div>

            {/* Top Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Active Disasters" value={activeDisasters.length} icon={AlertTriangle} color="red" sub={criticalCount > 0 ? `${criticalCount} critical` : undefined} />
                <StatCard label="Events (24h)" value={recent24h.length} icon={Radio} color="amber" sub={`${eventList.length} total ingested`} />
                <StatCard label="AI Predictions" value={predictionList.length} icon={Brain} color="purple" sub="severity + spread + impact" />
                <StatCard label="Data Feeds" value={`${sources.filter((s: any) => s.status === 'success').length}/${sources.length}`} icon={Activity} color={orchestratorRunning ? 'green' : 'blue'} sub={orchestratorRunning ? 'Orchestrator running' : 'Orchestrator stopped'} />
            </div>

            {/* Active Disasters */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Active Disasters</h2>
                    <Link href="/admin/live-map" className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                        View Map <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
                {activeDisasters.length ? (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-100 dark:border-white/5">
                                    <th className="text-left px-5 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Disaster</th>
                                    <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Type</th>
                                    <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Severity</th>
                                    <th className="text-left px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider">Created</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                                {activeDisasters.slice(0, 8).map((d: any) => (
                                    <tr key={d.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                        <td className="px-5 py-3"><p className="font-medium text-slate-900 dark:text-white truncate max-w-[240px]">{d.title || 'Untitled'}</p></td>
                                        <td className="px-3 py-3"><span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 capitalize">{d.type}</span></td>
                                        <td className="px-3 py-3"><SeverityBadge severity={d.severity} /></td>
                                        <td className="px-3 py-3 text-xs text-slate-500">{d.start_date ? new Date(d.start_date).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="p-10 text-center text-sm text-slate-400">No active disasters</div>
                )}
            </div>

            {/* Data Feeds + Recent Events */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Data Feeds */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Data Feed Status</h3>
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
                                <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium', s.status === 'success' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400' : s.status === 'error' ? 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500')}>{s.status || 'idle'}</span>
                            </div>
                        )) : <p className="text-xs text-slate-400 text-center py-4">No sources configured</p>}
                    </div>
                </div>

                {/* Recent Predictions */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Recent AI Predictions</h3>
                        <Link href="/admin/coordinator" className="text-xs text-blue-500 hover:text-blue-600 font-medium flex items-center gap-1">More <ChevronRight className="w-3 h-3" /></Link>
                    </div>
                    {predictionList.length > 0 ? (
                        <div className="space-y-2">
                            {predictionList.slice(0, 6).map((p: any) => (
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
                    ) : <p className="text-xs text-slate-400 text-center py-3">No predictions yet</p>}
                </div>
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <Link href="/admin/users" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
                    <Users className="w-6 h-6 text-blue-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Users</h4>
                    <p className="text-xs text-slate-500 mt-1">Manage users, roles, and permissions.</p>
                </Link>
                <Link href="/admin/live-map" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-md transition-all">
                    <Map className="w-6 h-6 text-emerald-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Live Map</h4>
                    <p className="text-xs text-slate-500 mt-1">Real-time disaster events on map.</p>
                </Link>
                <Link href="/admin/coordinator" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <Brain className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">AI Coordinator</h4>
                    <p className="text-xs text-slate-500 mt-1">Situation reports and anomaly detection.</p>
                </Link>
                <Link href="/admin/analytics" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-amber-300 dark:hover:border-amber-500/30 hover:shadow-md transition-all">
                    <BarChart3 className="w-6 h-6 text-amber-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Analytics</h4>
                    <p className="text-xs text-slate-500 mt-1">System performance and reports.</p>
                </Link>
            </div>
        </div>
    )
}

function StatCard({ label, value, icon: Icon, color, sub }: { label: string; value: string | number; icon: any; color: string; sub?: string }) {
    const colorMap: Record<string, string> = {
        blue: 'from-blue-500 to-blue-600', red: 'from-red-500 to-red-600', amber: 'from-amber-500 to-amber-600',
        green: 'from-green-500 to-green-600', purple: 'from-purple-500 to-purple-600',
    }
    return (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
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
        </div>
    )
}
