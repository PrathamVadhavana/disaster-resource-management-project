'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Activity, Users, AlertTriangle, Loader2, Package
} from 'lucide-react'
import {
    BarChart, Bar, PieChart, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

const CHART_COLORS = ['#ef4444', '#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#6b7280', '#ec4899', '#14b8a6']

function StatCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: any; color: string }) {
    return (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
            <div className={`w-10 h-10 rounded-xl ${color} flex items-center justify-center`}>
                <Icon className="w-5 h-5 text-white" />
            </div>
            <p className="mt-3 text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{label}</p>
        </div>
    )
}

export default function AdminAnalyticsPage() {
    const { data: disasters, isLoading: ld } = useQuery({
        queryKey: ['admin-analytics-disasters'],
        queryFn: () => api.getDisasters({ limit: 500 }),
        refetchInterval: 30000,
    })
    const { data: resources, isLoading: lr } = useQuery({
        queryKey: ['admin-analytics-resources'],
        queryFn: () => api.getResources({}),
        refetchInterval: 30000,
    })
    const { data: users, isLoading: lu } = useQuery({
        queryKey: ['admin-analytics-users'],
        queryFn: () => api.getUsers(),
        refetchInterval: 60000,
    })
    const { data: requests } = useQuery({
        queryKey: ['admin-analytics-requests'],
        queryFn: () => api.getNGORequests({ page_size: 1 }),
        refetchInterval: 60000,
    })

    const isLoading = ld || lr || lu
    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const userList = Array.isArray(users) ? users : []
    const totalRequests = (requests as any)?.total ?? 0

    // Disaster type distribution
    const typeCounts: Record<string, number> = {}
    disasterList.forEach((d: any) => { typeCounts[d.type || 'other'] = (typeCounts[d.type || 'other'] || 0) + 1 })
    const typeDistribution = Object.entries(typeCounts).map(([name, value], i) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1), value, color: CHART_COLORS[i % CHART_COLORS.length],
    }))

    // Severity distribution
    const sevCounts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 }
    disasterList.forEach((d: any) => { sevCounts[d.severity || 'medium'] = (sevCounts[d.severity || 'medium'] || 0) + 1 })
    const severityData = [
        { severity: 'Critical', count: sevCounts.critical, fill: '#ef4444' },
        { severity: 'High', count: sevCounts.high, fill: '#f97316' },
        { severity: 'Medium', count: sevCounts.medium, fill: '#eab308' },
        { severity: 'Low', count: sevCounts.low, fill: '#22c55e' },
    ]

    // Resource type distribution
    const resTypeCounts: Record<string, number> = {}
    resourceList.forEach((r: any) => { resTypeCounts[r.type || 'other'] = (resTypeCounts[r.type || 'other'] || 0) + (r.quantity || 1) })
    const resourceTypeData = Object.entries(resTypeCounts).map(([name, qty]) => ({
        type: name.charAt(0).toUpperCase() + name.slice(1), quantity: Math.round(qty),
    }))

    // Resource status distribution
    const statusCounts: Record<string, number> = { available: 0, allocated: 0, in_transit: 0, deployed: 0 }
    resourceList.forEach((r: any) => { statusCounts[r.status || 'available'] = (statusCounts[r.status || 'available'] || 0) + 1 })
    const statusData = Object.entries(statusCounts).map(([name, value], i) => ({
        name: name.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()), value,
        color: ['#22c55e', '#8b5cf6', '#3b82f6', '#f59e0b'][i] || '#6b7280',
    }))

    // User role distribution
    const roleCounts: Record<string, number> = {}
    userList.forEach((u: any) => { roleCounts[u.role || 'unknown'] = (roleCounts[u.role || 'unknown'] || 0) + 1 })
    const roleData = Object.entries(roleCounts).map(([name, count]) => ({
        role: name.charAt(0).toUpperCase() + name.slice(1), count,
    }))

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Platform Analytics</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Real-time overview of system performance and disaster response metrics
                </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Active Disasters" value={disasterList.filter((d: any) => d.status === 'active').length} icon={AlertTriangle} color="bg-gradient-to-br from-red-500 to-orange-600" />
                <StatCard label="Total Users" value={userList.length.toLocaleString()} icon={Users} color="bg-gradient-to-br from-blue-500 to-cyan-600" />
                <StatCard label="Total Resources" value={resourceList.length.toLocaleString()} icon={Package} color="bg-gradient-to-br from-purple-500 to-indigo-600" />
                <StatCard label="Resource Requests" value={totalRequests} icon={Activity} color="bg-gradient-to-br from-emerald-500 to-teal-600" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Disaster Type Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Disaster Type Distribution</h3>
                    {typeDistribution.length > 0 ? (
                        <div className="h-64 flex items-center">
                            <ResponsiveContainer width="60%" height="100%">
                                <PieChart>
                                    <Pie data={typeDistribution} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={4} dataKey="value">
                                        {typeDistribution.map((entry) => (<Cell key={entry.name} fill={entry.color} />))}
                                    </Pie>
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="space-y-2">
                                {typeDistribution.map((dt) => (
                                    <div key={dt.name} className="flex items-center gap-2">
                                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: dt.color }} />
                                        <span className="text-xs text-slate-600 dark:text-slate-400">{dt.name}</span>
                                        <span className="text-xs font-bold text-slate-900 dark:text-white ml-auto">{dt.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-slate-400 text-sm">No disaster data available</div>
                    )}
                </div>

                {/* Severity Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Disaster Severity Distribution</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={severityData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                <XAxis dataKey="severity" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                                    {severityData.map((entry) => (<Cell key={entry.severity} fill={entry.fill} />))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Resource by Type */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Resources by Type</h3>
                    <div className="h-64">
                        {resourceTypeData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={resourceTypeData} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                    <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                                    <YAxis dataKey="type" type="category" tick={{ fontSize: 11 }} stroke="#94a3b8" width={80} />
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                    <Bar dataKey="quantity" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm">No resource data</div>
                        )}
                    </div>
                </div>

                {/* Resource Status */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Resource Status Overview</h3>
                    {statusData.some(s => s.value > 0) ? (
                        <div className="h-64 flex items-center">
                            <ResponsiveContainer width="60%" height="100%">
                                <PieChart>
                                    <Pie data={statusData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={4} dataKey="value">
                                        {statusData.map((entry) => (<Cell key={entry.name} fill={entry.color} />))}
                                    </Pie>
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="space-y-2">
                                {statusData.map((item) => (
                                    <div key={item.name} className="flex items-center gap-2">
                                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                                        <span className="text-xs text-slate-600 dark:text-slate-400">{item.name}</span>
                                        <span className="text-xs font-bold text-slate-900 dark:text-white ml-auto">{item.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-slate-400 text-sm">No resource data</div>
                    )}
                </div>
            </div>

            {roleData.length > 0 && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Users by Role</h3>
                    <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={roleData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                <XAxis dataKey="role" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                <Bar dataKey="count" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}
        </div>
    )
}
