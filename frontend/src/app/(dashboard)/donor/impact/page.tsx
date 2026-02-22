'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    TrendingUp, Users, Heart, Globe, Loader2,
    BarChart3, Target, Shield, ArrowUpRight
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend } from 'recharts'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

export default function DonorImpactPage() {
    // Fetch donations from backend API
    const { data: donations = [], isLoading: donLoading } = useQuery<any[]>({
        queryKey: ['donor-donations'],
        queryFn: () => api.getDonations(),
    })

    const { data: disasters, isLoading: dLoading } = useQuery({
        queryKey: ['donor-impact-disasters'],
        queryFn: () => api.getDisasters(),
    })
    const { data: resources, isLoading: rLoading } = useQuery({
        queryKey: ['donor-impact-resources'],
        queryFn: () => api.getResources(),
    })
    const { data: requests } = useQuery({
        queryKey: ['donor-impact-requests'],
        queryFn: () => api.getNGORequests(),
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const requestList = Array.isArray(requests) ? requests : []

    const completedDonations = donations.filter(d => d.status === 'completed')
    const totalDonated = completedDonations.reduce((sum, d) => sum + (d.amount || 0), 0)

    // Compute real impact metrics
    const metrics = useMemo(() => {
        const activeDisasters = disasterList.filter((d: any) => d.status === 'active').length
        const resolvedDisasters = disasterList.filter((d: any) => d.status === 'resolved').length
        const totalResources = resourceList.length
        const allocatedResources = resourceList.filter((r: any) => r.status === 'allocated' || r.status === 'in_transit').length
        const fulfilledRequests = requestList.filter((r: any) => r.status === 'fulfilled' || r.status === 'approved').length

        return {
            totalDonated,
            causesSupported: completedDonations.length,
            disastersActive: activeDisasters,
            disastersResolved: resolvedDisasters,
            resourcesAllocated: allocatedResources,
            totalResources,
            requestsFulfilled: fulfilledRequests,
            totalRequests: requestList.length,
        }
    }, [disasterList, resourceList, requestList, totalDonated, completedDonations.length])

    // Charts data from real disaster data
    const typeDistribution = useMemo(() => {
        const counts: Record<string, number> = {}
        disasterList.forEach((d: any) => { counts[d.type] = (counts[d.type] || 0) + 1 })
        return Object.entries(counts).map(([name, value]) => ({ name, value }))
    }, [disasterList])

    const monthlyTrend = useMemo(() => {
        const months: Record<string, { disasters: number; resources: number }> = {}
        disasterList.forEach((d: any) => {
            if (!d.created_at) return
            const key = new Date(d.created_at).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
            if (!months[key]) months[key] = { disasters: 0, resources: 0 }
            months[key].disasters++
        })
        resourceList.forEach((r: any) => {
            if (!r.created_at) return
            const key = new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
            if (!months[key]) months[key] = { disasters: 0, resources: 0 }
            months[key].resources++
        })
        return Object.entries(months).map(([month, data]) => ({ month, ...data })).slice(-8)
    }, [disasterList, resourceList])

    const severityBreakdown = useMemo(() => {
        const counts: Record<string, number> = {}
        disasterList.forEach((d: any) => { counts[d.severity] = (counts[d.severity] || 0) + 1 })
        return Object.entries(counts).map(([name, value]) => ({ name, value }))
    }, [disasterList])

    if (dLoading || rLoading || donLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Your Impact</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">See how your contributions make a difference</p>
            </div>

            {/* Key Impact Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { icon: Heart, color: 'blue', label: 'Total Donated', value: `$${metrics.totalDonated.toLocaleString()}` },
                    { icon: Target, color: 'emerald', label: 'Causes Supported', value: metrics.causesSupported },
                    { icon: Shield, color: 'purple', label: 'Resources Allocated', value: metrics.resourcesAllocated },
                    { icon: Globe, color: 'amber', label: 'Requests Fulfilled', value: `${metrics.requestsFulfilled}/${metrics.totalRequests}` },
                ].map((stat, i) => (
                    <div key={i} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl bg-${stat.color}-100 dark:bg-${stat.color}-500/10 flex items-center justify-center`}>
                                <stat.icon className={`w-5 h-5 text-${stat.color}-600 dark:text-${stat.color}-400`} />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-slate-900 dark:text-white">{stat.value}</p>
                                <p className="text-xs text-slate-500">{stat.label}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Charts */}
            <div className="grid grid-cols-2 gap-6">
                {/* Disaster Type Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Disaster Types Addressed</h3>
                    {typeDistribution.length > 0 ? (
                        <ResponsiveContainer width="100%" height={250}>
                            <PieChart>
                                <Pie data={typeDistribution} cx="50%" cy="50%" innerRadius={60} outerRadius={100}
                                    dataKey="value" nameKey="name" paddingAngle={2}>
                                    {typeDistribution.map((_, idx) => <Cell key={idx} fill={COLORS[idx % COLORS.length]} />)}
                                </Pie>
                                <Tooltip />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    ) : (
                        <p className="text-sm text-slate-400 text-center py-10">No data available</p>
                    )}
                </div>

                {/* Severity Breakdown */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Severity Breakdown</h3>
                    {severityBreakdown.length > 0 ? (
                        <ResponsiveContainer width="100%" height={250}>
                            <BarChart data={severityBreakdown}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                                <Tooltip />
                                <Bar dataKey="value" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <p className="text-sm text-slate-400 text-center py-10">No data available</p>
                    )}
                </div>
            </div>

            {/* Monthly Trend */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Monthly Activity Trend</h3>
                {monthlyTrend.length > 0 ? (
                    <ResponsiveContainer width="100%" height={280}>
                        <LineChart data={monthlyTrend}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="disasters" stroke="#ef4444" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="resources" stroke="#3b82f6" strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                ) : (
                    <p className="text-sm text-slate-400 text-center py-10">No trend data available</p>
                )}
            </div>

            {/* Recent Donations */}
            {completedDonations.length > 0 && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Recent Contributions</h3>
                    <div className="space-y-3">
                        {completedDonations.slice(-5).reverse().map((d: any) => (
                            <div key={d.id} className="flex items-center justify-between py-2 border-b border-slate-50 dark:border-white/5 last:border-0">
                                <div>
                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{d.disaster_title || 'Donation'}</p>
                                    <p className="text-xs text-slate-500">{new Date(d.created_at || d.date).toLocaleDateString()}</p>
                                </div>
                                <span className="text-sm font-bold text-green-600 dark:text-green-400">${(d.amount || 0).toLocaleString()}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
