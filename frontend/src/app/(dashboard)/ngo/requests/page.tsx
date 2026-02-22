'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import type { ResourceRequest } from '@/types/api'
import {
    Loader2, Clock, CheckCircle2, XCircle,
    Search, MapPin, RefreshCw, Package,
    ChevronLeft, ChevronRight,
} from 'lucide-react'

const PAGE_SIZE = 20

const STATUS_OPTIONS = ['all', 'pending', 'in_progress', 'fulfilled', 'rejected'] as const

const STATUS_CONFIG: Record<string, { label: string; icon: typeof Clock; color: string }> = {
    pending: { label: 'Pending', icon: Clock, color: 'text-amber-600 bg-amber-50 dark:bg-amber-500/10 ring-amber-500/20' },
    in_progress: { label: 'In Progress', icon: RefreshCw, color: 'text-blue-600 bg-blue-50 dark:bg-blue-500/10 ring-blue-500/20' },
    fulfilled: { label: 'Fulfilled', icon: CheckCircle2, color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 ring-emerald-500/20' },
    rejected: { label: 'Rejected', icon: XCircle, color: 'text-red-600 bg-red-50 dark:bg-red-500/10 ring-red-500/20' },
}

const PRIORITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-amber-500',
    low: 'bg-green-500',
}

export default function NGORequestsPage() {
    const queryClient = useQueryClient()
    const [statusFilter, setStatusFilter] = useState<string>('all')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)

    // Reset page when filter changes
    const handleStatusChange = useCallback((s: string) => {
        setStatusFilter(s)
        setPage(1)
    }, [])

    // Server-side paginated query
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-requests', statusFilter, page],
        queryFn: () =>
            api.getNGORequests({
                ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
                page,
                page_size: PAGE_SIZE,
            }),
    })

    const requestList: ResourceRequest[] = data?.requests ?? (Array.isArray(data) ? data as unknown as ResourceRequest[] : [])
    const totalCount = data?.total ?? requestList.length
    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))

    // Realtime subscription replaces polling
    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('ngo-requests-realtime')
            .on(
                'postgres_changes',
                { event: '*', schema: 'public', table: 'resource_requests' },
                () => {
                    // Invalidate & refetch on any change
                    queryClient.invalidateQueries({ queryKey: ['ngo-requests'] })
                }
            )
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [queryClient])

    // Client-side search filter (applies on top of server-side pagination)
    const filtered = search
        ? requestList.filter((r) =>
            (r.title || r.description || r.resource_type || '')
                .toLowerCase()
                .includes(search.toLowerCase())
        )
        : requestList

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
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Requests Queue</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        View and manage incoming resource requests from victims.
                        {totalCount > 0 && (
                            <span className="ml-1 font-medium text-slate-600 dark:text-slate-300">
                                ({totalCount} total)
                            </span>
                        )}
                    </p>
                </div>
                <button onClick={() => refetch()} className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search requests..."
                        className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                    />
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1">
                    {STATUS_OPTIONS.map((s) => (
                        <button
                            key={s}
                            onClick={() => handleStatusChange(s)}
                            className={cn(
                                'px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all border',
                                statusFilter === s
                                    ? 'bg-blue-600 text-white border-blue-600'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5'
                            )}
                        >
                            {s === 'all' ? 'All' : s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </button>
                    ))}
                </div>
            </div>

            {/* Request Cards */}
            {filtered.length === 0 ? (
                <div className="text-center py-16 px-4">
                    <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 dark:text-slate-400 font-medium">No requests found</p>
                    <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                        {search ? 'Try adjusting your search.' : 'There are no requests matching this filter.'}
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {filtered.map((req) => {
                        const status = STATUS_CONFIG[req.status] || STATUS_CONFIG.pending
                        const StatusIcon = status.icon
                        return (
                            <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-md transition-all">
                                <div className="flex items-start gap-4">
                                    {/* Priority dot */}
                                    <div className={cn('w-2.5 h-2.5 rounded-full mt-2 shrink-0', PRIORITY_COLORS[req.priority] || 'bg-slate-400')} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                                {req.title || req.resource_type || 'Resource Request'}
                                            </h3>
                                            <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset', status.color)}>
                                                <StatusIcon className="w-3 h-3 inline mr-1" />
                                                {status.label}
                                            </span>
                                            {req.priority && (
                                                <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 capitalize">
                                                    {req.priority}
                                                </span>
                                            )}
                                        </div>
                                        {req.description && (
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 line-clamp-2">{req.description}</p>
                                        )}
                                        <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                                            {req.location_name && (
                                                <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{req.location_name}</span>
                                            )}
                                            {req.resource_type && (
                                                <span className="flex items-center gap-1"><Package className="w-3 h-3" />{req.resource_type}</span>
                                            )}
                                            {req.quantity && <span>Qty: {req.quantity}</span>}
                                            {req.created_at && (
                                                <span>{new Date(req.created_at).toLocaleDateString()}</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Pagination Controls */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Page {page} of {totalPages}
                    </p>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronLeft className="w-3.5 h-3.5" /> Previous
                        </button>
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            Next <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
