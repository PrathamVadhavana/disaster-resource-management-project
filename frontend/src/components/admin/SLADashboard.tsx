'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSLAConfig, updateSLAConfig, getSLAViolations, getSLAHistory, type SLAConfig, type SLAViolation } from '@/lib/api/workflow'
import { useState, useMemo } from 'react'
import toast from 'react-hot-toast'
import { Clock, AlertTriangle, Settings, Loader2, CheckCircle, Shield, TrendingUp, ArrowUpCircle, Eye, XCircle, Calendar, TrendingDown, RefreshCw } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { LineChart, Line, Legend } from 'recharts'
import { api } from '@/lib/api'
import { ReassignmentModal } from './ReassignmentModal'

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
        refetchInterval: 300000, // Refetch every 5 minutes
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

    // Chart data for violation distribution
    const chartData = useMemo(() => {
        const byType: Record<string, number> = {}
        violations.forEach(v => {
            const label = v.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            byType[label] = (byType[label] || 0) + 1
        })
        return Object.entries(byType).map(([name, count]) => ({ name, count }))
    }, [violations])

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

            {/* Compliance Metrics Cards */}
            {!configError && !violationsError && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <Shield className="w-3.5 h-3.5" />
                            Compliance Rate
                        </div>
                        <div className={`text-2xl font-bold ${compliance.rate >= 90 ? 'text-green-600' : compliance.rate >= 70 ? 'text-amber-600' : 'text-red-600'}`}>
                            {compliance.rate}%
                        </div>
                        <p className="text-[10px] text-slate-400 mt-0.5">{compliance.compliant} of {compliance.total} compliant</p>
                    </div>
                    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <TrendingDown className="w-3.5 h-3.5" />
                            Average Response Time
                        </div>
                        <div className="text-2xl font-bold text-blue-600">
                            {slaHistoryData?.summary?.avg_response_time || 0}h
                        </div>
                        <p className="text-[10px] text-slate-400 mt-0.5">Based on last 30 days</p>
                    </div>
                    <div className="rounded-xl border border-orange-200 dark:border-orange-900 bg-orange-50 dark:bg-orange-950/20 p-4">
                        <div className="flex items-center gap-2 text-orange-500 text-xs mb-1">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Requests at Risk
                        </div>
                        <div className="text-2xl font-bold text-orange-600">
                            {violationsData?.at_risk_count || 0}
                        </div>
                        <p className="text-[10px] text-orange-400 mt-0.5">Approaching SLA deadline</p>
                    </div>
                </div>
            )}

            {violationsData?.context_summary && !violationsError && (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 text-sm text-slate-600 dark:text-slate-300">
                    Tracking live requests in statuses {violationsData.context_summary.tracked_statuses.join(', ')}. {violationsData.context_summary.live_breaches} are currently over SLA and {violationsData.context_summary.requests_at_risk} are approaching breach.
                </div>
            )}

            {/* SLA History Chart */}
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
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={slaHistoryData?.chart_data || []}>
                            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-700" />
                            <XAxis
                                dataKey="date"
                                tick={{ fontSize: 11 }}
                                angle={-45}
                                textAnchor="end"
                                height={60}
                            />
                            <YAxis yAxisId="left" orientation="left" tick={{ fontSize: 11 }} />
                            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: 'var(--bg)',
                                    border: '1px solid var(--border)',
                                    borderRadius: '8px',
                                    fontSize: '12px'
                                }}
                                labelFormatter={(label) => `Date: ${label}`}
                                formatter={(value, name) => [
                                    value,
                                    name === 'violations' ? 'SLA Violations' : 'Avg Response Time (h)'
                                ]}
                            />
                            <Legend />
                            <Line
                                yAxisId="left"
                                type="monotone"
                                dataKey="violations"
                                stroke="#ef4444"
                                strokeWidth={2}
                                dot={{ fill: '#ef4444', strokeWidth: 2, r: 3 }}
                                activeDot={{ r: 6, stroke: '#ef4444', strokeWidth: 2 }}
                                name="SLA Violations"
                            />
                            <Line
                                yAxisId="right"
                                type="monotone"
                                dataKey="avg_response_time"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                dot={{ fill: '#3b82f6', strokeWidth: 2, r: 3 }}
                                activeDot={{ r: 6, stroke: '#3b82f6', strokeWidth: 2 }}
                                name="Avg Response Time"
                            />
                        </LineChart>
                    </ResponsiveContainer>
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

            {/* Violations Table with Action Buttons */}
            {loadingViolations ? (
                <div className="flex justify-center py-12">
                    <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
                </div>
            ) : violations.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                    <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-400" />
                    <p className="font-medium">All requests within SLA limits</p>
                    <p className="text-sm">No violations detected</p>
                </div>
            ) : (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-800">
                            <tr>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Request</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Type</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Status</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Violation</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Elapsed</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Escalated</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                            {violations.map((v) => (
                                <tr key={v.request_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-400">
                                        <button
                                            onClick={() => {
                                                toast.success(`Viewing details for ${v.request_id.slice(0, 8)}`)
                                            }}
                                            className="text-blue-500 hover:text-blue-700 underline decoration-dotted"
                                        >
                                            {v.request_id.slice(0, 8)}...
                                        </button>
                                    </td>
                                    <td className="px-4 py-3">{v.resource_type}</td>
                                    <td className="px-4 py-3">
                                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                                            {v.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${v.type === 'no_response' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                                v.type === 'stalled_assignment' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                                                    'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                                            }`}>
                                            {v.type.replace(/_/g, ' ')}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`font-medium ${v.hours_elapsed > v.sla_hours * 2 ? 'text-red-600' : 'text-amber-600'}`}>
                                            {v.hours_elapsed}h
                                        </span>
                                        <span className="text-slate-400 ml-1">/ {v.sla_hours}h</span>
                                    </td>
                                    <td className="px-4 py-3">
                                        {v.escalated ? (
                                            <span className="text-red-500 font-medium">Yes</span>
                                        ) : (
                                            <span className="text-slate-400">No</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-1">
                                            {!v.escalated && (
                                                <button
                                                    onClick={() => {
                                                        toast.success(`Escalating ${v.request_id.slice(0, 8)}...`)
                                                        escalateMutation.mutate(v.request_id)
                                                    }}
                                                    disabled={escalateMutation.isPending}
                                                    className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-red-500 transition-colors disabled:opacity-50"
                                                    title="Escalate"
                                                >
                                                    {escalateMutation.isPending && escalateMutation.variables === v.request_id ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ArrowUpCircle className="w-4 h-4" />}
                                                </button>
                                            )}
                                            {v.escalated && (
                                                <button
                                                    onClick={() => {
                                                        toast.success(`Marking ${v.request_id.slice(0, 8)} as resolved...`)
                                                        // Add resolve mutation here
                                                    }}
                                                    className="p-1.5 rounded-lg hover:bg-green-50 dark:hover:bg-green-500/10 text-green-500 transition-colors"
                                                    title="Mark Resolved"
                                                >
                                                    <CheckCircle className="w-4 h-4" />
                                                </button>
                                            )}
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
                                            <button
                                                onClick={() => {
                                                    toast.success(`Viewing details for ${v.request_id.slice(0, 8)}`)
                                                }}
                                                className="p-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/10 text-blue-500 transition-colors"
                                                title="View Details"
                                            >
                                                <Eye className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
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
