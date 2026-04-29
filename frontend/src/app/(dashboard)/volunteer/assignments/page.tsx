'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Package, Search, MapPin, Clock, AlertTriangle,
    CheckCircle2, Loader2, ChevronRight, Calendar,
    CheckCheck, X, Filter, ChevronLeft
} from 'lucide-react'
import { cn } from '@/lib/utils'

const PRIORITY_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
    critical: { bg: 'bg-red-100 dark:bg-red-500/10', text: 'text-red-700 dark:text-red-400', dot: 'bg-red-500 animate-pulse' },
    high:     { bg: 'bg-orange-100 dark:bg-orange-500/10', text: 'text-orange-700 dark:text-orange-400', dot: 'bg-orange-500' },
    medium:   { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400', dot: 'bg-amber-400' },
    low:      { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-700 dark:text-green-400', dot: 'bg-green-500' },
}

const RESOURCE_ICONS: Record<string, string> = {
    food: '🍱', water: '💧', medicine: '💊', clothes: '👕',
    blankets: '🛏️', shelter: '🏠', emergency_kit: '🧰', volunteers: '🙋',
}

export default function VolunteerTasksPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [resourceFilter, setResourceFilter] = useState('all')
    const [selected, setSelected] = useState<any>(null)
    const [arrivalNote, setArrivalNote] = useState('')

    const { data, isLoading } = useQuery({
        queryKey: ['volunteer-tasks'],
        queryFn: () => api.getVolunteerAvailableTasks(),
        refetchInterval: 30000,
    })

    const acceptMutation = useMutation({
        mutationFn: (requestId: string) =>
            api.acceptDeliveryTask(requestId, { notes: arrivalNote || undefined }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-tasks'] })
            queryClient.invalidateQueries({ queryKey: ['volunteer-assigned'] })
            setSelected(null)
            setArrivalNote('')
        },
    })

    const tasks: any[] = data?.tasks || []

    const resourceTypes = useMemo(() => {
        const types = [...new Set(tasks.map((t: any) => t.resource_type).filter(Boolean))]
        return types
    }, [tasks])

    const filtered = useMemo(() => {
        return tasks.filter((t: any) => {
            const matchSearch = !search ||
                (t.resource_type || '').toLowerCase().includes(search.toLowerCase()) ||
                (t.description || '').toLowerCase().includes(search.toLowerCase()) ||
                (t.disaster?.title || '').toLowerCase().includes(search.toLowerCase()) ||
                (t.location?.name || '').toLowerCase().includes(search.toLowerCase())
            const matchResource = resourceFilter === 'all' || t.resource_type === resourceFilter
            return matchSearch && matchResource
        })
    }, [tasks, search, resourceFilter])

    // Pagination
    const [taskPage, setTaskPage] = useState(1)
    const TASKS_PER_PAGE = 8
    const taskTotalPages = Math.max(1, Math.ceil(filtered.length / TASKS_PER_PAGE))
    const pagedTasks = filtered.slice((taskPage - 1) * TASKS_PER_PAGE, taskPage * TASKS_PER_PAGE)

    // Reset page when filters change
    useMemo(() => { setTaskPage(1) }, [search, resourceFilter])

    const stats = {
        total: tasks.length,
        critical: tasks.filter((t: any) => t.priority === 'critical').length,
        high: tasks.filter((t: any) => t.priority === 'high').length,
        fullyFunded: tasks.filter((t: any) => (t.fulfillment_pct || 0) >= 100).length,
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-purple-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Available Tasks</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Victim aid requests waiting for volunteer delivery
                </p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { label: 'Open Tasks', value: stats.total, color: 'blue', icon: Package },
                    { label: 'Critical', value: stats.critical, color: 'red', icon: AlertTriangle },
                    { label: 'High Priority', value: stats.high, color: 'orange', icon: Clock },
                    { label: 'Fully Funded', value: stats.fullyFunded, color: 'green', icon: CheckCircle2 },
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
                        placeholder="Search by resource, location, disaster..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                </div>
                <div className="flex items-center gap-2">
                    <Filter className="w-4 h-4 text-slate-400" />
                    <select value={resourceFilter} onChange={e => setResourceFilter(e.target.value)}
                        className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                        <option value="all">All Types</option>
                        {resourceTypes.map(t => (
                            <option key={t} value={t}>{t}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Task Cards */}
            <div className="space-y-3">
                {pagedTasks.map((task: any) => {
                    const ps = PRIORITY_STYLES[task.priority] || PRIORITY_STYLES.medium
                    const icon = RESOURCE_ICONS[task.resource_type?.toLowerCase()] || '📦'
                    return (
                        <button key={task.id} onClick={() => setSelected(task)}
                            className="w-full text-left rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg hover:border-purple-200 dark:hover:border-purple-500/30 transition-all group">
                            <div className="flex items-center gap-4">
                                <div className="text-2xl">{icon}</div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white capitalize">
                                            {task.resource_type || 'Aid'} — {task.quantity || '?'} units
                                        </h3>
                                        <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', ps.bg, ps.text)}>
                                            {task.priority}
                                        </span>
                                        {(task.fulfillment_pct || 0) >= 100 && (
                                            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400">
                                                Funded
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
                                        {task.disaster?.title && (
                                            <span className="flex items-center gap-1">
                                                <AlertTriangle className="w-3 h-3" />{task.disaster.title}
                                            </span>
                                        )}
                                        {task.location?.name && (
                                            <span className="flex items-center gap-1">
                                                <MapPin className="w-3 h-3" />{task.location.name}
                                            </span>
                                        )}
                                        {task.distance_km != null && (
                                            <span>{task.distance_km} km away</span>
                                        )}
                                        <span className="flex items-center gap-1">
                                            <Calendar className="w-3 h-3" />
                                            {task.created_at ? new Date(task.created_at).toLocaleDateString() : 'N/A'}
                                        </span>
                                    </div>
                                    {task.description && (
                                        <p className="text-xs text-slate-400 mt-1 truncate">{task.description}</p>
                                    )}
                                </div>
                                <div className="flex flex-col items-end gap-2 shrink-0">
                                    {task.fulfillment_pct != null && (
                                        <div className="text-right">
                                            <p className="text-[10px] text-slate-400">Funded</p>
                                            <p className="text-xs font-bold text-slate-700 dark:text-slate-300">{task.fulfillment_pct}%</p>
                                        </div>
                                    )}
                                    <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
                                </div>
                            </div>
                        </button>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Package className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No tasks found</p>
                    <p className="text-xs text-slate-500 mt-1">Tasks appear when victims raise requests and admin approves them</p>
                </div>
            )}

            {/* Pagination */}
            {taskTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-400">{filtered.length} task{filtered.length !== 1 ? 's' : ''}</p>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setTaskPage(p => Math.max(1, p - 1))}
                            disabled={taskPage <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft className="w-3 h-3" /> Prev
                        </button>
                        <span className="text-xs font-bold text-slate-500">{taskPage} / {taskTotalPages}</span>
                        <button
                            onClick={() => setTaskPage(p => Math.min(taskTotalPages, p + 1))}
                            disabled={taskPage >= taskTotalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            Next <ChevronRight className="w-3 h-3" />
                        </button>
                    </div>
                </div>
            )}

            {/* Task Detail Modal */}
            {selected && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setSelected(null)}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <span className="text-3xl">{RESOURCE_ICONS[selected.resource_type?.toLowerCase()] || '📦'}</span>
                                <div>
                                    <h2 className="text-lg font-bold text-slate-900 dark:text-white capitalize">
                                        {selected.resource_type} Request
                                    </h2>
                                    <p className="text-xs text-slate-500">{selected.location?.name || 'Location TBD'}</p>
                                </div>
                            </div>
                            <button onClick={() => setSelected(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                <X className="w-4 h-4 text-slate-400" />
                            </button>
                        </div>

                        <div className="space-y-3 text-sm mb-5">
                            <div className="grid grid-cols-2 gap-3">
                                <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                    <p className="text-xs text-slate-400 mb-1">Quantity</p>
                                    <p className="font-semibold text-slate-900 dark:text-white">{selected.quantity || 'N/A'} units</p>
                                </div>
                                <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                    <p className="text-xs text-slate-400 mb-1">Priority</p>
                                    <p className={cn('font-semibold capitalize', PRIORITY_STYLES[selected.priority]?.text)}>{selected.priority}</p>
                                </div>
                                <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                    <p className="text-xs text-slate-400 mb-1">Funded</p>
                                    <p className="font-semibold text-slate-900 dark:text-white">{selected.fulfillment_pct || 0}%</p>
                                </div>
                                <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                    <p className="text-xs text-slate-400 mb-1">Status</p>
                                    <p className="font-semibold text-slate-900 dark:text-white capitalize">{selected.status}</p>
                                </div>
                            </div>
                            {selected.disaster?.title && (
                                <div className="rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-100 dark:border-red-500/20 p-3">
                                    <p className="text-xs text-red-500 mb-1">Related Disaster</p>
                                    <p className="font-medium text-red-700 dark:text-red-400">{selected.disaster.title}</p>
                                    <p className="text-xs text-red-400 capitalize">{selected.disaster.type} · {selected.disaster.severity}</p>
                                </div>
                            )}
                            {selected.description && (
                                <p className="text-slate-600 dark:text-slate-400 text-xs leading-relaxed pt-2 border-t border-slate-100 dark:border-white/5">
                                    {selected.description}
                                </p>
                            )}
                        </div>

                        <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-white/5">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Accept this delivery task</h3>
                            <textarea
                                value={arrivalNote}
                                onChange={e => setArrivalNote(e.target.value)}
                                placeholder="Any notes? (e.g. estimated arrival time, vehicle type)"
                                rows={2}
                                className="w-full text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500"
                            />
                            {acceptMutation.isError && (
                                <p className="text-xs text-red-500">{(acceptMutation.error as any)?.message || 'Failed to accept task'}</p>
                            )}
                            <div className="flex gap-2">
                                <button onClick={() => setSelected(null)}
                                    className="flex-1 h-10 rounded-xl bg-slate-100 dark:bg-white/5 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
                                    Cancel
                                </button>
                                <button
                                    onClick={() => acceptMutation.mutate(selected.id)}
                                    disabled={acceptMutation.isPending}
                                    className="flex-1 h-10 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                                    {acceptMutation.isPending
                                        ? <Loader2 className="w-4 h-4 animate-spin" />
                                        : <CheckCheck className="w-4 h-4" />}
                                    Accept Task
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}