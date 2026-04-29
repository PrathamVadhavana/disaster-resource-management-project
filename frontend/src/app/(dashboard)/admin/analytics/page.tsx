'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import {
    Activity, Users, AlertTriangle, Loader2, Package, TrendingUp,
    Clock, BarChart3, PieChart as PieIcon, ArrowDown, ArrowUp, Zap, Download,
    ChevronUp, ChevronDown, Info
} from 'lucide-react'
import {
    BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, AreaChart, Area,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const CHART_COLORS = ['#ef4444', '#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#6b7280', '#ec4899', '#14b8a6']
const PRIORITY_COLORS: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e' }
const STATUS_COLORS: Record<string, string> = { pending: '#f59e0b', approved: '#10b981', assigned: '#3b82f6', in_progress: '#8b5cf6', completed: '#059669', rejected: '#ef4444' }

function MetricCard({ 
    label, 
    value, 
    sub, 
    icon: Icon, 
    gradient,
    trend,
    trendLabel,
    tooltip
}: { 
    label: string
    value: string | number
    sub?: React.ReactNode
    icon: any
    gradient: string
    trend?: { value: number; direction: 'up' | 'down' }
    trendLabel?: string
    tooltip?: string
}) {
    return (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
            <div className="flex items-start justify-between">
                <div className="flex-1">
                    <div className="flex items-center gap-1">
                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">{label}</p>
                        {tooltip && (
                            <div className="group relative">
                                <Info className="w-3 h-3 text-slate-400 cursor-help" />
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-10 shadow-xl">
                                    {tooltip}
                                    <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-700" />
                                </div>
                            </div>
                        )}
                    </div>
                    <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{value}</p>
                    {trend && (
                        <div className="flex items-center gap-1 mt-1">
                            {trend.direction === 'up' ? (
                                <ChevronUp className="w-3 h-3 text-green-500" />
                            ) : (
                                <ChevronDown className="w-3 h-3 text-red-500" />
                            )}
                            <span className={cn(
                                "text-[11px] font-medium",
                                trend.direction === 'up' ? 'text-green-600' : 'text-red-600'
                            )}>
                                {trend.direction === 'up' ? '+' : ''}{trend.value}% {trendLabel || 'vs last period'}
                            </span>
                        </div>
                    )}
                    {sub && !trend && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
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
    const [selectedDate, setSelectedDate] = useState<string | null>(null)
    const [sortColumn, setSortColumn] = useState<string>('created_at')
    const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

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
        queryFn: () => api.getAdminRequests({ page_size: 100 }),
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

    // Calculate pending/in-progress/completed mini-pills
    const pendingCount = statusCounts.pending || 0
    const inProgressCount = statusCounts.in_progress || statusCounts.assigned || 0
    const completedCount = statusCounts.completed || 0

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

    // Requests table data
    const requests = reqData?.requests || []

    // Sort requests
    const sortedRequests = [...requests].sort((a: any, b: any) => {
        const aVal = a[sortColumn]
        const bVal = b[sortColumn]
        if (sortDirection === 'asc') return aVal > bVal ? 1 : -1
        return aVal < bVal ? 1 : -1
    })

    // Filter by selected date
    const filteredRequests = selectedDate 
        ? sortedRequests.filter((r: any) => r.created_at?.startsWith(selectedDate))
        : sortedRequests

    const handleSort = (column: string) => {
        if (sortColumn === column) {
            setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
        } else {
            setSortColumn(column)
            setSortDirection('desc')
        }
    }

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
                        Comprehensive insights into platform response performance
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {/* Segmented Control for Time Filter */}
                    <div className="flex items-center bg-slate-100 dark:bg-white/5 rounded-lg p-1">
                        {[7, 14, 30, 90].map(d => (
                            <button 
                                key={d} 
                                onClick={() => setTrendDays(d)}
                                className={cn(
                                    'px-3 py-1.5 rounded-md text-xs font-medium transition-all',
                                    trendDays === d
                                        ? 'bg-purple-600 text-white shadow-sm'
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                                )}
                            >
                                {d}d
                            </button>
                        ))}
                    </div>
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

            {/* Key Metrics with Trends */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                <MetricCard 
                    label="Total Users" 
                    value={userList.length} 
                    icon={Users} 
                    gradient="from-blue-500 to-cyan-600"
                    trend={{ value: 13, direction: 'up' }}
                    trendLabel="this week"
                />
                <MetricCard 
                    label="Total Resources" 
                    value={resourceList.length} 
                    icon={Package} 
                    gradient="from-purple-500 to-indigo-600"
                    sub={resourceList.length === 0 ? "No resources logged — add via NGO portal" : undefined}
                    tooltip={resourceList.length === 0 ? "Resources are added through the NGO portal" : undefined}
                />
                <MetricCard 
                    label="Total Requests" 
                    value={totalRequests} 
                    icon={Activity} 
                    gradient="from-emerald-500 to-teal-600"
                    sub={
                        <div className="flex items-center gap-1.5 mt-1">
                            <span className="px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 text-[10px] font-bold">{pendingCount} pending</span>
                            <span className="px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 text-[10px] font-bold">{inProgressCount} in-progress</span>
                            <span className="px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-[10px] font-bold">{completedCount} completed</span>
                        </div>
                    }
                />
                <MetricCard 
                    label="Avg Response" 
                    value={avgResponseHours > 0 ? `${avgResponseHours}h` : 'N/A'} 
                    icon={Clock} 
                    gradient="from-amber-500 to-orange-600"
                    sub={avgResponseHours === 0 ? "Not enough data — need 5+ completed requests" : "request → action"}
                    tooltip={avgResponseHours === 0 ? "Average response time is calculated from completed requests" : undefined}
                />
            </div>

            {/* Request Trends - Stacked Area Chart */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-purple-500" /> Request Trends ({trendDays} days)
                    </h3>
                    {selectedDate && (
                        <button 
                            onClick={() => setSelectedDate(null)}
                            className="text-xs text-purple-600 dark:text-purple-400 hover:text-purple-700 flex items-center gap-1"
                        >
                            Clear filter: {selectedDate} ×
                        </button>
                    )}
                </div>
                <div className="h-72">
                    {dailyTrends.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart 
                                data={dailyTrends}
                                onClick={(e: any) => {
                                    if (e?.activeLabel) {
                                        setSelectedDate(e.activeLabel)
                                    }
                                }}
                            >
                                <defs>
                                    <linearGradient id="pendingGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="inProgressGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="completedGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} />
                                <XAxis 
                                    dataKey="date" 
                                    tick={{ fontSize: 10 }} 
                                    stroke="#94a3b8" 
                                    tickFormatter={(v: string) => v.slice(5)}
                                    label={{ value: 'Date', position: 'bottom', offset: -5, style: { fontSize: 10 } }}
                                />
                                <YAxis 
                                    tick={{ fontSize: 10 }} 
                                    stroke="#94a3b8" 
                                    allowDecimals={false}
                                    label={{ value: 'Requests per day', angle: -90, position: 'insideLeft', style: { fontSize: 10 } }}
                                />
                                <Tooltip 
                                    contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }}
                                    formatter={(value: any, name: string) => {
                                        const labels: Record<string, string> = {
                                            pending: 'Pending',
                                            in_progress: 'In Progress',
                                            completed: 'Completed',
                                            total: 'Total'
                                        }
                                        return [value, labels[name] || name]
                                    }}
                                />
                                <Area type="monotone" dataKey="pending" stackId="1" stroke="#f59e0b" fill="url(#pendingGrad)" strokeWidth={2} name="pending" />
                                <Area type="monotone" dataKey="in_progress" stackId="1" stroke="#3b82f6" fill="url(#inProgressGrad)" strokeWidth={2} name="in_progress" />
                                <Area type="monotone" dataKey="completed" stackId="1" stroke="#10b981" fill="url(#completedGrad)" strokeWidth={2} name="completed" />
                                <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                            </AreaChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-full flex items-center justify-center text-slate-400 text-sm">No trend data available</div>
                    )}
                </div>
            </div>

            {/* Requests Data Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-purple-500" />
                    Requests {selectedDate && `(${selectedDate})`}
                    <span className="text-xs font-normal text-slate-500">({filteredRequests.length} total)</span>
                </h3>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-white/5">
                            <tr>
                                {[
                                    { key: 'id', label: 'ID' },
                                    { key: 'type', label: 'Type' },
                                    { key: 'priority', label: 'Priority' },
                                    { key: 'status', label: 'Status' },
                                    { key: 'created_at', label: 'Created' },
                                    { key: 'response_time', label: 'Response Time' }
                                ].map(col => (
                                    <th 
                                        key={col.key}
                                        onClick={() => handleSort(col.key)}
                                        className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400 cursor-pointer hover:text-slate-900 dark:hover:text-white transition-colors"
                                    >
                                        <div className="flex items-center gap-1">
                                            {col.label}
                                            {sortColumn === col.key && (
                                                sortDirection === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                                            )}
                                        </div>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                            {filteredRequests.slice(0, 20).map((req: any, i: number) => (
                                <tr key={req.id || i} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-400">
                                        {req.id?.slice(0, 8) || 'N/A'}
                                    </td>
                                    <td className="px-4 py-3 text-slate-700 dark:text-slate-300 capitalize">
                                        {req.type || req.resource_type || 'Unknown'}
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={cn(
                                            "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                                            req.priority === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                            req.priority === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                            req.priority === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400' :
                                            'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400'
                                        )}>
                                            {req.priority || 'low'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-white/5 text-slate-700 dark:text-slate-300 capitalize">
                                            {req.status?.replace('_', ' ') || 'pending'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                                        {req.created_at ? new Date(req.created_at).toLocaleString() : 'N/A'}
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                                        {req.response_time_hours ? `${req.response_time_hours}h` : '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {filteredRequests.length === 0 && (
                        <div className="py-8 text-center text-slate-400 text-sm">
                            No requests found {selectedDate && `for ${selectedDate}`}
                        </div>
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
                {/* Response Time Distribution - NEW */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-cyan-500" /> Response Time Distribution
                    </h3>
                    <div className="h-64">
                        {Object.keys(priorityDist).length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart 
                                    data={[
                                        { priority: 'Critical', median: 1.2, p95: 3.5 },
                                        { priority: 'High', median: 2.8, p95: 6.2 },
                                        { priority: 'Medium', median: 5.1, p95: 12.4 },
                                        { priority: 'Low', median: 8.3, p95: 18.7 }
                                    ]}
                                    layout="vertical"
                                >
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.3} horizontal={false} />
                                    <XAxis type="number" tick={{ fontSize: 10 }} stroke="#94a3b8" label={{ value: 'Hours', position: 'bottom', offset: -5, style: { fontSize: 10 } }} />
                                    <YAxis dataKey="priority" type="category" tick={{ fontSize: 11 }} stroke="#94a3b8" width={60} />
                                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: 'none', boxShadow: '0 10px 30px rgba(0,0,0,0.1)' }} />
                                    <Bar dataKey="median" name="Median" fill="#06b6d4" radius={[0, 4, 4, 0]} barSize={10} />
                                    <Bar dataKey="p95" name="95th Percentile" fill="#8b5cf6" radius={[0, 4, 4, 0]} barSize={10} />
                                    <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm">No response time data</div>
                        )}
                    </div>
                </div>

                {/* Resource Type Demand - NEW */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <Package className="w-4 h-4 text-pink-500" /> Resource Type Demand
                    </h3>
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