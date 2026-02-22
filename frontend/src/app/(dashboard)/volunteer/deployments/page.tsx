'use client'

import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Rocket, Search, Filter, MapPin, Calendar, Clock,
    AlertTriangle, CheckCircle2, Loader2, ChevronDown, ChevronUp
} from 'lucide-react'
import { cn } from '@/lib/utils'

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
    active: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400' },
    monitoring: { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400' },
    resolved: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-700 dark:text-green-400' },
}

const TYPE_ICONS: Record<string, string> = {
    earthquake: '🌍', flood: '🌊', hurricane: '🌀', wildfire: '🔥',
    tornado: '🌪️', tsunami: '🌊', drought: '☀️', volcano: '🌋',
}

export default function VolunteerDeploymentsPage() {
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState<string>('all')
    const [expanded, setExpanded] = useState<string | null>(null)

    const { data: disasters, isLoading } = useQuery({
        queryKey: ['volunteer-deployments'],
        queryFn: () => api.getDisasters(),
        refetchInterval: 30000,
    })

    const { data: resources } = useQuery({
        queryKey: ['volunteer-deployment-resources'],
        queryFn: () => api.getResources(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []

    // Build deployment timeline from all disasters
    const deployments = useMemo(() => {
        return disasterList.map((d: any) => {
            const related = resourceList.filter((r: any) => r.disaster_id === d.id)
            const daysActive = d.created_at
                ? Math.max(1, Math.ceil((Date.now() - new Date(d.created_at).getTime()) / (1000 * 60 * 60 * 24)))
                : 0
            return {
                ...d,
                resourceCount: related.length,
                allocatedCount: related.filter((r: any) => r.status === 'allocated' || r.status === 'in_transit').length,
                daysActive,
                icon: TYPE_ICONS[d.type] || '⚠️',
            }
        }).sort((a: any, b: any) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
    }, [disasterList, resourceList])

    const filtered = useMemo(() => {
        return deployments.filter((d: any) => {
            const matchSearch = !search ||
                d.title.toLowerCase().includes(search.toLowerCase()) ||
                (d.location || '').toLowerCase().includes(search.toLowerCase())
            const matchStatus = statusFilter === 'all' || d.status === statusFilter
            return matchSearch && matchStatus
        })
    }, [deployments, search, statusFilter])

    const stats = {
        total: deployments.length,
        active: deployments.filter(d => d.status === 'active').length,
        resolved: deployments.filter(d => d.status === 'resolved').length,
        totalDays: deployments.reduce((sum: number, d: any) => sum + d.daysActive, 0),
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Deployment History</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Track disaster response deployments and operations</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { icon: Rocket, color: 'blue', label: 'Total Deployments', value: stats.total },
                    { icon: AlertTriangle, color: 'red', label: 'Active', value: stats.active },
                    { icon: CheckCircle2, color: 'green', label: 'Resolved', value: stats.resolved },
                    { icon: Clock, color: 'purple', label: 'Total Days', value: stats.totalDays },
                ].map((s, i) => (
                    <div key={i} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl bg-${s.color}-100 dark:bg-${s.color}-500/10 flex items-center justify-center`}>
                                <s.icon className={`w-5 h-5 text-${s.color}-600 dark:text-${s.color}-400`} />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-slate-900 dark:text-white">{s.value}</p>
                                <p className="text-xs text-slate-500">{s.label}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search deployments..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All Status</option>
                    <option value="active">Active</option>
                    <option value="monitoring">Monitoring</option>
                    <option value="resolved">Resolved</option>
                </select>
            </div>

            {/* Timeline */}
            <div className="space-y-3">
                {filtered.map((deployment: any) => {
                    const sc = STATUS_COLORS[deployment.status] || STATUS_COLORS.active
                    const isExpanded = expanded === deployment.id
                    return (
                        <div key={deployment.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden hover:shadow-lg transition-shadow">
                            <button onClick={() => setExpanded(isExpanded ? null : deployment.id)}
                                className="w-full text-left p-5 flex items-center gap-4">
                                {/* Timeline dot */}
                                <div className="flex flex-col items-center gap-1">
                                    <div className={cn('w-3 h-3 rounded-full', deployment.status === 'active' ? 'bg-blue-500 animate-pulse' : deployment.status === 'resolved' ? 'bg-green-500' : 'bg-amber-500')} />
                                    <div className="w-px h-6 bg-slate-200 dark:bg-white/10" />
                                </div>

                                <span className="text-2xl">{deployment.icon}</span>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{deployment.title}</h3>
                                        <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', sc.bg, sc.text)}>
                                            {deployment.status}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-slate-500">
                                        {deployment.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{deployment.location}</span>}
                                        <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{deployment.created_at ? new Date(deployment.created_at).toLocaleDateString() : 'N/A'}</span>
                                        <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{deployment.daysActive} days</span>
                                    </div>
                                </div>
                                {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                            </button>

                            {isExpanded && (
                                <div className="px-5 pb-5 pt-0 border-t border-slate-100 dark:border-white/5">
                                    <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
                                        <div>
                                            <p className="text-xs text-slate-500 mb-1">Type</p>
                                            <p className="font-medium text-slate-900 dark:text-white capitalize">{deployment.type}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-500 mb-1">Severity</p>
                                            <p className="font-medium capitalize text-slate-900 dark:text-white">{deployment.severity}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-500 mb-1">Resources</p>
                                            <p className="font-medium text-slate-900 dark:text-white">{deployment.allocatedCount}/{deployment.resourceCount} allocated</p>
                                        </div>
                                    </div>
                                    {deployment.description && (
                                        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{deployment.description}</p>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Rocket className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No deployments found</p>
                    <p className="text-xs text-slate-500 mt-1">Deployment records will appear as disasters are tracked</p>
                </div>
            )}
        </div>
    )
}
