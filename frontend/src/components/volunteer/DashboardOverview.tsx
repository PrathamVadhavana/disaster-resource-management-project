'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import {
    Loader2, MapPin, Shield, Clock, CheckCircle2,
    ArrowRight, AlertTriangle, Zap, Award, HandHeart, ClipboardList
} from 'lucide-react'

export function VolunteerDashboardOverview() {
    const { profile } = useAuth()

    const { data: disasters, isLoading: dLoad } = useQuery({
        queryKey: ['volunteer-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 20 }),
        refetchInterval: 30000,
    })

    // Fetch volunteer certifications to show deployment readiness
    const { data: certifications = [] } = useQuery({
        queryKey: ['volunteer-certifications'],
        queryFn: () => api.getCertifications(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const criticalDisasters = activeDisasters.filter((d: any) => d.severity === 'critical' || d.severity === 'high')

    // Compute volunteer status from profile metadata
    const volunteerStatus = profile?.metadata?.availability || 'Available'
    const activeCerts = Array.isArray(certifications) ? certifications.filter((c: any) => c.status === 'active').length : 0

    if (dLoad) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    const statCards = [
        { label: 'Active Disasters', value: activeDisasters.length, icon: AlertTriangle, bgColor: 'from-red-500 to-orange-600' },
        { label: 'Urgent Need', value: criticalDisasters.length, icon: Zap, bgColor: 'from-amber-500 to-orange-600' },
        { label: 'Status', value: volunteerStatus, icon: Shield, bgColor: 'from-emerald-500 to-teal-600' },
        { label: 'Certifications', value: activeCerts, icon: Award, bgColor: 'from-purple-500 to-indigo-600' },
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
                        <div className="flex items-center gap-3 mt-3">
                            <div className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                                <span className="text-sm font-medium">Available</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Active Disaster Zones */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Active Disaster Zones</h2>
                    <Link href="/volunteer/deployments" className="text-sm text-purple-600 dark:text-purple-400 hover:underline flex items-center gap-1">
                        View Map <ArrowRight className="w-3.5 h-3.5" />
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

            {/* Quick Actions */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link href="/volunteer/assignments" className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 hover:border-purple-300 dark:hover:border-purple-500/30 hover:shadow-md transition-all">
                    <ClipboardList className="w-6 h-6 text-purple-500 mb-2" />
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white">My Assignments</h4>
                    <p className="text-xs text-slate-500 mt-1">View your current and past deployment assignments.</p>
                    <div className="flex items-center gap-1 text-xs text-purple-500 mt-3 group-hover:translate-x-1 transition-transform">View <ArrowRight className="w-3 h-3" /></div>
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
