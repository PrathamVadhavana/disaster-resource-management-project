'use client'

import { useQuery } from '@tanstack/react-query'
import { getDashboardStats, getResourceRequests, type DashboardStats } from '@/lib/api/victim'
import { StatusBadge, PriorityBadge, ResourceTypeIcon } from './StatusBadge'
import { cn } from '@/lib/utils'
import { Loader2, AlertTriangle, Clock, CheckCircle2, TrendingUp, ArrowRight } from 'lucide-react'
import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'

export function DashboardOverview() {
    const { data: stats, isLoading: statsLoading } = useQuery<DashboardStats>({
        queryKey: ['victim-stats'],
        queryFn: getDashboardStats,
    })

    const { data: recentData } = useQuery({
        queryKey: ['victim-requests', { page: 1, page_size: 5, sort_by: 'created_at', sort_order: 'desc' }],
        queryFn: () => getResourceRequests({ page: 1, page_size: 5, sort_by: 'created_at', sort_order: 'desc' }),
    })

    if (statsLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    const statCards = [
        { label: 'Total Requests', value: stats?.total_requests || 0, icon: TrendingUp, iconColor: 'text-blue-500' },
        { label: 'Pending', value: stats?.pending || 0, icon: Clock, iconColor: 'text-amber-500' },
        { label: 'In Progress', value: (stats?.assigned || 0) + (stats?.in_progress || 0), icon: AlertTriangle, iconColor: 'text-purple-500' },
        { label: 'Completed', value: stats?.completed || 0, icon: CheckCircle2, iconColor: 'text-emerald-500' },
    ]

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Dashboard Overview</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Track your resource requests and status</p>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {statCards.map((card) => {
                    const Icon = card.icon
                    return (
                        <div
                            key={card.label}
                            className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5"
                        >
                            <div className="flex items-center justify-between mb-3">
                                <Icon className={cn('w-5 h-5', card.iconColor)} />
                            </div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{card.value}</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{card.label}</p>
                        </div>
                    )
                })}
            </div>

            {/* Urgent alert */}
            {(stats?.pending || 0) > 0 && (
                <div className="rounded-2xl border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/5 p-4 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                    <div>
                        <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                            {stats!.pending} request{stats!.pending > 1 ? 's' : ''} pending review
                        </p>
                        <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                            Your requests are awaiting approval from relief coordinators.
                        </p>
                    </div>
                </div>
            )}

            {/* Recent Requests */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Recent Requests</h2>
                    <Link
                        href="/victim/requests"
                        className="text-sm text-red-600 dark:text-red-400 hover:underline flex items-center gap-1"
                    >
                        View All <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
                {recentData?.requests?.length ? (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {recentData.requests.map((req) => (
                            <Link
                                key={req.id}
                                href={`/victim/requests/${req.id}`}
                                className="flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors"
                            >
                                <ResourceTypeIcon type={req.resource_type} size="sm" />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium text-slate-900 dark:text-white">
                                            {req.items?.length > 1
                                                ? `${req.items.length} resources`
                                                : req.items?.[0]?.resource_type === 'Custom'
                                                    ? req.items[0].custom_name || 'Custom'
                                                    : req.resource_type}
                                        </span>
                                        <PriorityBadge priority={req.priority} />
                                    </div>
                                    <p className="text-xs text-slate-400 mt-0.5">
                                        {formatDistanceToNow(new Date(req.created_at), { addSuffix: true })}
                                    </p>
                                </div>
                                <StatusBadge status={req.status} />
                            </Link>
                        ))}
                    </div>
                ) : (
                    <div className="p-10 text-center">
                        <p className="text-slate-400 text-sm">No requests yet</p>
                        <Link
                            href="/victim/requests/new"
                            className="inline-block mt-3 px-4 py-2 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors"
                        >
                            Create First Request
                        </Link>
                    </div>
                )}
            </div>

            {/* Resources by Type */}
            {stats?.by_type && Object.keys(stats.by_type).length > 0 && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Requests by Type</h2>
                    </div>
                    <div className="p-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                        {Object.entries(stats.by_type).map(([type, count]) => (
                            <div key={type} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                <ResourceTypeIcon type={type} size="sm" />
                                <div>
                                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{count}</p>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">{type}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
