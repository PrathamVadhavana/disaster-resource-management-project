'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSLAConfig, updateSLAConfig, getSLAViolations, type SLAConfig, type SLAViolation } from '@/lib/api/workflow'
import { useState } from 'react'
import { Clock, AlertTriangle, Settings, Loader2, CheckCircle, Shield, TrendingUp } from 'lucide-react'

export function SLADashboard() {
    const queryClient = useQueryClient()
    const [editing, setEditing] = useState(false)
    const [config, setConfig] = useState<Partial<SLAConfig>>({})

    const { data: slaConfig, isLoading: loadingConfig } = useQuery({
        queryKey: ['sla-config'],
        queryFn: getSLAConfig,
    })

    const { data: violationsData, isLoading: loadingViolations } = useQuery({
        queryKey: ['sla-violations'],
        queryFn: getSLAViolations,
        refetchInterval: 30000, // refresh every 30s
    })

    const updateMutation = useMutation({
        mutationFn: (data: Partial<SLAConfig>) => updateSLAConfig(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sla-config'] })
            setEditing(false)
        },
    })

    const violations = violationsData?.violations || []
    const criticalCount = violations.filter(v => v.hours_elapsed > v.sla_hours * 2).length
    const warningCount = violations.length - criticalCount

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

            {/* Stats Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                    <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
                        <Shield className="w-4 h-4" />
                        SLA Status
                    </div>
                    <div className={`text-2xl font-bold ${violations.length === 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {violations.length === 0 ? 'All Clear' : `${violations.length} Violations`}
                    </div>
                </div>
                <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 p-4">
                    <div className="flex items-center gap-2 text-red-500 text-sm mb-1">
                        <AlertTriangle className="w-4 h-4" />
                        Critical (2x+ SLA)
                    </div>
                    <div className="text-2xl font-bold text-red-600">{criticalCount}</div>
                </div>
                <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/20 p-4">
                    <div className="flex items-center gap-2 text-amber-500 text-sm mb-1">
                        <TrendingUp className="w-4 h-4" />
                        Warning (1x SLA)
                    </div>
                    <div className="text-2xl font-bold text-amber-600">{warningCount}</div>
                </div>
            </div>

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

            {/* Violations Table */}
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
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                            {violations.map((v) => (
                                <tr key={v.request_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-400">
                                        {v.request_id.slice(0, 8)}...
                                    </td>
                                    <td className="px-4 py-3">{v.resource_type}</td>
                                    <td className="px-4 py-3">
                                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                                            {v.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                            v.type === 'no_response' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
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
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
