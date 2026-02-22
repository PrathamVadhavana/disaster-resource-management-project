'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Heart, Search, Filter, AlertTriangle, MapPin,
    TrendingUp, Clock, Loader2, CheckCircle2, ExternalLink
} from 'lucide-react'
import { cn } from '@/lib/utils'

const SEVERITY_COLORS: Record<string, string> = {
    critical: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
    medium: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    low: 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400',
}

const TYPE_ICONS: Record<string, string> = {
    earthquake: '🌍', flood: '🌊', hurricane: '🌀', wildfire: '🔥',
    tornado: '🌪️', tsunami: '🌊', drought: '☀️', volcano: '🌋',
}

export default function DonorCausesPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [severityFilter, setSeverityFilter] = useState<string>('all')

    // Fetch pledges from backend API
    const { data: pledges = [] } = useQuery({
        queryKey: ['donor-pledges'],
        queryFn: () => api.getPledges(),
    })

    const donatedIds = useMemo(() => {
        return new Set(pledges.map((p: any) => p.disaster_id))
    }, [pledges])

    const { data: disasters, isLoading } = useQuery({
        queryKey: ['donor-causes-disasters'],
        queryFn: () => api.getDisasters(),
        refetchInterval: 30000,
    })

    const { data: resources } = useQuery({
        queryKey: ['donor-causes-resources'],
        queryFn: () => api.getResources(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []

    // Pledge mutation
    const pledgeMutation = useMutation({
        mutationFn: (disasterId: string) => api.createPledge(disasterId),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['donor-pledges'] }),
    })

    // Also create a pending donation when pledging
    const donateMutation = useMutation({
        mutationFn: (disasterId: string) => api.createDonation({ disaster_id: disasterId, amount: 0, status: 'pending' }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['donor-donations'] }),
    })

    const handleDonate = (disasterId: string) => {
        pledgeMutation.mutate(disasterId)
        donateMutation.mutate(disasterId)
    }

    // Only show active disasters as causes
    const activeCauses = useMemo(() => {
        return disasterList
            .filter((d: any) => d.status === 'active' || d.status === 'monitoring')
            .map((d: any) => {
                const relatedResources = resourceList.filter((r: any) => r.disaster_id === d.id)
                const totalNeeded = relatedResources.reduce((acc: number, r: any) => acc + (r.quantity || 0), 0)
                const allocated = relatedResources.filter((r: any) => r.status === 'allocated' || r.status === 'in_transit').length
                const progress = relatedResources.length > 0 ? Math.round((allocated / relatedResources.length) * 100) : 0
                return { ...d, resourcesNeeded: totalNeeded, progress, resourceCount: relatedResources.length }
            })
    }, [disasterList, resourceList])

    const filtered = useMemo(() => {
        return activeCauses.filter((c: any) => {
            const matchSearch = !search ||
                (c.title || '').toLowerCase().includes(search.toLowerCase()) ||
                (c.location || '').toLowerCase().includes(search.toLowerCase())
            const matchSeverity = severityFilter === 'all' || c.severity === severityFilter
            return matchSearch && matchSeverity
        })
    }, [activeCauses, search, severityFilter])

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Active Causes</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Support ongoing disaster relief efforts — {activeCauses.length} active causes
                </p>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-3 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                        <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{activeCauses.filter((c: any) => c.severity === 'critical').length}</p>
                        <p className="text-xs text-slate-500">Critical Causes</p>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <Heart className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{donatedIds.size}</p>
                        <p className="text-xs text-slate-500">Causes Supported</p>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                        <TrendingUp className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{activeCauses.length}</p>
                        <p className="text-xs text-slate-500">Active Causes</p>
                    </div>
                </div>
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search causes by name or location..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All Severity</option>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                </select>
            </div>

            {/* Causes Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {filtered.map((cause: any) => {
                    const isDonated = donatedIds.has(cause.id)
                    return (
                        <div key={cause.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden hover:shadow-lg transition-shadow">
                            <div className="p-5 space-y-4">
                                {/* Icon + Title */}
                                <div className="flex items-start gap-3">
                                    <div className="text-2xl">{TYPE_ICONS[cause.type] || '⚠️'}</div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">{cause.title}</h3>
                                        {cause.location && (
                                            <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                                                <MapPin className="w-3 h-3" />{cause.location}
                                            </p>
                                        )}
                                    </div>
                                    <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', SEVERITY_COLORS[cause.severity] || SEVERITY_COLORS.medium)}>
                                        {cause.severity}
                                    </span>
                                </div>

                                {/* Description */}
                                {cause.description && (
                                    <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{cause.description}</p>
                                )}

                                {/* Resource Progress */}
                                <div>
                                    <div className="flex items-center justify-between text-xs mb-1.5">
                                        <span className="text-slate-500">Resource Fulfillment</span>
                                        <span className="font-semibold text-slate-900 dark:text-white">{cause.progress}%</span>
                                    </div>
                                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                                        <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all"
                                            style={{ width: `${cause.progress}%` }} />
                                    </div>
                                    <p className="text-[10px] text-slate-400 mt-1">{cause.resourceCount} resources tracked</p>
                                </div>

                                {/* Meta */}
                                <div className="flex items-center gap-3 text-[10px] text-slate-400">
                                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {cause.created_at ? new Date(cause.created_at).toLocaleDateString() : 'N/A'}</span>
                                    <span className="capitalize">{cause.type}</span>
                                </div>
                            </div>

                            {/* Donate / Donated Button */}
                            <div className="px-5 pb-4">
                                {isDonated ? (
                                    <button disabled className="w-full h-10 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-sm font-medium flex items-center justify-center gap-2 cursor-default">
                                        <CheckCircle2 className="w-4 h-4" /> Pledged Support
                                    </button>
                                ) : (
                                    <button onClick={() => handleDonate(cause.id)}
                                        className="w-full h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2">
                                        <Heart className="w-4 h-4" /> Support This Cause
                                    </button>
                                )}
                            </div>
                        </div>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Heart className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No active causes found</p>
                    <p className="text-xs text-slate-500 mt-1">Check back later for new relief opportunities</p>
                </div>
            )}
        </div>
    )
}
