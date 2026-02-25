'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import {
    Activity, Users, AlertTriangle, Loader2, Package, TrendingUp,
    Clock, BarChart3, PieChart as PieIcon, ArrowDown, ArrowUp, Zap, Download
} from 'lucide-react'
import {
    BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, AreaChart, Area,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const CHART_COLORS = ['#ef4444', '#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#6b7280', '#ec4899', '#14b8a6']
const PRIORITY_COLORS: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e' }
const STATUS_COLORS: Record<string, string> = { pending: '#f59e0b', approved: '#10b981', assigned: '#3b82f6', in_progress: '#8b5cf6', completed: '#059669', rejected: '#ef4444' }

function MetricCard({ label, value, sub, icon: Icon, gradient }: { label: string; value: string | number; sub?: string; icon: any; gradient: string }) {
    return (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">{label}</p>
                    <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</p>
                    {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
                </div>
                <div className={cn('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center', gradient)}>
                    <Icon className="w-5 h-5 text-white" />
                </div>
            </div>
        </div>
    )
}

export default function AdminAnalyticsPage() {
    const [trendDays, setTrendDays] = useState(30)

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
    const { data: trends } = useQuery({
        queryKey: ['admin-analytics-trends', trendDays],
        queryFn: () => api.getRequestTrends({ days: trendDays }),
        refetchInterval: 60000,
    })
    const { data: reqData } = useQuery({
        queryKey: ['admin-analytics-requests'],
        queryFn: () => api.getAdminRequests({ page_size: 1 }),
        refetchInterval: 60000,
    })

    const { data: summary } = useQuery({
        queryKey: ['admin-analytics-summary'],
        queryFn: () => api.getAnalyticsSummary(),
        refetchInterval: 60000,
    })

    const { data: volunteerPerformance } = useQuery({
        queryKey: ['admin-analytics-volunteers'],
        queryFn: () => api.getVolunteerPerformance(),
        refetchInterval: 60000,
    })

    const { data: burnRate } = useQuery({
        queryKey: ['admin-analytics-burnrate', trendDays],
        queryFn: () => api.getResourceBurnRate({ days: trendDays }),
        refetchInterval: 60000,
    })

    const isLoading = ld || lr || lu
    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const userList = Array.isArray(users) ? users : []
    const activeDisasters = disasterList.filter((d: any) => d.status === 'active')
    const totalRequests = reqData?.total || trends?.total_requests || 0
    const statusCounts = reqData?.status_counts || {}
    const avgResponseHours = trends?.avg_response_hours || 0
    const dailyTrends = trends?.daily_trends || []
    const priorityDist = trends?.priority_distribution || {}
    const typeDist = trends?.type_distribution || {}

    // Disaster type distribution
    const typeCounts: Record<string, number> = {}
    disasterList.forEach((d: any) => { typeCounts[d.type || 'other'] = (typeCounts[d.type || 'other'] || 0) + 1 })
    const typeDistribution = Object.entries(typeCounts).map(([name, value], i) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1), value, color: CHART_COLORS[i % CHART_COLORS.length],
    }))

    // Resource status distribution
    const statusData: Record<string, number> = { available: 0, allocated: 0, in_transit: 0, deployed: 0 }
    resourceList.forEach((r: any) => { statusData[r.status || 'available'] = (statusData[r.status || 'available'] || 0) + 1 })
    const resourceStatusData = Object.entries(statusData).map(([name, value], i) => ({
        name: name.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()), value,
        color: ['#22c55e', '#8b5cf6', '#3b82f6', '#f59e0b'][i] || '#6b7280',
    }))

    // User role distribution
    const roleCounts: Record<string, number> = {}
    userList.forEach((u: any) => { roleCounts[u.role || 'unknown'] = (roleCounts[u.role || 'unknown'] || 0) + 1 })
    const roleData = Object.entries(roleCounts).map(([name, count]) => ({
        role: name.charAt(0).toUpperCase() + name.slice(1), count,
    }))

    // Request priority distribution for chart
    const priorityChartData = Object.entries(priorityDist).map(([name, count]) => ({
        priority: name.charAt(0).toUpperCase() + name.slice(1),
        count: count as number,
        fill: PRIORITY_COLORS[name] || '#6b7280',
    }))

    // Request type distribution for chart
    const requestTypeData = Object.entries(typeDist).map(([name, count], i) => ({
        type: name, count: count as number, fill: CHART_COLORS[i % CHART_COLORS.length],
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
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <BarChart3 className="w-6 h-6 text-purple-500" />
                        Platform Analytics
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Comprehensive insights into disaster response performance
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {[7, 14, 30, 90].map(d => (
                        <button key={d} onClick={() => setTrendDays(d)}
                            className={cn('px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                                trendDays === d
                                    ? 'bg-purple-600 text-white shadow-sm'
                                    : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10'
                            )}>
                            {d}d
                        </button>
                    ))}
                    <div className="relative ml-2 group">
                        <button className="flex items-center gap-1 px-4 py-2 rounded-xl text-xs font-bold bg-purple-600 text-white hover:bg-purple-700 shadow-lg shadow-purple-500/20 transition-all">
                            <Download className="w-3.5 h-3.5" /> Export Data
                        </button>
                        <div className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-20 p-2 overflow-hidden">
                            <div className="px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-tight border-b border-slate-100 dark:border-white/5 mb-1">Standard Tables</div>
                            {(['requests', 'resources', 'users'] as const).map(dt => (
                                <button key={dt} onClick={() => api.exportData(dt)}
                                    className="w-full text-left px-3 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 rounded-xl capitalize transition-colors">
                                    {dt} History
                                </button>
                            ))}
                            <div className="px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-tight border-b border-slate-100 dark:border-white/5 mt-2 mb-1">Phase 6 Interactivity</div>
                            {(['verifications', 'pledges', 'missions', 'pulse'] as const).map(dt => (
                                <button key={dt} onClick={() => api.exportInteractivityData(dt)}
                                    className="w-full text-left px-3 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 rounded-xl capitalize transition-colors">
                                    {dt} Log
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                <MetricCard label="Active Disasters" value={activeDisasters.length} icon={AlertTriangle} gradient="from-red-500 to-orange-600" sub={`${disasterList.length} total`} />
                <MetricCard label="Total Users" value={userList.length} icon={Users} gradient="from-blue-500 to-cyan-600" />
                <MetricCard label="Total Resources" value={resourceList.length} icon={Package} gradient="from-purple-500 to-indigo-600" />
                <MetricCard label="Total Requests" value={totalRequests} icon={Activity} gradient="from-emerald-500 to-teal-600" sub={`${statusCounts.pending || 0} pending`} />
                <MetricCard label="Avg Response" value={avgResponseHours > 0 ? `${avgResponseHours}h` : 'N/A'} icon={Clock} gradient="from-amber-500 to-orange-600" sub="request → action" />
            </div>

            {/* Request Trends - Line Chart */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-purple-500" /> Request Trends ({trendDays} days)
                </h3>
                <div className="h-72">
                    {dailyTrends.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={dailyTrends}>
                                <defs>
                                    <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" tickFormatter={(v: string) => v.slice(5)} />
                                <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" allowDecimals={false} />
                                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                <Area type="monotone" dataKey="total" stroke="#8b5cf6" fill="url(#totalGrad)" strokeWidth={2} />
                                <Line type="monotone" dataKey="approved" stroke="#10b981" strokeWidth={1.5} dot={false} />
                                <Line type="monotone" dataKey="rejected" stroke="#ef4444" strokeWidth={1.5} dot={false} />
                                <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                            </AreaChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-full flex items-center justify-center text-slate-400 text-sm">No trend data available</div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Resource Burn Rate - Phase 7 */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Zap className="w-4 h-4 text-amber-500" /> Resource Fulfillment Speed (Fulfillment vs Need)
                    </h3>
                    <div className="h-64">
                        {burnRate && burnRate.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={burnRate}>
                                    <defs>
                                        <linearGradient id="reqGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.1} />
                                            <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="fulGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor="#10b981" stopOpacity={0.1} />
                                            <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                    <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" tickFormatter={(v: string) => v.slice(5)} />
                                    <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" />
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                    <Area type="monotone" dataKey="requested" name="Units Requested" stroke="#f59e0b" fill="url(#reqGrad)" strokeWidth={2} />
                                    <Area type="monotone" dataKey="fulfilled" name="Units Fulfilled" stroke="#10b981" fill="url(#fulGrad)" strokeWidth={2} />
                                    <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm italic">Gathering fulfillment data...</div>
                        )}
                    </div>
                </div>

                {/* Volunteer Ranking - Phase 7 */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Users className="w-4 h-4 text-blue-500" /> Volunteer Impact Ranking
                    </h3>
                    <div className="h-64">
                        {volunteerPerformance && volunteerPerformance.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={volunteerPerformance.slice(0, 10)} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} vertical={false} />
                                    <XAxis type="number" hide />
                                    <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} stroke="#94a3b8" width={80} />
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} cursor={{ fill: 'transparent' }} />
                                    <Bar dataKey="total_verifs" name="Total Verifications" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={12} />
                                    <Bar dataKey="accuracy" name="Accuracy %" fill="#10b981" radius={[0, 4, 4, 0]} barSize={8} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm italic">No volunteer metrics yet</div>
                        )}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Request Priority Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Request Priority Distribution</h3>
                    <div className="h-64">
                        {priorityChartData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={priorityChartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                    <XAxis dataKey="priority" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                                    <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                    <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                                        {priorityChartData.map((entry) => (<Cell key={entry.priority} fill={entry.fill} />))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm">No data</div>
                        )}
                    </div>
                </div>

                {/* Request Type Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Request Type Breakdown</h3>
                    {requestTypeData.length > 0 ? (
                        <div className="h-64 flex items-center">
                            <ResponsiveContainer width="55%" height="100%">
                                <PieChart>
                                    <Pie data={requestTypeData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="count">
                                        {requestTypeData.map((entry) => (<Cell key={entry.type} fill={entry.fill} />))}
                                    </Pie>
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="space-y-2">
                                {requestTypeData.map((dt) => (
                                    <div key={dt.type} className="flex items-center gap-2">
                                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: dt.fill }} />
                                        <span className="text-xs text-slate-600 dark:text-slate-400">{dt.type}</span>
                                        <span className="text-xs font-bold text-slate-900 dark:text-white ml-auto">{dt.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-slate-400 text-sm">No data</div>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Disaster Type Distribution */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Disaster Type Distribution</h3>
                    {typeDistribution.length > 0 ? (
                        <div className="h-64 flex items-center">
                            <ResponsiveContainer width="55%" height="100%">
                                <PieChart>
                                    <Pie data={typeDistribution} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value">
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
                        <div className="h-64 flex items-center justify-center text-slate-400 text-sm">No disaster data</div>
                    )}
                </div>

                {/* Resource Status */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Resource Utilization</h3>
                    {resourceStatusData.some(s => s.value > 0) ? (
                        <div className="h-64 flex items-center">
                            <ResponsiveContainer width="55%" height="100%">
                                <PieChart>
                                    <Pie data={resourceStatusData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value">
                                        {resourceStatusData.map((entry) => (<Cell key={entry.name} fill={entry.color} />))}
                                    </Pie>
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="space-y-2">
                                {resourceStatusData.map((item) => (
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

            {/* Users by Role */}
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

            {/* Request Status Summary */}
            {Object.keys(statusCounts).length > 0 && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Request Status Summary</h3>
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
                        {Object.entries(statusCounts).map(([status, count]) => (
                            <div key={status} className="rounded-xl border border-slate-100 dark:border-white/5 p-3 text-center">
                                <div className="w-3 h-3 rounded-full mx-auto mb-2" style={{ backgroundColor: STATUS_COLORS[status] || '#6b7280' }} />
                                <p className="text-lg font-bold text-slate-900 dark:text-white">{count as number}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider">{status.replace('_', ' ')}</p>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
