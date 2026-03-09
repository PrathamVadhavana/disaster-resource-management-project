'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import { OperationalPulseTimeline } from './OperationalPulse'
import Link from 'next/link'
import {
    Loader2, AlertTriangle, Users, Radio, Activity,
    ArrowRight, Brain, Map, CheckCircle2, TrendingUp,
    ChevronRight, Zap, BarChart3, Shield, Inbox, Package
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

    const { data: disasters, isLoading: dLoad, isError: dError } = useQuery({
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
        queryFn: () => api.getIngestionStatus(),
        refetchInterval: 15000,
    })

    const { data: predictions, isLoading: pLoad } = useQuery({
        queryKey: ['admin-predictions'],
        queryFn: () => api.getPredictions({}),
        refetchInterval: 30000,
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const predictionList = Array.isArray(predictions) ? predictions : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const orchestratorRunning = ingestion?.orchestrator?.is_running

    const isLoading = dLoad || eLoad || iLoad || pLoad
    const isError = dError

    if (isError) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <AlertTriangle className="w-10 h-10 text-amber-500" />
                <p className="text-sm text-slate-500">Unable to load dashboard data.</p>
                <button onClick={() => window.location.reload()} className="text-sm text-blue-500 hover:underline">Retry</button>
            </div>
        )
    }

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
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Admin Command Center</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Global response monitoring and AI system oversight</p>
                </div>
                <div className="flex items-center gap-2">
                    <div className={cn('px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center gap-2 shadow-sm border', orchestratorRunning ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20' : 'bg-red-500/10 text-red-600 border-red-500/20')}>
                        <span className={cn('w-1.5 h-1.5 rounded-full', orchestratorRunning ? 'bg-emerald-500 animate-pulse' : 'bg-red-500')} />
                        System: {orchestratorRunning ? 'Running' : 'Stopped'}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: 'Active Disasters', value: activeDisasters.length.toString(), icon: AlertTriangle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-500/10' },
                    { label: 'Ingested Events', value: events?.length?.toString() || '0', icon: Radio, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-500/10' },
                    { label: 'AI Predictions', value: predictionList.length.toString(), icon: Brain, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-500/10' },
                    { label: 'System Health', value: orchestratorRunning ? 'Online' : 'Offline', icon: Activity, color: orchestratorRunning ? 'text-emerald-500' : 'text-slate-500', bg: orchestratorRunning ? 'bg-emerald-50 dark:bg-emerald-500/10' : 'bg-slate-50 dark:bg-slate-500/10' }
                ].map((card, idx) => (
                    <div key={idx} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-4">
                        <div className={cn("w-12 h-12 rounded-xl flex items-center justify-center shrink-0", card.bg)}>
                            <card.icon className={cn("w-6 h-6", card.color)} />
                        </div>
                        <div>
                            <p className="text-2xl font-black text-slate-900 dark:text-white leading-tight">{card.value}</p>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{card.label}</p>
                        </div>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Column - Map & Pulse */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Operational Pulse Section */}
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                            <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                <Activity className="w-4 h-4 text-blue-500" />
                                Operational Pulse
                            </h2>
                            <div className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Live Response Feed</span>
                            </div>
                        </div>
                        <div className="p-5 max-h-[600px] overflow-y-auto thin-scrollbar">
                            <OperationalPulseTimeline />
                        </div>
                    </div>

                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                            <h2 className="font-semibold text-slate-900 dark:text-white">Active Disasters</h2>
                            <Link href="/admin/disasters" className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                                All <ArrowRight className="w-3.5 h-3.5" />
                            </Link>
                        </div>
                        <div className="divide-y divide-slate-100 dark:divide-white/5">
                            {activeDisasters.length ? activeDisasters.slice(0, 5).map((d: any) => (
                                <div key={d.id} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{d.title}</p>
                                        <p className="text-[10px] text-slate-400 mt-0.5 capitalize">{d.type} • {d.location_name}</p>
                                    </div>
                                    <SeverityBadge severity={d.severity} />
                                </div>
                            )) : (
                                <div className="p-8 text-center text-sm text-slate-400">No active disasters</div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Sidebar Column */}
                <div className="space-y-6">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                            <h2 className="font-semibold text-slate-900 dark:text-white">AI Predictions</h2>
                            <Link href="/admin/ai-intelligence" className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
                                <ChevronRight className="w-4 h-4" />
                            </Link>
                        </div>
                        <div className="divide-y divide-slate-100 dark:divide-white/5">
                            {predictionList.slice(0, 5).map((p: any) => (
                                <div key={p.id} className="p-4 hover:bg-slate-50 dark:hover:bg-white/[0.02]">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{p.prediction_type}</span>
                                        <span className="text-[10px] font-medium text-emerald-500 flex items-center gap-1"><Zap className="w-2.5 h-2.5" /> {Math.round(p.confidence_score * 100)}%</span>
                                    </div>
                                    <p className="text-sm text-slate-900 dark:text-white truncate">{p.disaster_title || 'Impacting Location'}</p>
                                    <div className="mt-2 h-1 w-full bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${p.confidence_score * 100}%` }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                            <h2 className="font-semibold text-slate-900 dark:text-white">Quick Actions</h2>
                        </div>
                        <div className="p-4 grid grid-cols-2 gap-2">
                            <Link href="/admin/requests" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group">
                                <Inbox className="w-5 h-5 text-blue-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-blue-500">Inbox</span>
                            </Link>
                            <Link href="/admin/resources" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group">
                                <Package className="w-5 h-5 text-emerald-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-emerald-500">Resources</span>
                            </Link>
                            <Link href="/admin/users" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group">
                                <Users className="w-5 h-5 text-amber-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-amber-500">Users</span>
                            </Link>
                            <Link href="/admin/live-map" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group text-center">
                                <Map className="w-5 h-5 text-purple-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-purple-500 leading-none">Response Map</span>
                            </Link>
                            <Link href="/admin/ai-intelligence" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group">
                                <Brain className="w-5 h-5 text-indigo-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-indigo-500">AI Intelligence</span>
                            </Link>
                            <Link href="/admin/analytics" className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-white/[0.05] transition-colors group">
                                <BarChart3 className="w-5 h-5 text-rose-500" />
                                <span className="text-[10px] font-medium text-slate-500 group-hover:text-rose-500">Analytics</span>
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
