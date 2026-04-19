'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import {
    Loader2, MapPin, Shield, Clock, CheckCircle2,
    ArrowRight, AlertTriangle, Zap, Award, HandHeart,
    ClipboardList, ShieldCheck, Rocket, PackageCheck, Truck
} from 'lucide-react'
import { VerificationHub } from './VerificationHub'

export function VolunteerDashboardOverview() {
    const { profile } = useAuth()

    const { data: disasters, isLoading: dLoad, isError: dError } = useQuery({
        queryKey: ['volunteer-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 20 }),
        refetchInterval: 30000,
    })

    const { data: volunteerStats, isLoading: vStatsLoad } = useQuery({
        queryKey: ['volunteer-stats'],
        queryFn: () => api.getVolunteerStats(),
    })

    const { data: activeDeploymentData } = useQuery({
        queryKey: ['active-deployment'],
        queryFn: () => api.getActiveDeployment(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const criticalDisasters = activeDisasters.filter((d: any) => d.severity === 'critical' || d.severity === 'high')

    const activeCerts = volunteerStats?.certifications_count || 0
    const activeDeployment = activeDeploymentData?.active_deployment

    if (dError) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <AlertTriangle className="w-10 h-10 text-amber-500" />
                <p className="text-sm text-slate-500">Unable to load dashboard data.</p>
                <button onClick={() => window.location.reload()} className="text-sm text-blue-500 hover:underline">Retry</button>
            </div>
        )
    }

    if (dLoad || vStatsLoad) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    const statCards = [
        { label: 'Impact Score',       value: volunteerStats?.impact_score || 0,              icon: Zap,          bgColor: 'from-amber-400 to-orange-500' },
        { label: 'Hours Contributed',  value: volunteerStats?.total_hours_contributed || 0,   icon: Clock,        bgColor: 'from-blue-500 to-blue-600' },
        { label: 'Deployments',        value: volunteerStats?.completed_deployments || 0,     icon: Rocket,       bgColor: 'from-emerald-500 to-emerald-600' },
        { label: 'Certifications',     value: activeCerts,                                     icon: Award,        bgColor: 'from-purple-500 to-indigo-600' },
        { label: 'Deliveries Done',    value: volunteerStats?.completed_deliveries || 0,      icon: PackageCheck, bgColor: 'from-teal-500 to-cyan-600' },
        { label: 'Total Tasks',        value: volunteerStats?.total_delivery_tasks || 0,      icon: Truck,        bgColor: 'from-slate-500 to-slate-600' },
    ]

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                    Welcome, {profile?.full_name || 'Volunteer'}
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Thank you for volunteering. Here's your mission briefing.
                </p>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
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

            {/* Active deployment banner */}
            {activeDeployment && (
                <div className="rounded-2xl bg-blue-600 text-white p-5">
                    <div className="flex items-center gap-3">
                        <span className="w-2.5 h-2.5 rounded-full bg-white animate-pulse shrink-0" />
                        <div>
                            <p className="font-semibold text-sm">Currently Deployed</p>
                            <p className="text-blue-100 text-sm">{activeDeployment.task_description || 'General volunteer support'}</p>
                        </div>
                        <Link href="/volunteer/deployments" className="ml-auto px-3 py-1.5 rounded-lg bg-white/20 hover:bg-white/30 text-sm font-medium transition-colors">
                            View
                        </Link>
                    </div>
                </div>
            )}

            {/* Readiness Banner */}
            <div className="rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 p-6 text-white">
                <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
                        <HandHeart className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-lg font-bold">Your Readiness Status</h3>
                        <p className="text-sm text-purple-100 mt-1">
                            {criticalDisasters.length > 0
                                ? `${criticalDisasters.length} high-priority disaster${criticalDisasters.length > 1 ? 's' : ''} need volunteers. Stand by for deployment.`
                                : 'No urgent deployments at this time. Keep your profile and certifications up to date.'}
                        </p>
                        <div className="flex items-center gap-1.5 mt-3">
                            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                            <span className="text-sm font-medium">Available</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Active Disaster Zones */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Active Disaster Zones</h2>
                    <Link href="/volunteer/deployments" className="text-sm text-purple-600 dark:text-purple-400 hover:underline flex items-center gap-1">
                        View History <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
                {activeDisasters.length ? (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {activeDisasters.slice(0, 8).map((d: any) => (
                            <div key={d.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                <div className={cn(
                                    'w-2 h-2 rounded-full shrink-0',
                                    d.severity === 'critical' ? 'bg-red-500 animate-pulse' : d.severity === 'high' ? 'bg-orange-500' : d.severity === 'medium' ? 'bg-amber-500' : 'bg-green-500'
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
                                    'text-[10px] px-2 py-0.5 rounded-full font-semibold',
                                    d.severity === 'critical' || d.severity === 'high'
                                        ? 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400'
                                        : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
                                )}>
                                    {d.severity === 'critical' || d.severity === 'high' ? 'Volunteers Needed' : d.severity}
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="p-10 text-center text-sm text-slate-400">No active disasters at the moment</div>
                )}
            </div>

            {/* Field Verification Hub */}
            <VerificationHub />

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <Link href="/volunteer/assignments" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <ClipboardList className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Available Tasks</h4>
                    <p className="text-xs text-slate-500 mt-1">Browse and accept delivery tasks from approved victim requests.</p>
                    <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">Browse <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/volunteer/deliveries" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-teal-300 dark:hover:border-teal-500/30 hover:shadow-md transition-all">
                    <PackageCheck className="w-6 h-6 text-teal-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">My Deliveries</h4>
                    <p className="text-xs text-slate-500 mt-1">Track and update status of your accepted delivery tasks.</p>
                    <div className="flex items-center gap-1 text-xs text-teal-500 mt-3 group-hover:translate-x-1 transition-transform">Track <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/volunteer/certifications" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-amber-300 dark:hover:border-amber-500/30 hover:shadow-md transition-all">
                    <Award className="w-6 h-6 text-amber-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Certifications</h4>
                    <p className="text-xs text-slate-500 mt-1">Manage your skills and certifications for deployment matching.</p>
                    <div className="flex items-center gap-1 text-xs text-amber-500 mt-3 group-hover:translate-x-1 transition-transform">Manage <ArrowRight className="w-3 h-3" /></div>
                </Link>
                <Link href="/volunteer/profile" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-blue-300 dark:hover:border-blue-500/30 hover:shadow-md transition-all">
                    <Shield className="w-6 h-6 text-blue-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Update Availability</h4>
                    <p className="text-xs text-slate-500 mt-1">Set your availability status and deployment preferences.</p>
                    <div className="flex items-center gap-1 text-xs text-blue-500 mt-3 group-hover:translate-x-1 transition-transform">Update <ArrowRight className="w-3 h-3" /></div>
                </Link>
            </div>
        </div>
    )
}