'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getResourceRequests, type ResourceRequest, type RequestFilters } from '@/lib/api/victim'
import { StatusBadge, PriorityBadge, ResourceTypeIcon } from './StatusBadge'
import { UrgencyTags, ConfidenceBadge } from './UrgencyTags'
import { cn } from '@/lib/utils'
import { Search, Filter, ChevronLeft, ChevronRight, Loader2, Plus, X, Sparkles } from 'lucide-react'
import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'

const STATUSES = ['pending', 'approved', 'assigned', 'in_progress', 'completed', 'rejected']
const TYPES = ['Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Financial Aid', 'Evacuation', 'Volunteers', 'Custom', 'Multiple']
const PRIORITIES = ['critical', 'high', 'medium', 'low']

/** Debounce hook — only updates value after delay */
function useDebouncedValue<T>(value: T, delayMs: number): T {
    const [debounced, setDebounced] = useState(value)
    useEffect(() => {
        const t = setTimeout(() => setDebounced(value), delayMs)
        return () => clearTimeout(t)
    }, [value, delayMs])
    return debounced
}

export function RequestList() {
    const [filters, setFilters] = useState<RequestFilters>({ page: 1, page_size: 10 })
    const [searchInput, setSearchInput] = useState('')
    const [showFilters, setShowFilters] = useState(false)

    // Debounce search by 400ms to prevent rapid re-fetching
    const debouncedSearch = useDebouncedValue(searchInput, 400)

    // Build a stable query key that includes search
    const queryKey = ['victim-requests', { ...filters, search: debouncedSearch || undefined }]

    const { data, isLoading, isFetching } = useQuery({
        queryKey,
        queryFn: () => getResourceRequests({ ...filters, search: debouncedSearch || undefined }),
        placeholderData: (prev) => prev,
        staleTime: 10_000,
        refetchOnWindowFocus: false,
    })

    const setFilter = useCallback((key: keyof RequestFilters, value: string | undefined) => {
        setFilters((f) => ({ ...f, [key]: value || undefined, page: 1 }))
    }, [])

    const clearFilters = useCallback(() => {
        setFilters({ page: 1, page_size: 10 })
        setSearchInput('')
    }, [])

    const totalPages = data ? Math.ceil(data.total / (filters.page_size || 10)) : 0
    const hasActiveFilters = filters.status || filters.resource_type || filters.priority || debouncedSearch

    const getItemLabel = (req: ResourceRequest) => {
        if (req.items?.length > 1) return `${req.items.length} resources requested`
        if (req.items?.[0]?.resource_type === 'Custom') return req.items[0].custom_name || 'Custom Resource'
        return req.resource_type
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Requests</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{data?.total ?? 0} total requests</p>
                </div>
                <div className="flex items-center gap-2">
                    <Link
                        href="/victim/requests/chatbot"
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 text-white text-sm font-semibold shadow-lg shadow-amber-500/20 hover:shadow-amber-500/30 hover:brightness-110 transition-all"
                    >
                        <Sparkles className="w-4 h-4" />
                        AI Assist
                    </Link>
                    <Link
                        href="/victim/requests/new"
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-red-500 to-orange-600 text-white text-sm font-semibold shadow-lg shadow-red-500/20 hover:shadow-red-500/30 hover:brightness-110 transition-all"
                    >
                        <Plus className="w-4 h-4" />
                        New Request
                    </Link>
                </div>
            </div>

            {/* Search + Filter toggle */}
            <div className="flex gap-3">
                <div className="flex-1 relative">
                    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                        type="text"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        placeholder="Search requests…"
                        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50"
                    />
                </div>
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className={cn(
                        'flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-medium transition-colors',
                        showFilters || hasActiveFilters
                            ? 'border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400'
                            : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5'
                    )}
                >
                    <Filter className="w-4 h-4" />
                    Filter
                </button>
            </div>

            {/* Filter panel */}
            {showFilters && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Filters</h3>
                        {hasActiveFilters && (
                            <button onClick={clearFilters} className="text-xs text-red-500 hover:underline flex items-center gap-1">
                                <X className="w-3 h-3" /> Clear all
                            </button>
                        )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Status</label>
                            <select
                                value={filters.status || ''}
                                onChange={(e) => setFilter('status', e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm"
                            >
                                <option value="">All</option>
                                {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Type</label>
                            <select
                                value={filters.resource_type || ''}
                                onChange={(e) => setFilter('resource_type', e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm"
                            >
                                <option value="">All</option>
                                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">Priority</label>
                            <select
                                value={filters.priority || ''}
                                onChange={(e) => setFilter('priority', e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm"
                            >
                                <option value="">All</option>
                                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                            </select>
                        </div>
                    </div>
                </div>
            )}

            {/* Request list */}
            {isLoading ? (
                <div className="flex items-center justify-center h-40">
                    <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
                </div>
            ) : data?.requests?.length ? (
                <div className={cn('space-y-3 transition-opacity', isFetching && 'opacity-60')}>
                    {data.requests.map((req) => (
                        <Link
                            key={req.id}
                            href={`/victim/requests/${req.id}`}
                            className="block rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4 hover:border-red-200 dark:hover:border-red-500/20 hover:shadow-sm transition-all"
                        >
                            <div className="flex items-start gap-4">
                                <ResourceTypeIcon type={req.resource_type} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-start justify-between gap-2">
                                        <div>
                                            <p className="font-semibold text-slate-900 dark:text-white">{getItemLabel(req)}</p>
                                            {req.items?.length > 1 && (
                                                <div className="flex flex-wrap gap-1.5 mt-1.5">
                                                    {req.items.map((it, i) => (
                                                        <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/5 text-xs text-slate-600 dark:text-slate-400">
                                                            {it.resource_type === 'Custom' ? it.custom_name : it.resource_type} ×{it.quantity}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                            {(!req.items || req.items.length <= 1) && (
                                                <p className="text-xs text-slate-400 mt-0.5">Qty: {req.quantity}</p>
                                            )}
                                        </div>
                                        <StatusBadge status={req.status} />
                                    </div>
                                    <div className="flex items-center gap-3 mt-2">
                                        <PriorityBadge priority={req.priority} />
                                        {(req as any).ai_confidence != null && (
                                            <ConfidenceBadge confidence={(req as any).ai_confidence} />
                                        )}
                                        <span suppressHydrationWarning className="text-xs text-slate-400">
                                            {formatDistanceToNow(new Date(req.created_at), { addSuffix: true })}
                                        </span>
                                    </div>
                                    {/* Urgency signal tags */}
                                    {(req as any).urgency_signals?.length > 0 && (
                                        <div className="mt-2">
                                            <UrgencyTags signals={(req as any).urgency_signals} max={3} />
                                        </div>
                                    )}
                                    {req.description && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 line-clamp-1">
                                            {req.description}
                                        </p>
                                    )}
                                </div>
                            </div>
                        </Link>
                    ))}
                </div>
            ) : (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-12 text-center">
                    <p className="text-slate-400 text-sm">No requests found</p>
                    <Link
                        href="/victim/requests/new"
                        className="inline-block mt-3 px-4 py-2 rounded-xl bg-red-500 text-white text-sm font-medium"
                    >
                        Create Request
                    </Link>
                </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between">
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                        Page {filters.page} of {totalPages}
                    </p>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setFilters((f) => ({ ...f, page: Math.max(1, (f.page || 1) - 1) }))}
                            disabled={(filters.page || 1) <= 1}
                            className="p-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                        >
                            <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                            onClick={() => setFilters((f) => ({ ...f, page: Math.min(totalPages, (f.page || 1) + 1) }))}
                            disabled={(filters.page || 1) >= totalPages}
                            className="p-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                        >
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
