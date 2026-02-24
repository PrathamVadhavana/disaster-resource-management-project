'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import { useAuth } from '@/lib/auth-provider'
import {
    Loader2, Clock, CheckCircle2, XCircle, Search, MapPin, Package,
    ChevronLeft, ChevronRight, ArrowRight, Truck, HandHeart, AlertTriangle,
    Play, Check, RefreshCw, Filter
} from 'lucide-react'

const STATUS_TABS = ['approved', 'assigned', 'in_progress', 'completed'] as const

const STATUS_CONFIG: Record<string, { label: string; icon: any; color: string; bg: string }> = {
    approved: { label: 'Available', icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50 dark:bg-green-500/10 ring-green-500/20' },
    assigned: { label: 'Assigned', icon: HandHeart, color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-500/10 ring-blue-500/20' },
    in_progress: { label: 'In Progress', icon: Truck, color: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-500/10 ring-purple-500/20' },
    completed: { label: 'Completed', icon: Check, color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-500/10 ring-emerald-500/20' },
}

const PRIORITY_DOT: Record<string, string> = {
    critical: 'bg-red-500 animate-pulse', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-green-500',
}

export default function NGOFulfillmentPage() {
    const { profile } = useAuth()
    const qc = useQueryClient()
    const [tab, setTab] = useState<string>('approved')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [actionModal, setActionModal] = useState<{ req: any; action: 'claim' | 'complete' } | null>(null)
    const [note, setNote] = useState('')

    // Fetch requests via ngo endpoint
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-fulfillment', tab, page],
        queryFn: () => {
            if (tab === 'approved') {
                return api.getNgoAvailableRequests({ limit: 20, offset: (page - 1) * 20 })
            }
            return api.getNgoAssignedRequests({ status: tab, limit: 20, offset: (page - 1) * 20 })
        },
    })

    const requests = data?.requests || []
    const total = data?.total || 0
    const totalPages = Math.max(1, Math.ceil(total / 20))
    const statusCounts = data?.status_counts || {}

    // Realtime subscription
    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('ngo-requests-rt')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'resource_requests' }, () => {
                qc.invalidateQueries({ queryKey: ['ngo-fulfillment'] })
            })
            .subscribe()
        return () => { supabase.removeChannel(channel) }
    }, [qc])

    // Claim mutation
    const claimMutation = useMutation({
        mutationFn: async (requestId: string) => {
            return api.claimNgoRequest(requestId, {
                notes: note || 'Claimed by NGO',
            })
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-fulfillment'] })
            setActionModal(null)
            setNote('')
        },
    })

    // Mark in-progress / completed
    const statusMutation = useMutation({
        mutationFn: async ({ id, status }: { id: string; status: string }) => {
            return api.updateNgoRequestStatus(id, { status })
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-fulfillment'] })
            setActionModal(null)
            setNote('')
        },
    })

    const filtered = search
        ? requests.filter((r: any) =>
            (r.description || r.resource_type || r.victim_name || '').toLowerCase().includes(search.toLowerCase())
        )
        : requests

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <HandHeart className="w-6 h-6 text-emerald-500" />
                        Request Fulfillment
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Claim approved requests and track fulfillment progress
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Status Tabs */}
            <div className="flex items-center gap-3 overflow-x-auto pb-1">
                {STATUS_TABS.map(s => {
                    const cfg = STATUS_CONFIG[s]
                    const Icon = cfg.icon
                    const count = statusCounts[s] || 0
                    return (
                        <button key={s} onClick={() => { setTab(s); setPage(1) }}
                            className={cn(
                                'flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all border whitespace-nowrap',
                                tab === s
                                    ? 'bg-emerald-600 text-white border-emerald-600 shadow-md'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5'
                            )}>
                            <Icon className="w-4 h-4" />
                            {cfg.label}
                            <span className={cn('text-xs px-1.5 py-0.5 rounded-full', tab === s ? 'bg-white/20 text-white' : 'bg-slate-100 dark:bg-white/10 text-slate-500')}>{count}</span>
                        </button>
                    )
                })}
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search requests..."
                    className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
            </div>

            {/* Request Cards */}
            {filtered.length === 0 ? (
                <div className="text-center py-16">
                    <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">No {STATUS_CONFIG[tab]?.label.toLowerCase()} requests</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {filtered.map((req: any) => (
                        <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-md transition-all">
                            <div className="flex items-start gap-4">
                                <div className={cn('w-3 h-3 rounded-full mt-1.5 shrink-0', PRIORITY_DOT[req.priority] || 'bg-slate-400')} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                            {req.resource_type || 'Resource Request'}
                                        </h3>
                                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset',
                                            STATUS_CONFIG[req.status]?.bg || 'bg-slate-100')}>
                                            {STATUS_CONFIG[req.status]?.label || req.status}
                                        </span>
                                        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 capitalize">
                                            {req.priority}
                                        </span>
                                    </div>
                                    {req.description && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 line-clamp-2">{req.description}</p>
                                    )}
                                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-400 flex-wrap">
                                        {req.victim_name && <span className="flex items-center gap-1">👤 {req.victim_name}</span>}
                                        {req.address_text && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{req.address_text}</span>}
                                        <span>Qty: {req.quantity || 1}</span>
                                        <span>{new Date(req.created_at).toLocaleDateString()}</span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    {tab === 'approved' && (
                                        <button
                                            onClick={() => claimMutation.mutate(req.id)}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors">
                                            <Play className="w-3 h-3" /> Claim
                                        </button>
                                    )}
                                    {(tab === 'assigned' || tab === 'in_progress') && (
                                        <>
                                            {req.status === 'assigned' && (
                                                <button
                                                    onClick={() => statusMutation.mutate({ id: req.id, status: 'in_progress' })}
                                                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 text-white hover:bg-blue-700">
                                                    <Truck className="w-3 h-3" /> Start
                                                </button>
                                            )}
                                            {req.status === 'in_progress' && (
                                                <button
                                                    onClick={() => statusMutation.mutate({ id: req.id, status: 'completed' })}
                                                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-600 text-white hover:bg-green-700">
                                                    <CheckCircle2 className="w-3 h-3" /> Complete
                                                </button>
                                            )}
                                        </>
                                    )}
                                    {tab === 'completed' && (
                                        <span className="text-xs text-emerald-600 font-medium flex items-center gap-1"><Check className="w-3 h-3" /> Done</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500">Page {page} of {totalPages} ({total} total)</p>
                    <div className="flex gap-2">
                        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40">
                            <ChevronLeft className="w-3.5 h-3.5" /> Previous
                        </button>
                        <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40">
                            Next <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
