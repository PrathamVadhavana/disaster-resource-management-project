'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import { useState, useEffect } from 'react'
import { subscribeToTable } from '@/lib/realtime'
import {
    Loader2, AlertTriangle, Clock, CheckCircle2, TrendingUp,
    ArrowRight, Package, MapPin, Activity, ListOrdered,
    Truck, Building2, Target, Route, Bell, Timer, Zap,
} from 'lucide-react'

const STATUS_COLORS: Record<string, string> = {
    approved: 'bg-blue-500',
    availability_submitted: 'bg-purple-500',
    under_review: 'bg-indigo-500',
    assigned: 'bg-orange-500',
    in_progress: 'bg-yellow-500',
    delivered: 'bg-green-500',
    completed: 'bg-emerald-700',
    closed: 'bg-slate-500',
    urgent: 'bg-red-500',
}

const STATUS_LABELS: Record<string, string> = {
    approved: 'Approved',
    availability_submitted: 'Availability Submitted',
    under_review: 'Under Review',
    assigned: 'Assigned',
    in_progress: 'In Progress',
    delivered: 'Delivered',
    completed: 'Completed',
    closed: 'Closed',
}

export function NGODashboardOverview() {
    const { profile } = useAuth()
    const [mounted, setMounted] = useState(false)
    useEffect(() => { setMounted(true) }, [])

    const { data: stats, isLoading: sLoad, isError: sError } = useQuery({
        queryKey: ['ngo-enhanced-stats'],
        queryFn: () => api.getNgoStats(),
        refetchInterval: 15000,
    })

    const { data: auditData, isLoading: aLoad } = useQuery({
        queryKey: ['ngo-recent-activity'],
        queryFn: () => api.getNgoAuditLog({ limit: 8 }),
        refetchInterval: 20000,
    })

    const { data: notifData, isLoading: nLoad } = useQuery({
        queryKey: ['ngo-notifications-feed'],
        queryFn: () => api.getNgoNotifications({ limit: 10 }),
        refetchInterval: 10000,
    })

    const { data: disasters } = useQuery({
        queryKey: ['ngo-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 50 }),
        refetchInterval: 30000,
    })

    // Realtime sync
    useEffect(() => {
        const unsub1 = subscribeToTable('resource_requests', () => {
            // Will trigger re-renders via React Query
        })
        const unsub2 = subscribeToTable('notifications', () => {
            // Notification sound/visual
        })
        return () => { unsub1(); unsub2() }
    }, [])

    const disasterList = Array.isArray(disasters) ? disasters : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const criticalDisasters = activeDisasters.filter((d: any) => d.severity === 'critical')
    const recentActivity = auditData?.entries || []
    const notifications = notifData?.notifications || []
    const unreadCount = notifData?.unread_count || 0

    const isLoading = sLoad

    if (sError) {
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
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 flex items-center justify-center animate-pulse">
                        <Building2 className="w-8 h-8 text-blue-500" />
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 text-slate-400 animate-spin" />
                    <span className="text-sm text-slate-500">Loading dashboard...</span>
                </div>
            </div>
        )
    }

    const kpiCards = [
        { label: 'Approved Requests', value: stats?.total_approved || 0, icon: ListOrdered, bgColor: 'from-blue-500 to-blue-600', desc: 'Available to fulfill' },
        { label: 'Availability Submitted', value: stats?.availability_submitted || 0, icon: Target, bgColor: 'from-purple-500 to-purple-600', desc: 'Pending admin review' },
        { label: 'Assigned to You', value: stats?.assigned || 0, icon: CheckCircle2, bgColor: 'from-orange-500 to-orange-600', desc: 'Ready for action' },
        { label: 'Active Deliveries', value: stats?.active_deliveries || 0, icon: Truck, bgColor: 'from-amber-500 to-yellow-600', desc: 'Currently in transit' },
        { label: 'Completed', value: stats?.completed || 0, icon: CheckCircle2, bgColor: 'from-emerald-500 to-emerald-600', desc: 'Successfully delivered' },
        { label: 'Urgent Requests', value: stats?.urgent_requests || 0, icon: Zap, bgColor: 'from-red-500 to-red-600', desc: 'Critical + High priority' },
        { label: 'Avg Response Time', value: `${stats?.avg_response_time_hours || 0}h`, icon: Timer, bgColor: 'from-indigo-500 to-indigo-600', desc: 'Average hours to respond' },
        { label: 'Total Distance', value: `${stats?.total_distance_km || 0} km`, icon: Route, bgColor: 'from-cyan-500 to-teal-600', desc: 'Cumulative coverage' },
    ]

    // Status distribution data
    const statusData = stats?.by_status || {}
    const totalByStatus = Object.values(statusData as Record<string, number>).reduce((a: number, b: number) => a + b, 0)

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                        Welcome, {profile?.organization || profile?.full_name || 'Organization'}
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Manage relief operations, track deployments, and coordinate resources in real-time.
                    </p>
                </div>
                {unreadCount > 0 && (
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                        <Bell className="w-4 h-4 text-red-500" />
                        <span className="text-xs font-semibold text-red-600 dark:text-red-400">{unreadCount} new</span>
                    </div>
                )}
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {kpiCards.map((card) => {
                    const Icon = card.icon
                    return (
                        <div key={card.label} className="group rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg hover:border-slate-300 dark:hover:border-white/20 transition-all duration-300">
                            <div className="flex items-center justify-between mb-3">
                                <div className={cn('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform', card.bgColor)}>
                                    <Icon className="w-5 h-5 text-white" />
                                </div>
                            </div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{card.value}</p>
                            <p className="text-xs font-medium text-slate-600 dark:text-slate-400 mt-0.5">{card.label}</p>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">{card.desc}</p>
                        </div>
                    )
                })}
            </div>

            {/* Critical Alert Banner */}
            {criticalDisasters.length > 0 && (
                <div className="rounded-2xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-4 flex items-start gap-3 animate-pulse">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
                    <div className="flex-1">
                        <p className="text-sm font-semibold text-red-800 dark:text-red-300">
                            {criticalDisasters.length} critical disaster{criticalDisasters.length > 1 ? 's' : ''} requiring immediate attention
                        </p>
                        <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                            Deploy resources and coordinate relief immediately.
                        </p>
                    </div>
                    <Link href="/ngo/requests" className="shrink-0 text-sm font-medium text-red-600 dark:text-red-400 hover:underline flex items-center gap-1">
                        View <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Status Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <h2 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Activity className="w-4 h-4 text-blue-500" /> Status Distribution
                    </h2>
                    {totalByStatus > 0 ? (
                        <div className="space-y-3">
                            {Object.entries(statusData as Record<string, number>).map(([status, count]) => (
                                <div key={status} className="space-y-1">
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="font-medium text-slate-600 dark:text-slate-400">{STATUS_LABELS[status] || status}</span>
                                        <span className="text-slate-500">{count}</span>
                                    </div>
                                    <div className="h-2 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <div
                                            className={cn('h-full rounded-full transition-all duration-700', STATUS_COLORS[status] || 'bg-slate-400')}
                                            style={{ width: `${Math.max(4, (Number(count) / totalByStatus) * 100)}%` }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-sm text-slate-400 text-center py-6">No assigned requests yet</p>
                    )}
                </div>

                {/* Recent Activity Timeline */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <h2 className="font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-purple-500" /> Recent Activity
                    </h2>
                    {recentActivity.length > 0 ? (
                        <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                            {recentActivity.map((entry: any, idx: number) => (
                                <div key={entry.id || idx} className="flex items-start gap-3 group">
                                    <div className="w-2 h-2 rounded-full bg-blue-500 mt-2 shrink-0 group-hover:scale-150 transition-transform" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{entry.description || entry.action_type}</p>
                                        <p className="text-[10px] text-slate-400 mt-0.5">
                                            {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-sm text-slate-400 text-center py-6">No activity recorded yet</p>
                    )}
                </div>
            </div>

            {/* Notification Feed */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                        <Bell className="w-4 h-4 text-amber-500" /> Notifications
                        {unreadCount > 0 && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-red-500 text-white">{unreadCount}</span>
                        )}
                    </h2>
                </div>
                {notifications.length > 0 ? (
                    <div className="divide-y divide-slate-100 dark:divide-white/5 max-h-64 overflow-y-auto">
                        {notifications.map((n: any) => (
                            <div key={n.id} className={cn(
                                'flex items-start gap-3 px-5 py-3 transition-colors',
                                !n.read ? 'bg-blue-50/50 dark:bg-blue-500/5' : 'hover:bg-slate-50 dark:hover:bg-white/[0.02]'
                            )}>
                                <div className={cn('w-2 h-2 rounded-full mt-2 shrink-0', !n.read ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600')} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-slate-800 dark:text-slate-200">{n.title}</p>
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{n.message}</p>
                                    <p className="text-[10px] text-slate-400 mt-1">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</p>
                                </div>
                                {n.priority === 'critical' && (
                                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/10 text-red-600 font-bold">URGENT</span>
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="p-8 text-center text-sm text-slate-400">No notifications yet</div>
                )}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link href="/ngo/requests" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
                    <ListOrdered className="w-6 h-6 text-blue-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Approved Requests</h4>
                    <p className="text-xs text-slate-500 mt-1">View approved requests and submit your availability.</p>
                    <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/ngo/inventory" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-md transition-all">
                    <Package className="w-6 h-6 text-emerald-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Manage Inventory</h4>
                    <p className="text-xs text-slate-500 mt-1">Track available, reserved, and low-stock resources.</p>
                    <div className="flex items-center gap-1 text-xs text-emerald-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/ngo/deliveries" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <Truck className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Delivery Tracking</h4>
                    <p className="text-xs text-slate-500 mt-1">Monitor active deliveries and update progress.</p>
                    <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
            </div>
        </div>
    )
}
