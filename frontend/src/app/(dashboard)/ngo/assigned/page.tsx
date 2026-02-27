'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import {
    Loader2, Search, MapPin, ChevronLeft, ChevronRight,
    CheckSquare, Truck, Play, CheckCircle2, Package,
    RefreshCw, Navigation, Clock, User, AlertTriangle,
    Upload, FileText, ArrowRight, Timer,
} from 'lucide-react'

const STATUS_CONFIG: Record<string, { label: string; color: string; textColor: string; nextAction?: string; nextStatus?: string }> = {
    assigned: { label: 'Assigned', color: 'bg-orange-500', textColor: 'text-orange-600 bg-orange-50 dark:bg-orange-500/10 ring-orange-500/20', nextAction: 'Start Delivery', nextStatus: 'in_progress' },
    in_progress: { label: 'In Progress', color: 'bg-yellow-500', textColor: 'text-yellow-700 bg-yellow-50 dark:bg-yellow-500/10 ring-yellow-500/20', nextAction: 'Mark Delivered', nextStatus: 'delivered' },
    delivered: { label: 'Delivered', color: 'bg-green-500', textColor: 'text-green-600 bg-green-50 dark:bg-green-500/10 ring-green-500/20', nextAction: 'Mark Completed', nextStatus: 'completed' },
    completed: { label: 'Completed', color: 'bg-emerald-700', textColor: 'text-emerald-700 bg-emerald-50 dark:bg-emerald-500/10 ring-emerald-500/20' },
    closed: { label: 'Closed', color: 'bg-slate-500', textColor: 'text-slate-600 bg-slate-50 dark:bg-slate-500/10 ring-slate-500/20' },
}

const STATUS_TABS = ['all', 'assigned', 'in_progress', 'delivered', 'completed'] as const

export default function NGOAssignedRequestsPage() {
    const qc = useQueryClient()
    const [tab, setTab] = useState('all')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [actionNote, setActionNote] = useState('')
    const [confirmAction, setConfirmAction] = useState<{ req: any; nextStatus: string } | null>(null)

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-assigned', tab, page],
        queryFn: () => api.getNgoAssignedRequests({
            status: tab === 'all' ? undefined : tab,
            limit: 20,
            offset: (page - 1) * 20,
        }),
    })

    // Realtime
    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('ngo-assigned-rt')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'resource_requests' }, () => {
                qc.invalidateQueries({ queryKey: ['ngo-assigned'] })
            })
            .subscribe()
        return () => { supabase.removeChannel(channel) }
    }, [qc])

    const statusMutation = useMutation({
        mutationFn: async ({ id, newStatus }: { id: string; newStatus: string }) => {
            return api.updateNgoDeliveryStatus(id, {
                new_status: newStatus,
                notes: actionNote || undefined,
            })
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-assigned'] })
            qc.invalidateQueries({ queryKey: ['ngo-enhanced-stats'] })
            setConfirmAction(null)
            setActionNote('')
        },
    })

    const requests = data?.requests || []
    const total = data?.total || 0
    const totalPages = Math.max(1, Math.ceil(total / 20))
    const statusCounts = data?.status_counts || {}

    const filtered = search
        ? requests.filter((r: any) =>
            (r.description || r.resource_type || r.victim_name || '').toLowerCase().includes(search.toLowerCase())
        )
        : requests

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
                <Loader2 className="w-8 h-8 text-orange-500 animate-spin" />
                <span className="text-sm text-slate-500">Loading assigned requests...</span>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <CheckSquare className="w-6 h-6 text-orange-500" />
                        Assigned Requests
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Track and manage requests assigned to your organization.
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Status Tabs */}
            <div className="flex items-center gap-3 overflow-x-auto pb-1">
                {STATUS_TABS.map(s => {
                    const count = s === 'all' ? total : (statusCounts[s] || 0)
                    return (
                        <button key={s} onClick={() => { setTab(s); setPage(1) }}
                            className={cn(
                                'flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all border whitespace-nowrap',
                                tab === s
                                    ? 'bg-orange-500 text-white border-orange-500 shadow-md'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5'
                            )}>
                            {s === 'all' ? 'All' : STATUS_CONFIG[s]?.label || s}
                            <span className={cn('text-xs px-1.5 py-0.5 rounded-full', tab === s ? 'bg-white/20 text-white' : 'bg-slate-100 dark:bg-white/10 text-slate-500')}>{count}</span>
                        </button>
                    )
                })}
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search assigned requests..."
                    className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-orange-500 focus:outline-none" />
            </div>

            {/* Request Cards */}
            {filtered.length === 0 ? (
                <div className="text-center py-16">
                    <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">No assigned requests</p>
                    <p className="text-sm text-slate-400 mt-1">Requests will appear here after admin assigns them to you.</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {filtered.map((req: any) => {
                        const cfg = STATUS_CONFIG[req.status] || STATUS_CONFIG.assigned
                        return (
                            <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg transition-all">
                                {/* Top row */}
                                <div className="flex items-start justify-between mb-3">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                            {req.resource_type || 'Resource'}
                                        </h3>
                                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset', cfg.textColor)}>
                                            {cfg.label}
                                        </span>
                                        <span className="text-[10px] text-slate-400 font-mono">{req.id?.slice(0, 8)}</span>
                                    </div>
                                    {cfg.nextAction && cfg.nextStatus && (
                                        <button
                                            onClick={() => setConfirmAction({ req, nextStatus: cfg.nextStatus! })}
                                            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-orange-500 to-amber-500 text-white hover:from-orange-600 hover:to-amber-600 shadow-sm transition-all">
                                            {req.status === 'assigned' && <Play className="w-3.5 h-3.5" />}
                                            {req.status === 'in_progress' && <Truck className="w-3.5 h-3.5" />}
                                            {req.status === 'delivered' && <CheckCircle2 className="w-3.5 h-3.5" />}
                                            {cfg.nextAction}
                                        </button>
                                    )}
                                    {req.status === 'completed' && (
                                        <span className="flex items-center gap-1 text-xs text-emerald-600 font-semibold">
                                            <CheckCircle2 className="w-3.5 h-3.5" /> Completed
                                        </span>
                                    )}
                                </div>

                                {/* Details Grid */}
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                                    <div>
                                        <p className="text-slate-400 mb-0.5 flex items-center gap-1"><User className="w-3 h-3" /> Victim</p>
                                        <p className="font-medium text-slate-700 dark:text-slate-300">{req.victim_name || 'Unknown'}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5 flex items-center gap-1"><Package className="w-3 h-3" /> Quantity</p>
                                        <p className="font-bold text-slate-900 dark:text-white">{req.quantity}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5 flex items-center gap-1"><Navigation className="w-3 h-3" /> Distance</p>
                                        <p className="font-medium text-cyan-600">{req.distance_km !== null ? `${req.distance_km} km` : 'N/A'}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5 flex items-center gap-1"><Clock className="w-3 h-3" /> ETA</p>
                                        <p className="font-medium text-slate-700 dark:text-slate-300">
                                            {req.estimated_delivery ? new Date(req.estimated_delivery).toLocaleDateString() : 'N/A'}
                                        </p>
                                    </div>
                                </div>

                                {req.address_text && (
                                    <div className="flex items-center gap-1 text-xs text-slate-400 mb-3">
                                        <MapPin className="w-3 h-3" /> {req.address_text}
                                    </div>
                                )}

                                {/* Progress Bar */}
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-400">Progress</span>
                                        <span className="font-semibold text-slate-600 dark:text-slate-400">{req.progress_pct || 0}%</span>
                                    </div>
                                    <div className="h-2 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <div
                                            className={cn('h-full rounded-full transition-all duration-700', cfg.color)}
                                            style={{ width: `${Math.max(4, req.progress_pct || 0)}%` }}
                                        />
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500">Page {page} of {totalPages}</p>
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

            {/* Confirm Status Change Modal */}
            {confirmAction && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
                            Confirm Status Change
                        </h2>
                        <p className="text-sm text-slate-500 mb-4">
                            Change status from <span className="font-semibold">{STATUS_CONFIG[confirmAction.req.status]?.label}</span> to{' '}
                            <span className="font-semibold">{STATUS_CONFIG[confirmAction.nextStatus]?.label}</span>?
                        </p>
                        <div className="mb-4">
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Notes (optional)</label>
                            <textarea value={actionNote} onChange={e => setActionNote(e.target.value)} rows={2}
                                placeholder="Add delivery notes..."
                                className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-orange-500 focus:outline-none resize-none" />
                        </div>
                        {statusMutation.error && (
                            <div className="mb-3 p-2 rounded-lg bg-red-50 dark:bg-red-500/10 text-xs text-red-600 font-medium">
                                {(statusMutation.error as Error).message}
                            </div>
                        )}
                        <div className="flex gap-3">
                            <button onClick={() => { setConfirmAction(null); setActionNote('') }}
                                className="flex-1 h-10 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5">
                                Cancel
                            </button>
                            <button
                                onClick={() => statusMutation.mutate({ id: confirmAction.req.id, newStatus: confirmAction.nextStatus })}
                                disabled={statusMutation.isPending}
                                className="flex-1 h-10 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 text-white text-sm font-semibold hover:from-orange-600 hover:to-amber-600 disabled:opacity-50 flex items-center justify-center gap-2">
                                {statusMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                                Confirm
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
