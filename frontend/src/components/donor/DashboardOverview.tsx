'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import {
    Loader2, Heart, TrendingUp, Globe, DollarSign,
    ArrowRight, Target, BarChart3, Sparkles, Users
} from 'lucide-react'

export function DonorDashboardOverview() {
    const { profile } = useAuth()

    const { data: disasters, isLoading: dLoad } = useQuery({
        queryKey: ['donor-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 20 }),
        refetchInterval: 60000,
    })

    const { data: urgentNeeds, isLoading: uLoad } = useQuery({
        queryKey: ['donor-urgent-needs'],
        queryFn: () => api.getUrgentNeeds(),
        refetchInterval: 60000,
    })

    // Fetch real donor stats from backend
    const { data: donorStats } = useQuery({
        queryKey: ['donor-stats'],
        queryFn: () => api.getDonorStats(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const needsList = Array.isArray(urgentNeeds) ? urgentNeeds : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')

    const isLoading = dLoad

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    const statCards = [
        { label: 'Active Crises', value: activeDisasters.length, icon: Globe, bgColor: 'from-red-500 to-orange-600' },
        { label: 'Urgent Needs', value: needsList.length, icon: Target, bgColor: 'from-amber-500 to-orange-600' },
        { label: 'Your Donations', value: donorStats?.completed_donations ?? 0, icon: Heart, bgColor: 'from-emerald-500 to-teal-600' },
        { label: 'Impact Score', value: donorStats?.impact_score ?? 0, icon: Sparkles, bgColor: 'from-purple-500 to-indigo-600' },
    ]

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                    Welcome, {profile?.full_name || 'Donor'}
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Your generosity makes a difference. Track your impact and discover new causes.
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

            {/* Impact Banner */}
            <div className="rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 p-6 text-white">
                <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
                        <Heart className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-lg font-bold">Make a Difference Today</h3>
                        <p className="text-sm text-emerald-100 mt-1">
                            {activeDisasters.length > 0
                                ? `There are ${activeDisasters.length} active disasters needing support. Your contribution can save lives.`
                                : 'There are currently no active disasters, but your contributions help build resilience for future emergencies.'}
                        </p>
                        <Link href="/donor/causes" className="inline-flex items-center gap-1 mt-3 text-sm font-semibold bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition-colors">
                            Discover Causes <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </div>
            </div>

            {/* Active Crises */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Active Crises Needing Support</h2>
                </div>
                {activeDisasters.length ? (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {activeDisasters.slice(0, 6).map((d: any) => (
                            <div key={d.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                <div className={cn(
                                    'w-2 h-2 rounded-full shrink-0',
                                    d.severity === 'critical' ? 'bg-red-500 animate-pulse' : d.severity === 'high' ? 'bg-orange-500' : 'bg-amber-500'
                                )} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{d.title || 'Untitled Crisis'}</p>
                                    <p className="text-xs text-slate-400 capitalize mt-0.5">{d.type} · {d.severity}</p>
                                </div>
                                <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 rounded-full">
                                    Needs help
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="p-10 text-center text-sm text-slate-400">No active crises at the moment</div>
                )}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link href="/donor/donations" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-md transition-all">
                    <DollarSign className="w-6 h-6 text-emerald-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Donation History</h4>
                    <p className="text-xs text-slate-500 mt-1">View your past donations and their impact on relief efforts.</p>
                    <div className="flex items-center gap-1 text-xs text-emerald-500 mt-3 group-hover:translate-x-1 transition-transform">View <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/donor/impact" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <BarChart3 className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Impact Report</h4>
                    <p className="text-xs text-slate-500 mt-1">See how your contributions have helped communities recover.</p>
                    <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">View <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/donor/causes" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
                    <Users className="w-6 h-6 text-blue-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Discover Causes</h4>
                    <p className="text-xs text-slate-500 mt-1">Find verified NGOs and relief programs to support.</p>
                    <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">Explore <ArrowRight className="w-3 h-3" /></div>
                </Link>
            </div>
        </div>
    )
}
