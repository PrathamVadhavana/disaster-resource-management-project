'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSLAConfig, updateSLAConfig, getSLAViolations, getSLAHistory, type SLAConfig, type SLAViolation } from '@/lib/api/workflow'
import { useState, useMemo } from 'react'
import toast from 'react-hot-toast'
import { Clock, AlertTriangle, Settings, Loader2, CheckCircle, Shield, TrendingUp, ArrowUpCircle, Eye, XCircle, Calendar, TrendingDown, RefreshCw, Info, CheckCircle2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend } from 'recharts'
import { LineChart, Line } from 'recharts'
import { api } from '@/lib/api'
import { ReassignmentModal } from './ReassignmentModal'
import { cn } from '@/lib/utils'

// Circular Progress Ring Component
function CircularProgress({ value, max, color, size = 60 }: { value: number; max: number; color: string; size?: number }) {
    const percentage = max > 0 ? (value / max) * 100 : 0
    const strokeWidth = 6
    const radius = (size - strokeWidth) / 2
    const circumference = radius * 2 * Math.PI
    const offset = circumference - (percentage / 100) * circumference

    return (
        <svg width={size} height={size} className="transform -rotate-90">
            <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                stroke="currentColor"
                strokeWidth={strokeWidth}
                fill="none"
                className="text-slate-200 dark:text-slate-700"
            />
            <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                stroke={color}
                strokeWidth={strokeWidth}
                fill="none"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                strokeLinecap="round"
                className="transition-all duration-500"
            />
        </svg>
    )
}

export function SLADashboard() {
    const queryClient = useQueryClient()
    const [editing, setEditing] = useState(false)
    const [config, setConfig] = useState<Partial<SLAConfig>>({})

    const { data: slaConfig, isLoading: loadingConfig, error: configError } = useQuery({
        queryKey: ['sla-config'],
        queryFn: getSLAConfig,
        retry: false,
    })

    const { data: violationsData, isLoading: loadingViolations, error: violationsError } = useQuery({
        queryKey: ['sla-violations'],
        queryFn: getSLAViolations,
        refetchInterval: 30000,
        retry: false,
    })

    const { data: slaHistoryData, isLoading: loadingHistory, error: historyError } = useQuery({
        queryKey: ['sla-history'],
        queryFn: () => getSLAHistory(30),
        refetchInterval: 300000,
        retry: false,
    })

    const updateMutation = useMutation({
        mutationFn: (data: Partial<SLAConfig>) => updateSLAConfig(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sla-config'] })
            setEditing(false)
            toast.success('SLA configuration updated')
        },
        onError: (err: any) => toast.error(err.message || 'Failed to update SLA config'),
    })

    // Action mutations for violations
    const escalateMutation = useMutation({
        mutationFn: (requestId: string) => api.adminRequestAction(requestId, { action: 'escalate' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sla-violations'] })
            toast.success('Request escalated')
        },
        onError: (err: any) => toast.error(err.message || 'Failed to escalate'),
    })

    // Reassignment state
    const [reassignModalOpen, setReassignModalOpen] = useState(false)
    const [reassigningRequest, setReassigningRequest] = useState<SLAViolation | null>(null)

    const violations = violationsData?.violations || []
    const criticalCount = violations.filter(v => v.hours_elapsed > v.sla_hours * 2).length
    const warningCount = violations.length - criticalCount

    // Check if we have any data at all
    const hasData = (violationsData?.total_active_requests || 0) > 0

    // Compliance metrics
    const compliance = useMemo(() => {
        const total = violationsData?.total_active_requests || 0
        const compliant = Math.max(total - violations.length, 0)
        const rate = total > 0 ? Math.round((compliant / total) * 100) : 100
        const avgOverage = violations.length > 0
            ? +(violations.reduce((sum: number, v: SLAViolation) => sum + (v.hours_elapsed - v.sla_hours), 0) / violations.length).toFixed(1)
            : 0
        return { total, compliant, rate, avgOverage }
    }, [violations, violationsData])

    // SLA tier metrics
    const slaTiers = useMemo(() => {
        const approvedThreshold = slaConfig?.approved_sla_hours || 2
        const assignedThreshold = slaConfig?.assigned_sla_hours || 4
        const inProgressThreshold = slaConfig?.in_progress_sla_hours || 24

        const approvedViolations = violations.filter(v => v.status === 'approved' && v.hours_elapsed > approvedThreshold)
        const assignedViolations = violations.filter(v => v.status === 'assigned' && v.hours_elapsed > assignedThreshold)
        const inProgressViolations = violations.filter(v => v.status === 'in_progress' && v.hours_elapsed > inProgressThreshold)

        const approvedTotal = violations.filter(v => v.status === 'approved').length
        const assignedTotal = violations.filter(v => v.status === 'assigned').length
        const inProgressTotal = violations.filter(v => v.status === 'in_progress').length

        return [
            {
                label: 'Approved SLA',
                threshold: approvedThreshold,
                compliant: approvedTotal - approvedViolations.length,
                total: approvedTotal,
                color: '#22c55e',
                icon: CheckCircle2
            },
            {
                label: 'Assigned SLA',
                threshold: assignedThreshold,
                compliant: assignedTotal - assignedViolations.length,
                total: assignedTotal,
                color: '#f59e0b',
                icon: Clock
            },
            {
                label: 'In Progress SLA',
                threshold: inProgressThreshold,
                compliant: inProgressTotal - inProgressViolations.length,
                total: inProgressTotal,
                color: '#ef4444',
                icon: AlertTriangle
            }
        ]
    }, [violations, slaConfig])

    // Chart data for violation distribution
    const chartData = useMemo(() => {
        const byType: Record<string, number> = {}
        violations.forEach(v => {
            const label = v.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            byType[label] = (byType[label] || 0) + 1
        })
        return Object.entries(byType).map(([name, count]) => ({ name, count }))
    }, [violations])

    // SLA History chart data - stacked bar
    const historyChartData = useMemo(() => {
        if (!slaHistoryData?.chart_data) return []
        return slaHistoryData.chart_data.map((item: any) => ({
            ...item,
            compliant: (item.total_requests || 0) - (item.violations || 0),
            breached: item.violations || 0
        }))
    }, [slaHistoryData])

    const typeColors = ['#ef4444', '#f59e0b', '#f97316', '#e11d48', '#dc2626']

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Clock className="w-6 h-6 text-blue-500" />
                        SLA Monitoring
                    </h2>
                    <p className="text-sm text-slate-500 mt-1">
                        Track response time compliance and escalations
                    </p>
                </div>
                <button
                    onClick={() => setEditing(!editing)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 text-sm"
                >
                    <Settings className="w-4 h-4" />
                    {editing ? 'Cancel' : 'Configure'}
                </button>
            </div>

            {/* Error Messages */}
            {(configError || violationsError) && (
                <div className="rounded-xl border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-950/20 p-4">
                    <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-400 mb-2">
                        <AlertTriangle className="w-5 h-5" />
                        <span className="font-medium">Live SLA data unavailable</span>
                    </div>
                    <div className="text-sm text-yellow-600 dark:text-yellow-400 space-y-1">
                        {configError && <p>SLA Configuration: {(configError as Error).message}</p>}
                        {violationsError && <p>SLA Violations: {(violationsError as Error).message}</p>}
                        <p className="mt-2 text-xs text-yellow-500">The dashboard is not substituting fallback counts. Check the API connection or data availability.</p>
                    </div>
                </div>
            )}

            {/* Empty State Banner */}
            {!configError && !violationsError && !hasData && (
                <div className="rounded-2xl border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20 p-6">
                    <div className="flex items-start gap-4">
                        <div className="p-3 rounded-xl bg-blue-100 dark:bg-blue-500/10">
                            <Info className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="flex-1">
                            <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">No requests tracked yet</h3>
                            <p className="text-sm text-blue-700 dark:text-blue-300 mb-3">
                                SLA tracking begins once requests move from pending → assigned.
                            </p>
                            <div className="flex items-center gap-4 text-sm">
                                <span className="text-blue-600 dark:text-blue-400">
                                    Current thresholds:
                                </span>
                                <span className="px-2 py-1 rounded-lg bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 font-medium">
                                    Approved: {slaConfig?.approved_sla_hours || 2}h
                                </span>
                                <span className="px-2 py-1 rounded-lg bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 font-medium">
                                    Assigned: {slaConfig?.assigned_sla_hours || 4}h
                                </span>
                                <span className="px-2 py-1 rounded-lg bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 font-medium">
                                    In Progress: {slaConfig?.in_progress_sla_hours || 24}h
                                </span>
                            </div>
                            <button 
                                onClick={() => setEditing(true)}
                                className="mt-3 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                            >
                                Configure Thresholds →
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SLA Tier Cards with Circular Progress */}
            {!configError && !violationsError && hasData && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {slaTiers.map((tier, i) => {
                        const Icon = tier.icon
                        const rate = tier.total > 0 ? Math.round((tier.compliant / tier.total) * 100) : 100
                        return (
                            <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                                            <Icon className="w-3.5 h-3.5" style={{ color: tier.color }} />
                                            {tier.label}
                                        </div>
                                        <div className="text-2xl font-bold" style={{ color: tier.color }}>
                                            {rate}%
                                        </div>
                                        <p className="text-[10px] text-slate-400 mt-0.5">
                                            {tier.compliant} of {tier.total} compliant
                                        </p>
                                        <p className="text-[10px] text-slate-400">
                                            Threshold: {tier.threshold}h
                                        </p>
                                    </div>
                                    <div className="relative">
                                        <CircularProgress value={tier.compliant} max={tier.total} color={tier.color} size={60} />
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">{rate}%</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {violationsData?.context_summary && !violationsError && hasData && (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 text-sm text-slate-600 dark:text-slate-300">
                    <p>
                        Tracking live requests in statuses {violationsData.context_summary.tracked_statuses.join(', ')}. {violationsData.context_summary.live_breaches} are currently over SLA and {violationsData.context_summary.requests_at_risk} are approaching breach.
                    </p>
                </div>
            )}

            {/* SLA History Chart - Stacked Bar */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                        <Calendar className="w-4 h-4" />
                        SLA History (Last 30 Days)
                    </h3>
                    {loadingHistory && (
                        <div className="flex items-center gap-2 text-slate-500 text-sm">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Loading history...
                        </div>
                    )}
                </div>

                {historyError && (
                    <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                        <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-400 text-sm">
                            <AlertTriangle className="w-4 h-4" />
                            <span>Unable to load SLA history data</span>
                        </div>
                        <p className="text-xs text-yellow-500 mt-1">Please check your connection and try again.</p>
                    </div>
                )}

                <div className="h-[300px]">
                    {historyChartData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={historyChartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-700" />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 11 }}
                                    angle={-45}
                                    textAnchor="end"
                                    height={60}
                                />
                                <YAxis yAxisId="left" orientation="left" tick={{ fontSize: 11 }} label={{ value: 'Requests', angle: -90, position: 'insideLeft', style: { fontSize: 10 } }} />
                                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} label={{ value: 'Avg Response (h)', angle: 90, position: 'insideRight', style: { fontSize: 10 } }} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: 'var(--bg)',
                                        border: '1px solid var(--border)',
                                        borderRadius: '8px',
                                        fontSize: '12px'
                                    }}
                                    labelFormatter={(label) => `Date: ${label}`}
                                    formatter={(value: any, name: string) => [
                                        value,
                                        name === 'compliant' ? 'Compliant' : name === 'breached' ? 'Breached' : 'Avg Response Time (h)'
                                    ]}
                                />
                                <Legend />
                                <Bar yAxisId="left" dataKey="compliant" name="Compliant" fill="#22c55e" stackId="a" radius={[0, 0, 0, 0]} />
                                <Bar yAxisId="left" dataKey="breached" name="Breached" fill="#ef4444" stackId="a" radius={[4, 4, 0, 0]} />
                                <Line yAxisId="right" type="monotone" dataKey="avg_response_time" name="Avg Response Time" stroke="#06b6d4" strokeWidth={2} dot={{ fill: '#06b6d4', strokeWidth: 2, r: 3 }} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-slate-400">
                            <div className="w-full h-full border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl flex items-center justify-center">
                                <div className="text-center">
                                    <Calendar className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">No SLA history yet</p>
                                    <p className="text-xs mt-1">Data will appear once requests are tracked</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Summary Stats */}
                {slaHistoryData?.summary && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 pt-4 border-t border-slate-200 dark:border-slate-700">
                        <div className="text-center">
                            <div className="text-lg font-bold text-red-600">{slaHistoryData.summary.total_violations}</div>
                            <div className="text-xs text-slate-500">Total Violations</div>
                        </div>
                        <div className="text-center">
                            <div className="text-lg font-bold text-amber-600">{slaHistoryData.summary.avg_violations_per_day}</div>
                            <div className="text-xs text-slate-500">Avg Violations/Day</div>
                        </div>
                        <div className="text-center">
                            <div className="text-lg font-bold text-blue-600">{slaHistoryData.summary.avg_response_time}h</div>
                            <div className="text-xs text-slate-500">Avg Response Time</div>
                        </div>
                        <div className="text-center">
                            <div className="text-lg font-bold text-green-600">{slaHistoryData.summary.total_requests}</div>
                            <div className="text-xs text-slate-500">Total Requests</div>
                        </div>
                    </div>
                )}
            </div>

            {/* Requests at Risk Section */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-orange-500" />
                    Requests at Risk
                    {violationsData?.at_risk_count !== undefined && (
                        <span className="px-2 py-0.5 rounded-full bg-orange-100 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 text-[10px] font-bold">
                            {violationsData.at_risk_count}
                        </span>
                    )}
                </h3>

                {violationsData?.at_risk_count === 0 ? (
                    <div className="py-8 text-center">
                        <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-500/10 flex items-center justify-center mx-auto mb-3">
                            <CheckCircle2 className="w-6 h-6 text-green-500" />
                        </div>
                        <p className="text-sm font-medium text-green-700 dark:text-green-400">All requests are within SLA thresholds</p>
                        <p className="text-xs text-slate-500 mt-1">No requests are approaching their deadlines</p>
                    </div>
                ) : violations.length > 0 ? (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50">
                                <tr>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Request ID</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Type</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Priority</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Status</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Time Elapsed</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">SLA Deadline</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Time Remaining</th>
                                    <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                                {violations.slice(0, 10).map((v) => {
                                    const timeRemaining = v.sla_hours - v.hours_elapsed
                                    const isOverdue = timeRemaining < 0
                                    return (
                                        <tr key={v.request_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                                            <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-400">
                                                {v.request_id?.slice(0, 8)}...
                                            </td>
                                            <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{v.resource_type}</td>
                                            <td className="px-4 py-3">
                                                <span className={cn(
                                                    "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                                                    v.priority === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                                    v.priority === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                                    'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                                                )}>
                                                    {v.priority || 'medium'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 capitalize">
                                                    {v.status?.replace('_', ' ')}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={cn(
                                                    "font-medium",
                                                    isOverdue ? 'text-red-600' : timeRemaining < v.sla_hours * 0.25 ? 'text-orange-600' : 'text-slate-700 dark:text-slate-300'
                                                )}>
                                                    {v.hours_elapsed}h
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                                                {v.sla_hours}h
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={cn(
                                                    "font-medium",
                                                    isOverdue ? 'text-red-600' : 'text-green-600'
                                                )}>
                                                    {isOverdue ? `${Math.abs(timeRemaining).toFixed(1)}h overdue` : `${timeRemaining.toFixed(1)}h remaining`}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-1">
                                                    <button
                                                        onClick={() => {
                                                            setReassigningRequest(v)
                                                            setReassignModalOpen(true)
                                                        }}
                                                        className="p-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/10 text-blue-500 transition-colors"
                                                        title="Reassign"
                                                    >
                                                        <RefreshCw className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="py-8 text-center text-slate-400">
                        <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">Loading request data...</p>
                    </div>
                )}
            </div>

            {/* SLA Violation Distribution Chart */}
            {chartData.length > 0 && (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Violation Distribution</h3>
                    <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-700" />
                            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                            <Tooltip
                                contentStyle={{ backgroundColor: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
                            />
                            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                                {chartData.map((_, i) => (
                                    <Cell key={i} fill={typeColors[i % typeColors.length]} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* SLA Config Editor */}
            {editing && (
                <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20 p-6 space-y-4">
                    <h3 className="font-semibold text-slate-900 dark:text-white">SLA Configuration</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        {[
                            { key: 'approved_sla_hours' as const, label: 'Approved → Response', desc: 'Max hours before approved request should get a responder' },
                            { key: 'assigned_sla_hours' as const, label: 'Assigned → Action', desc: 'Max hours before assigned request should start delivery' },
                            { key: 'in_progress_sla_hours' as const, label: 'In Progress → Delivery', desc: 'Max hours before delivery should be completed' },
                        ].map(({ key, label, desc }) => (
                            <div key={key}>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</label>
                                <p className="text-xs text-slate-500 mb-1">{desc}</p>
                                <input
                                    type="number"
                                    step="0.5"
                                    min="0.5"
                                    max={key === 'in_progress_sla_hours' ? 168 : 72}
                                    defaultValue={slaConfig?.[key]}
                                    onChange={(e) => setConfig(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))}
                                    className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                                />
                            </div>
                        ))}
                    </div>
                    <button
                        onClick={() => updateMutation.mutate(config)}
                        disabled={updateMutation.isPending || Object.keys(config).length === 0}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-50 text-sm"
                    >
                        {updateMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                        Save Configuration
                    </button>
                </div>
            )}

            {/* Reassignment Modal */}
            <ReassignmentModal
                isOpen={reassignModalOpen}
                onClose={() => {
                    setReassignModalOpen(false)
                    setReassigningRequest(null)
                }}
                onSuccess={() => {
                    queryClient.invalidateQueries({ queryKey: ['sla-violations'] })
                    toast.success('Request reassigned successfully')
                }}
                requestId={reassigningRequest?.request_id || ''}
                currentAssignedTo={reassigningRequest?.assigned_to || undefined}
            />
        </div>
    )
}