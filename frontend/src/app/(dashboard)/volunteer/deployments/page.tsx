'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Rocket, Search, MapPin, Calendar, Clock,
    CheckCircle2, Loader2, ChevronDown, ChevronUp,
    LogOut, AlertTriangle, X, ChevronLeft, ChevronRight
} from 'lucide-react'
import { cn } from '@/lib/utils'

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
    active:    { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400', dot: 'bg-blue-500 animate-pulse' },
    completed: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-700 dark:text-green-400', dot: 'bg-green-500' },
}

export default function VolunteerDeploymentsPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('all')
    const [expanded, setExpanded] = useState<string | null>(null)
    const [checkoutNotes, setCheckoutNotes] = useState('')
    const [checkingOut, setCheckingOut] = useState<string | null>(null)
    const [isCheckingIn, setIsCheckingIn] = useState(false)
    const [checkInDisaster, setCheckInDisaster] = useState('')
    const [checkInTask, setCheckInTask] = useState('')

    const { data: disastersData } = useQuery({
        queryKey: ['available-disasters'],
        queryFn: () => api.getVolunteerAvailableDisasters(),
        enabled: isCheckingIn
    })

    const { data: historyData, isLoading } = useQuery({
        queryKey: ['volunteer-ops-history'],
        queryFn: () => api.getVolunteerOpsHistory({ limit: 100 }),
        refetchInterval: 30000,
    })

    const { data: activeData } = useQuery({
        queryKey: ['active-deployment'],
        queryFn: () => api.getActiveDeployment(),
        refetchInterval: 15000,
    })

    const checkOutMutation = useMutation({
        mutationFn: ({ opId, notes }: { opId: string; notes: string }) =>
            api.checkOutVolunteer(opId, { notes }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-ops-history'] })
            queryClient.invalidateQueries({ queryKey: ['active-deployment'] })
            queryClient.invalidateQueries({ queryKey: ['volunteer-stats'] })
            setCheckingOut(null)
            setCheckoutNotes('')
        },
    })

    const checkInMutation = useMutation({
        mutationFn: (data: { disaster_id: string; task_description: string }) =>
            api.checkInVolunteer(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-ops-history'] })
            queryClient.invalidateQueries({ queryKey: ['active-deployment'] })
            queryClient.invalidateQueries({ queryKey: ['volunteer-stats'] })
            setIsCheckingIn(false)
            setCheckInDisaster('')
            setCheckInTask('')
        },
    })

    const ops: any[] = historyData?.ops || []
    const activeDeployment = activeData?.active_deployment

    const filtered = useMemo(() => {
        return ops.filter((op: any) => {
            const matchSearch = !search ||
                (op.task_description || '').toLowerCase().includes(search.toLowerCase()) ||
                (op.disaster?.title || '').toLowerCase().includes(search.toLowerCase()) ||
                (op.notes || '').toLowerCase().includes(search.toLowerCase())
            const matchStatus = statusFilter === 'all' || op.status === statusFilter
            return matchSearch && matchStatus
        })
    }, [ops, search, statusFilter])

    // Pagination
    const [opsPage, setOpsPage] = useState(1)
    const OPS_PER_PAGE = 8
    const opsTotalPages = Math.max(1, Math.ceil(filtered.length / OPS_PER_PAGE))
    const pagedOps = filtered.slice((opsPage - 1) * OPS_PER_PAGE, opsPage * OPS_PER_PAGE)
    useMemo(() => { setOpsPage(1) }, [search, statusFilter])

    const stats = {
        total: ops.length,
        active: ops.filter((o: any) => o.status === 'active').length,
        completed: ops.filter((o: any) => o.status === 'completed').length,
        totalHours: ops.reduce((sum: number, o: any) => sum + (o.hours_worked || 0), 0),
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-purple-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Deployment History</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Your check-in and check-out records</p>
                </div>
                {!activeDeployment && (
                    <button onClick={() => setIsCheckingIn(true)}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 transition-colors">
                        <MapPin className="w-4 h-4" /> Start Check-In
                    </button>
                )}
            </div>

            {/* Check-In Modal */}
            {isCheckingIn && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Check Into Disaster Zone</h2>
                            <button onClick={() => setIsCheckingIn(false)}><X className="w-4 h-4 text-slate-400" /></button>
                        </div>
                        <div className="space-y-3 mb-5">
                            <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Select Disaster Zone</label>
                            <select
                                value={checkInDisaster}
                                onChange={e => setCheckInDisaster(e.target.value)}
                                className="w-full text-sm h-10 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            >
                                <option value="" disabled>Select active disaster...</option>
                                {(disastersData?.disasters || []).map((d: any) => (
                                    <option key={d.id} value={d.id}>{d.title} ({d.location_name})</option>
                                ))}
                            </select>

                            <label className="text-xs font-medium text-slate-700 dark:text-slate-300 block mt-3">Task / Role Description</label>
                            <input
                                value={checkInTask}
                                onChange={e => setCheckInTask(e.target.value)}
                                placeholder="e.g. Medical Triage, Debris Removal"
                                className="w-full text-sm h-10 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            />
                            {checkInMutation.isError && (
                                <p className="text-xs text-red-500">{(checkInMutation.error as any)?.message || 'Failed to check-in'}</p>
                            )}
                        </div>
                        <div className="flex gap-2">
                            <button onClick={() => setIsCheckingIn(false)}
                                className="flex-1 h-10 rounded-xl bg-slate-100 dark:bg-white/5 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
                                Cancel
                            </button>
                            <button
                                onClick={() => checkInMutation.mutate({ disaster_id: checkInDisaster, task_description: checkInTask })}
                                disabled={checkInMutation.isPending || !checkInDisaster || !checkInTask}
                                className="flex-1 h-10 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                                {checkInMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                                Confirm Form
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Active deployment banner */}
            {activeDeployment && (
                <div className="rounded-2xl bg-blue-600 text-white p-5">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                                <p className="text-sm font-semibold">Currently Deployed</p>
                            </div>
                            <p className="text-blue-100 text-sm">{activeDeployment.task_description || 'General volunteer support'}</p>
                            {activeDeployment.disaster_title && (
                                <p className="text-blue-200 text-xs mt-1">{activeDeployment.disaster_title}</p>
                            )}
                            <p className="text-blue-200 text-xs mt-1">
                                Since {activeDeployment.check_in_time ? new Date(activeDeployment.check_in_time).toLocaleString() : 'N/A'}
                            </p>
                        </div>
                        <button
                            onClick={() => setCheckingOut(activeDeployment.id)}
                            className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl bg-white/20 hover:bg-white/30 text-sm font-medium transition-colors">
                            <LogOut className="w-4 h-4" /> Check Out
                        </button>
                    </div>

                    {checkingOut === activeDeployment.id && (
                        <div className="mt-4 pt-4 border-t border-white/20 space-y-3">
                            <textarea
                                value={checkoutNotes}
                                onChange={e => setCheckoutNotes(e.target.value)}
                                placeholder="What did you accomplish? (optional)"
                                rows={2}
                                className="w-full text-sm px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-blue-200 resize-none focus:outline-none"
                            />
                            <div className="flex gap-2">
                                <button onClick={() => setCheckingOut(null)}
                                    className="flex-1 h-9 rounded-lg bg-white/10 text-sm hover:bg-white/20 transition-colors">
                                    Cancel
                                </button>
                                <button
                                    onClick={() => checkOutMutation.mutate({ opId: activeDeployment.id, notes: checkoutNotes })}
                                    disabled={checkOutMutation.isPending}
                                    className="flex-1 h-9 rounded-lg bg-white text-blue-700 font-semibold text-sm flex items-center justify-center gap-2 hover:bg-blue-50 transition-colors disabled:opacity-60">
                                    {checkOutMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                                    Confirm Check-Out
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { icon: Rocket, color: 'blue', label: 'Total Deployments', value: stats.total },
                    { icon: AlertTriangle, color: 'amber', label: 'Active', value: stats.active },
                    { icon: CheckCircle2, color: 'green', label: 'Completed', value: stats.completed },
                    { icon: Clock, color: 'purple', label: 'Total Hours', value: `${stats.totalHours.toFixed(1)}h` },
                ].map((s, i) => (
                    <div key={i} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl bg-${s.color}-100 dark:bg-${s.color}-500/10 flex items-center justify-center`}>
                                <s.icon className={`w-5 h-5 text-${s.color}-600 dark:text-${s.color}-400`} />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-slate-900 dark:text-white">{s.value}</p>
                                <p className="text-xs text-slate-500">{s.label}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Search by task, disaster, notes..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                </div>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All</option>
                    <option value="active">Active</option>
                    <option value="completed">Completed</option>
                </select>
            </div>

            {/* Ops list */}
            <div className="space-y-3">
                {pagedOps.map((op: any) => {
                    const sc = STATUS_COLORS[op.status] || STATUS_COLORS.completed
                    const isExpanded = expanded === op.id
                    return (
                        <div key={op.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                            <button onClick={() => setExpanded(isExpanded ? null : op.id)}
                                className="w-full text-left p-5 flex items-center gap-4">
                                <div className="flex flex-col items-center gap-1 shrink-0">
                                    <div className={cn('w-3 h-3 rounded-full', sc.dot)} />
                                    <div className="w-px h-6 bg-slate-200 dark:bg-white/10" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">
                                            {op.task_description || 'General deployment'}
                                        </h3>
                                        <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', sc.bg, sc.text)}>
                                            {op.status}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
                                        {op.disaster?.title && (
                                            <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{op.disaster.title}</span>
                                        )}
                                        <span className="flex items-center gap-1">
                                            <Calendar className="w-3 h-3" />
                                            {op.check_in_time ? new Date(op.check_in_time).toLocaleDateString() : 'N/A'}
                                        </span>
                                        {op.hours_worked != null && (
                                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{op.hours_worked}h</span>
                                        )}
                                    </div>
                                </div>
                                {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />}
                            </button>

                            {isExpanded && (
                                <div className="px-5 pb-5 border-t border-slate-100 dark:border-white/5">
                                    <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Check-in</p>
                                            <p className="font-medium text-slate-900 dark:text-white text-xs">
                                                {op.check_in_time ? new Date(op.check_in_time).toLocaleString() : 'N/A'}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Check-out</p>
                                            <p className="font-medium text-slate-900 dark:text-white text-xs">
                                                {op.check_out_time ? new Date(op.check_out_time).toLocaleString() : 'Still deployed'}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Hours worked</p>
                                            <p className="font-medium text-slate-900 dark:text-white">{op.hours_worked ?? '—'}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Disaster type</p>
                                            <p className="font-medium text-slate-900 dark:text-white capitalize">{op.disaster?.type || '—'}</p>
                                        </div>
                                    </div>
                                    {op.notes && (
                                        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-white/5 pt-3">
                                            <span className="font-medium">Notes: </span>{op.notes}
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Rocket className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No deployments yet</p>
                    <p className="text-xs text-slate-500 mt-1">Check into a disaster zone to start logging your deployments</p>
                </div>
            )}

            {/* Pagination */}
            {opsTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-400">{filtered.length} deployment{filtered.length !== 1 ? 's' : ''}</p>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setOpsPage(p => Math.max(1, p - 1))}
                            disabled={opsPage <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft className="w-3 h-3" /> Prev
                        </button>
                        <span className="text-xs font-bold text-slate-500">{opsPage} / {opsTotalPages}</span>
                        <button
                            onClick={() => setOpsPage(p => Math.min(opsTotalPages, p + 1))}
                            disabled={opsPage >= opsTotalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            Next <ChevronRight className="w-3 h-3" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}