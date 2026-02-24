'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    ClipboardList, Search, MapPin, Clock, AlertTriangle,
    CheckCircle2, Filter, Loader2, ChevronRight, Calendar,
    Play
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ChatRoom } from '@/components/shared/ChatRoom'
import { useAuth } from '@/lib/auth-provider'

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
    active: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400', label: 'Active' },
    monitoring: { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400', label: 'Monitoring' },
    resolved: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-700 dark:text-green-400', label: 'Resolved' },
}

const SEVERITY_STYLES: Record<string, string> = {
    critical: 'text-red-600 dark:text-red-400',
    high: 'text-orange-600 dark:text-orange-400',
    medium: 'text-amber-600 dark:text-amber-400',
    low: 'text-green-600 dark:text-green-400',
}

const TYPE_ICONS: Record<string, string> = {
    earthquake: '🌍', flood: '🌊', hurricane: '🌀', wildfire: '🔥',
    tornado: '🌪️', tsunami: '🌊', drought: '☀️', volcano: '🌋',
}

export default function VolunteerAssignmentsPage() {
    const { user } = useAuth()
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState<string>('all')
    const [selected, setSelected] = useState<any>(null)
    const [taskDesc, setTaskDesc] = useState('')

    const { data: assignmentsData, isLoading, refetch } = useQuery({
        queryKey: ['volunteer-assignments'],
        queryFn: () => api.getVolunteerAvailableAssignments(),
        refetchInterval: 30000,
    })

    const checkInMutation = useMutation({
        mutationFn: (disasterId: string) => api.checkInVolunteer({
            disaster_id: disasterId,
            task_description: taskDesc || 'General volunteer support',
        }),
        onSuccess: () => {
            setSelected(null)
            setTaskDesc('')
            // Optionally could navigate to active deployment view or show success toast
            alert('Successfully checked in!')
        },
        onError: (err: any) => {
            alert('Failed to check in: ' + err.message)
        }
    })

    const assignments = Array.isArray(assignmentsData) ? assignmentsData.map((d: any) => ({
        id: d.id,
        title: d.title,
        type: d.type,
        severity: d.severity,
        status: d.status,
        location: d.location || 'Location TBD',
        description: d.description,
        created_at: d.created_at,
        resourcesNeeded: 0, // Simplified for brevity
        icon: TYPE_ICONS[d.type] || '⚠️',
    })) : []

    const filtered = useMemo(() => {
        return assignments.filter((a: any) => {
            const matchSearch = !search ||
                a.title.toLowerCase().includes(search.toLowerCase()) ||
                a.location.toLowerCase().includes(search.toLowerCase())
            const matchStatus = statusFilter === 'all' || a.status === statusFilter
            return matchSearch && matchStatus
        })
    }, [assignments, search, statusFilter])

    const stats = {
        total: assignments.length,
        active: assignments.filter(a => a.status === 'active').length,
        monitoring: assignments.filter(a => a.status === 'monitoring').length,
        critical: assignments.filter(a => a.severity === 'critical').length,
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Assignments</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Active disaster response missions requiring volunteer support</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { icon: ClipboardList, color: 'blue', label: 'Total Assignments', value: stats.total },
                    { icon: AlertTriangle, color: 'red', label: 'Active Missions', value: stats.active },
                    { icon: Clock, color: 'amber', label: 'Monitoring', value: stats.monitoring },
                    { icon: AlertTriangle, color: 'purple', label: 'Critical', value: stats.critical },
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
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search assignments..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All Status</option>
                    <option value="active">Active</option>
                    <option value="monitoring">Monitoring</option>
                </select>
            </div>

            {/* Assignment Cards */}
            <div className="space-y-3">
                {filtered.map(a => {
                    const ss = STATUS_STYLES[a.status] || STATUS_STYLES.active
                    return (
                        <button key={a.id} onClick={() => setSelected(a)}
                            className="w-full text-left rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg transition-all group">
                            <div className="flex items-center gap-4">
                                <div className="text-2xl">{a.icon}</div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">{a.title}</h3>
                                        <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', ss.bg, ss.text)}>{ss.label}</span>
                                        <span className={cn('text-[10px] font-semibold uppercase', SEVERITY_STYLES[a.severity])}>
                                            {a.severity}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-slate-500">
                                        <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{a.location}</span>
                                        <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{a.created_at ? new Date(a.created_at).toLocaleDateString() : 'N/A'}</span>
                                        <span>{a.resourcesNeeded} resources needed</span>
                                    </div>
                                </div>
                                <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
                            </div>
                        </button>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <ClipboardList className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No assignments found</p>
                    <p className="text-xs text-slate-500 mt-1">New missions will appear here when disasters occur</p>
                </div>
            )}

            {/* Detail Panel */}
            {selected && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setSelected(null)}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg p-6" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-3 mb-4">
                            <span className="text-3xl">{selected.icon}</span>
                            <div>
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">{selected.title}</h2>
                                <p className="text-xs text-slate-500">{selected.location}</p>
                            </div>
                        </div>
                        <div className="space-y-3 text-sm">
                            <p><span className="text-slate-500">Type:</span> <span className="capitalize text-slate-900 dark:text-white">{selected.type}</span></p>
                            <p><span className="text-slate-500">Severity:</span> <span className={cn('font-semibold capitalize', SEVERITY_STYLES[selected.severity])}>{selected.severity}</span></p>
                            <p><span className="text-slate-500">Status:</span> <span className="capitalize text-slate-900 dark:text-white">{selected.status}</span></p>
                            <p><span className="text-slate-500">Resources Needed:</span> <span className="text-slate-900 dark:text-white">{selected.resourcesNeeded}</span></p>
                            <p><span className="text-slate-500">Started:</span> <span className="text-slate-900 dark:text-white">{selected.created_at ? new Date(selected.created_at).toLocaleString() : 'N/A'}</span></p>
                            {selected.description && <p className="text-slate-600 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-white/5">{selected.description}</p>}
                        </div>

                        <div className="mt-5 space-y-3 pt-4 border-t border-slate-100 dark:border-white/5">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Check In to Deployment</h3>
                            <input
                                value={taskDesc} onChange={e => setTaskDesc(e.target.value)}
                                placeholder="What role/task are you fulfilling? (Optional)"
                                className="w-full text-sm h-10 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50"
                            />
                            <div className="flex gap-2">
                                <button onClick={() => setSelected(null)}
                                    className="flex-1 h-10 rounded-xl bg-slate-100 dark:bg-white/5 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
                                    Cancel
                                </button>
                                <button
                                    onClick={() => checkInMutation.mutate(selected.id)}
                                    disabled={checkInMutation.isPending}
                                    className="flex-1 h-10 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                                    {checkInMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                    Confirm Check-In
                                </button>
                            </div>
                        </div>

                        <div className="mt-5 space-y-3 pt-4 border-t border-slate-100 dark:border-white/5">
                            <ChatRoom disasterId={selected.id} currentUserId={user?.id} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
