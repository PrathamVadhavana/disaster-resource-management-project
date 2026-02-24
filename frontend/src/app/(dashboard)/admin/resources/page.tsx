'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
    Loader2, Search, Package, ChevronLeft, ChevronRight,
    Droplets, Utensils, HeartPulse, Home, Shirt, X,
    RefreshCw, BarChart3, User, TrendingUp
} from 'lucide-react'

const CATEGORY_ICONS: Record<string, any> = {
    Food: Utensils,
    Water: Droplets,
    Medical: HeartPulse,
    Shelter: Home,
    Clothes: Shirt,
    Clothing: Shirt,
}

const CATEGORY_COLORS: Record<string, { bg: string; text: string; gradient: string }> = {
    Food: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', gradient: 'from-amber-500 to-orange-600' },
    Water: { bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', gradient: 'from-blue-500 to-cyan-600' },
    Medical: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', gradient: 'from-red-500 to-rose-600' },
    Shelter: { bg: 'bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400', gradient: 'from-emerald-500 to-green-600' },
    Clothes: { bg: 'bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400', gradient: 'from-purple-500 to-indigo-600' },
    Clothing: { bg: 'bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400', gradient: 'from-purple-500 to-indigo-600' },
}

export default function AdminResourcesPage() {
    const [filters, setFilters] = useState({
        category: '',
        search: '',
        page: 1,
        page_size: 20,
    })

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['admin-resources', filters],
        queryFn: () => api.getAdminAvailableResources({
            ...filters,
            category: filters.category || undefined,
            search: filters.search || undefined,
        }),
        refetchInterval: 30000,
    })

    const resources = data?.resources || []
    const total = data?.total || 0
    const categorySummary = data?.category_summary || {}
    const totalPages = Math.ceil(total / filters.page_size)

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Package className="w-6 h-6 text-emerald-500" />
                        Available Resources
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Resources contributed by NGOs, donors, and volunteers across all categories
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <RefreshCw className="w-4 h-4" />
                    Refresh
                </button>
            </div>

            {/* Category Summary Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {Object.entries(categorySummary).map(([cat, info]: [string, any]) => {
                    const Icon = CATEGORY_ICONS[cat] || Package
                    const colors = CATEGORY_COLORS[cat] || { bg: 'bg-slate-500/10', text: 'text-slate-600', gradient: 'from-slate-500 to-slate-600' }
                    const remaining = Math.max(0, (info.total || 0) - (info.claimed || 0))
                    const pct = info.total > 0 ? Math.round((remaining / info.total) * 100) : 0
                    const isActive = filters.category === cat
                    return (
                        <button
                            key={cat}
                            onClick={() => setFilters(f => ({ ...f, category: f.category === cat ? '' : cat, page: 1 }))}
                            className={cn(
                                'rounded-xl border p-4 text-left transition-all hover:shadow-md',
                                isActive
                                    ? 'border-emerald-500 dark:border-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 shadow-sm'
                                    : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]'
                            )}
                        >
                            <div className="flex items-center justify-between mb-2">
                                <div className={cn('w-9 h-9 rounded-xl bg-gradient-to-br flex items-center justify-center', colors.gradient)}>
                                    <Icon className="w-4 h-4 text-white" />
                                </div>
                                <span className="text-[10px] font-bold text-slate-400">{info.count} items</span>
                            </div>
                            <p className="text-sm font-semibold text-slate-900 dark:text-white">{cat}</p>
                            <div className="mt-2">
                                <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                                    <span>{remaining} available</span>
                                    <span>{pct}%</span>
                                </div>
                                <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                                    <div
                                        className={cn('h-full rounded-full bg-gradient-to-r transition-all', colors.gradient)}
                                        style={{ width: `${pct}%` }}
                                    />
                                </div>
                            </div>
                        </button>
                    )
                })}
            </div>

            {/* Filters */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="relative flex-1 min-w-[200px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            placeholder="Search resources by title, description..."
                            value={filters.search}
                            onChange={(e) => setFilters(f => ({ ...f, search: e.target.value, page: 1 }))}
                            className="w-full pl-9 pr-3 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                        />
                    </div>
                    {(filters.category || filters.search) && (
                        <button
                            onClick={() => setFilters({ category: '', search: '', page: 1, page_size: 20 })}
                            className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 text-sm text-slate-500 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-1.5 transition-colors"
                        >
                            <X className="w-3.5 h-3.5" />
                            Clear
                        </button>
                    )}
                </div>
            </div>

            {/* Resources Grid */}
            {isLoading ? (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
                </div>
            ) : resources.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 dark:border-white/10 p-16 text-center">
                    <Package className="w-14 h-14 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No resources found</p>
                    <p className="text-xs text-slate-500 mt-1">Try adjusting your filters or check back later</p>
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {resources.map((res: any) => {
                            const Icon = CATEGORY_ICONS[res.category] || Package
                            const colors = CATEGORY_COLORS[res.category] || { bg: 'bg-slate-500/10', text: 'text-slate-600', gradient: 'from-slate-500 to-slate-600' }
                            const remaining = res.remaining_quantity || 0
                            const total = res.total_quantity || 0
                            const claimed = res.claimed_quantity || 0
                            const pct = total > 0 ? Math.round((remaining / total) * 100) : 0
                            return (
                                <div key={res.resource_id || res.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg hover:border-slate-300 dark:hover:border-white/20 transition-all group">
                                    {/* Header */}
                                    <div className="flex items-start justify-between mb-3">
                                        <div className="flex items-center gap-3">
                                            <div className={cn('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center shrink-0', colors.gradient)}>
                                                <Icon className="w-5 h-5 text-white" />
                                            </div>
                                            <div className="min-w-0">
                                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white truncate">{res.title}</h3>
                                                <p className="text-[11px] text-slate-500 capitalize">{res.category} · {res.resource_type}</p>
                                            </div>
                                        </div>
                                        <span className={cn(
                                            'text-[10px] font-bold px-2 py-0.5 rounded-full',
                                            res.status === 'available'
                                                ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400'
                                                : 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
                                        )}>
                                            {res.status}
                                        </span>
                                    </div>

                                    {/* Description */}
                                    {res.description && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mb-3 line-clamp-2">{res.description}</p>
                                    )}

                                    {/* Quantity bar */}
                                    <div className="mb-3">
                                        <div className="flex items-center justify-between text-[11px] mb-1">
                                            <span className="text-slate-500">{remaining} of {total} {res.unit} remaining</span>
                                            <span className={cn('font-bold', pct > 50 ? 'text-emerald-600' : pct > 20 ? 'text-amber-600' : 'text-red-600')}>{pct}%</span>
                                        </div>
                                        <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                                            <div
                                                className={cn(
                                                    'h-full rounded-full transition-all bg-gradient-to-r',
                                                    pct > 50 ? 'from-emerald-400 to-green-500' : pct > 20 ? 'from-amber-400 to-orange-500' : 'from-red-400 to-rose-500'
                                                )}
                                                style={{ width: `${pct}%` }}
                                            />
                                        </div>
                                    </div>

                                    {/* Provider & Location */}
                                    <div className="flex items-center justify-between text-xs text-slate-500 pt-3 border-t border-slate-100 dark:border-white/5">
                                        <div className="flex items-center gap-1.5">
                                            <User className="w-3 h-3" />
                                            <span className="truncate max-w-[120px]">{res.provider_name || 'Unknown'}</span>
                                            <span className={cn(
                                                'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded',
                                                res.provider_role === 'ngo' || res.provider_role_name === 'ngo'
                                                    ? 'bg-blue-100 dark:bg-blue-500/10 text-blue-600'
                                                    : 'bg-orange-100 dark:bg-orange-500/10 text-orange-600'
                                            )}>
                                                {res.provider_role || res.provider_role_name || 'unknown'}
                                            </span>
                                        </div>
                                        <span className="text-[10px] text-slate-400 truncate max-w-[120px]">{res.address_text || '—'}</span>
                                    </div>
                                </div>
                            )
                        })}
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center justify-between">
                        <p className="text-xs text-slate-500">
                            Showing {Math.min((filters.page - 1) * filters.page_size + 1, total)}–{Math.min(filters.page * filters.page_size, total)} of {total}
                        </p>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => setFilters(f => ({ ...f, page: Math.max(1, f.page - 1) }))}
                                disabled={filters.page <= 1}
                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                            >
                                <ChevronLeft className="w-4 h-4" />
                            </button>
                            <span className="text-xs font-medium text-slate-600 dark:text-slate-400 px-2">
                                Page {filters.page} of {totalPages || 1}
                            </span>
                            <button
                                onClick={() => setFilters(f => ({ ...f, page: Math.min(totalPages, f.page + 1) }))}
                                disabled={filters.page >= totalPages}
                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                            >
                                <ChevronRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
