'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import {
    Loader2, AlertTriangle, Clock, CheckCircle2, TrendingUp,
    ArrowRight, Package, Users, MapPin, Activity, ListOrdered
} from 'lucide-react'

export function NGODashboardOverview() {
    const { profile } = useAuth()

    const { data: disasters, isLoading: dLoad } = useQuery({
        queryKey: ['ngo-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 50 }),
        refetchInterval: 30000,
    })

    const { data: resources, isLoading: rLoad } = useQuery({
        queryKey: ['ngo-resources'],
        queryFn: () => api.getResources({}),
        refetchInterval: 30000,
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const criticalDisasters = activeDisasters.filter((d: any) => d.severity === 'critical')
    const availableResources = resourceList.filter((r: any) => r.status === 'available')

    const isLoading = dLoad && rLoad

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    const statCards = [
        { label: 'Active Disasters', value: activeDisasters.length, icon: AlertTriangle, iconColor: 'text-red-500', bgColor: 'from-red-500 to-red-600' },
        { label: 'Critical', value: criticalDisasters.length, icon: Activity, iconColor: 'text-orange-500', bgColor: 'from-orange-500 to-orange-600' },
        { label: 'Available Resources', value: availableResources.length, icon: Package, iconColor: 'text-blue-500', bgColor: 'from-blue-500 to-blue-600' },
        { label: 'Total Resources', value: resourceList.length, icon: TrendingUp, iconColor: 'text-emerald-500', bgColor: 'from-emerald-500 to-emerald-600' },
    ]

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                    Welcome, {profile?.organization || profile?.full_name || 'Organization'}
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Manage relief operations, track deployments, and coordinate resources.
                </p>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {statCards.map((card) => {
                    const Icon = card.icon
                    return (
                        <div key={card.label} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                            <div className="flex items-center justify-between mb-3">
                                <div className={cn('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center', card.bgColor)}>
                                    <Icon className="w-5 h-5 text-white" />
                                </div>
                            </div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{card.value}</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{card.label}</p>
                        </div>
                    )
                })}
            </div>

            {/* Critical Alert Banner */}
            {criticalDisasters.length > 0 && (
                <div className="rounded-2xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-4 flex items-start gap-3">
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

            {/* Active Disasters Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Active Disasters</h2>
                    <Link href="/ngo/live-map" className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                        View Map <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
                {activeDisasters.length ? (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {activeDisasters.slice(0, 8).map((d: any) => (
                            <div key={d.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                <div className={cn(
                                    'w-2 h-2 rounded-full shrink-0',
                                    d.severity === 'critical' ? 'bg-red-500' : d.severity === 'high' ? 'bg-orange-500' : d.severity === 'medium' ? 'bg-amber-500' : 'bg-green-500'
                                )} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{d.title || 'Untitled'}</p>
                                    <div className="flex items-center gap-2 mt-0.5">
                                        <span className="text-xs text-slate-400 capitalize">{d.type}</span>
                                        {d.location_name && (
                                            <span className="text-xs text-slate-400 flex items-center gap-0.5"><MapPin className="w-3 h-3" />{d.location_name}</span>
                                        )}
                                    </div>
                                </div>
                                <span className={cn(
                                    'text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset',
                                    d.severity === 'critical' ? 'bg-red-500/10 text-red-600 ring-red-500/20' :
                                    d.severity === 'high' ? 'bg-orange-500/10 text-orange-600 ring-orange-500/20' :
                                    d.severity === 'medium' ? 'bg-amber-500/10 text-amber-600 ring-amber-500/20' :
                                    'bg-green-500/10 text-green-600 ring-green-500/20'
                                )}>
                                    {d.severity}
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="p-10 text-center text-sm text-slate-400">No active disasters currently</div>
                )}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link href="/ngo/requests" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
                    <ListOrdered className="w-6 h-6 text-blue-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Requests Queue</h4>
                    <p className="text-xs text-slate-500 mt-1">View and fulfill pending resource requests from victims.</p>
                    <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/ngo/inventory" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-md transition-all">
                    <Package className="w-6 h-6 text-emerald-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Manage Inventory</h4>
                    <p className="text-xs text-slate-500 mt-1">Track and update available supplies and resources.</p>
                    <div className="flex items-center gap-1 text-xs text-emerald-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/ngo/live-map" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <MapPin className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Deployment Map</h4>
                    <p className="text-xs text-slate-500 mt-1">View deployment zones, disaster locations, and resource distribution.</p>
                    <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">Open <ArrowRight className="w-3 h-3" /></div>
                </Link>
            </div>
        </div>
    )
}
