'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    PackageCheck, Search, MapPin, Loader2, ChevronDown, ChevronUp,
    Truck, CheckCircle2, AlertTriangle, X, Upload, KeyRound
} from 'lucide-react'
import { cn } from '@/lib/utils'

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string; next: string | null; nextLabel: string | null }> = {
    volunteered:  { label: 'Accepted',     bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-700 dark:text-purple-400', next: 'in_progress', nextLabel: 'Start Delivery' },
    assigned:     { label: 'Assigned',     bg: 'bg-blue-100 dark:bg-blue-500/10',     text: 'text-blue-700 dark:text-blue-400',     next: 'in_progress', nextLabel: 'Start Delivery' },
    in_progress:  { label: 'In Progress',  bg: 'bg-amber-100 dark:bg-amber-500/10',   text: 'text-amber-700 dark:text-amber-400',   next: 'delivered',   nextLabel: 'Mark Delivered' },
    delivered:    { label: 'Delivered',    bg: 'bg-teal-100 dark:bg-teal-500/10',     text: 'text-teal-700 dark:text-teal-400',     next: 'completed',   nextLabel: 'Confirm Complete' },
    completed:    { label: 'Completed',    bg: 'bg-green-100 dark:bg-green-500/10',   text: 'text-green-700 dark:text-green-400',   next: null,          nextLabel: null },
}

const RESOURCE_ICONS: Record<string, string> = {
    food: '🍱', water: '💧', medicine: '💊', clothes: '👕',
    blankets: '🛏️', shelter: '🏠', emergency_kit: '🧰', volunteers: '🙋',
}

export default function VolunteerDeliveriesPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('all')
    const [expanded, setExpanded] = useState<string | null>(null)
    const [actionRequest, setActionRequest] = useState<any>(null)
    const [proofUrl, setProofUrl] = useState('')
    const [deliveryCode, setDeliveryCode] = useState('')
    const [statusNotes, setStatusNotes] = useState('')

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['volunteer-assigned'],
        queryFn: () => api.getVolunteerAssignedRequests(),
        refetchInterval: 30000,
    })

    const updateMutation = useMutation({
        mutationFn: ({ requestId, newStatus }: { requestId: string; newStatus: string }) =>
            api.updateDeliveryStatus(requestId, {
                new_status: newStatus,
                notes: statusNotes || undefined,
                proof_url: proofUrl || undefined,
                delivery_code: deliveryCode || undefined,
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-assigned'] })
            queryClient.invalidateQueries({ queryKey: ['volunteer-stats'] })
            setActionRequest(null)
            setProofUrl('')
            setDeliveryCode('')
            setStatusNotes('')
        },
    })

    const requests: any[] = data?.requests || []

    const filtered = useMemo(() => {
        return requests.filter((r: any) => {
            const matchSearch = !search ||
                (r.resource_type || '').toLowerCase().includes(search.toLowerCase()) ||
                (r.victim_name || '').toLowerCase().includes(search.toLowerCase()) ||
                (r.description || '').toLowerCase().includes(search.toLowerCase())
            const myStatus = r.my_entry?.status || r.status
            const matchStatus = statusFilter === 'all' || myStatus === statusFilter || r.status === statusFilter
            return matchSearch && matchStatus
        })
    }, [requests, search, statusFilter])

    const stats = {
        total: requests.length,
        active: requests.filter((r: any) => ['assigned', 'in_progress', 'volunteered'].includes(r.status)).length,
        delivered: requests.filter((r: any) => r.status === 'delivered').length,
        completed: requests.filter((r: any) => r.status === 'completed').length,
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-purple-500" /></div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Deliveries</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Track and update your accepted delivery tasks</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                {[
                    { label: 'Total Tasks', value: stats.total, color: 'blue', icon: PackageCheck },
                    { label: 'In Progress', value: stats.active, color: 'amber', icon: Truck },
                    { label: 'Delivered', value: stats.delivered, color: 'teal', icon: CheckCircle2 },
                    { label: 'Completed', value: stats.completed, color: 'green', icon: CheckCircle2 },
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
                        placeholder="Search by resource type, victim, notes..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                </div>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All Status</option>
                    <option value="assigned">Assigned</option>
                    <option value="in_progress">In Progress</option>
                    <option value="delivered">Delivered</option>
                    <option value="completed">Completed</option>
                </select>
            </div>

            {/* Delivery Cards */}
            <div className="space-y-3">
                {filtered.map((req: any) => {
                    const myStatus = req.my_entry?.status || req.status
                    const sc = STATUS_CONFIG[myStatus] || STATUS_CONFIG.assigned
                    const icon = RESOURCE_ICONS[req.resource_type?.toLowerCase()] || '📦'
                    const isExpanded = expanded === req.id
                    return (
                        <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                            <button onClick={() => setExpanded(isExpanded ? null : req.id)}
                                className="w-full text-left p-5 flex items-center gap-4">
                                <span className="text-2xl shrink-0">{icon}</span>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white capitalize">
                                            {req.resource_type} — {req.quantity} units
                                        </h3>
                                        <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', sc.bg, sc.text)}>
                                            {sc.label}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
                                        {req.victim_name && (
                                            <span>For: {req.victim_name}</span>
                                        )}
                                        {req.estimated_delivery && (
                                            <span>ETA: {new Date(req.estimated_delivery).toLocaleDateString()}</span>
                                        )}
                                        {req.latitude && (
                                            <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />Location set</span>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 shrink-0">
                                    {sc.next && (
                                        <button
                                            onClick={e => { e.stopPropagation(); setActionRequest({ ...req, nextStatus: sc.next, nextLabel: sc.nextLabel }) }}
                                            className="px-3 py-1.5 rounded-lg bg-purple-600 text-white text-xs font-semibold hover:bg-purple-700 transition-colors">
                                            {sc.nextLabel}
                                        </button>
                                    )}
                                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                                </div>
                            </button>

                            {isExpanded && (
                                <div className="px-5 pb-5 border-t border-slate-100 dark:border-white/5">
                                    <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Priority</p>
                                            <p className="font-medium text-slate-900 dark:text-white capitalize">{req.priority || '—'}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Request status</p>
                                            <p className="font-medium text-slate-900 dark:text-white capitalize">{req.status}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Accepted on</p>
                                            <p className="font-medium text-slate-900 dark:text-white text-xs">
                                                {req.my_entry?.created_at ? new Date(req.my_entry.created_at).toLocaleString() : '—'}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 mb-1">Victim</p>
                                            <p className="font-medium text-slate-900 dark:text-white">{req.victim_name || '—'}</p>
                                        </div>
                                    </div>
                                    {req.description && (
                                        <p className="mt-3 text-xs text-slate-500 border-t border-slate-100 dark:border-white/5 pt-3">{req.description}</p>
                                    )}
                                    {req.my_entry?.proof_url && (
                                        <div className="mt-3 pt-3 border-t border-slate-100 dark:border-white/5">
                                            <p className="text-xs text-slate-400 mb-1">Delivery proof</p>
                                            <a href={req.my_entry.proof_url} target="_blank" rel="noopener noreferrer"
                                                className="text-xs text-purple-600 underline">View proof</a>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <PackageCheck className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No deliveries yet</p>
                    <p className="text-xs text-slate-500 mt-1">Accept tasks from the Assignments page to see them here</p>
                </div>
            )}

            {/* Status Update Modal */}
            {actionRequest && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setActionRequest(null)}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">{actionRequest.nextLabel}</h2>
                            <button onClick={() => setActionRequest(null)}><X className="w-4 h-4 text-slate-400" /></button>
                        </div>

                        <div className="space-y-3 mb-5">
                            <p className="text-sm text-slate-500">
                                Updating <span className="font-medium text-slate-900 dark:text-white capitalize">{actionRequest.resource_type}</span> delivery to <span className="font-medium text-purple-600">{actionRequest.nextStatus}</span>
                            </p>

                            <textarea
                                value={statusNotes}
                                onChange={e => setStatusNotes(e.target.value)}
                                placeholder="Notes (optional)"
                                rows={2}
                                className="w-full text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500"
                            />

                            {actionRequest.nextStatus === 'delivered' && (
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1">
                                        <Upload className="w-3 h-3" /> Proof of delivery URL
                                    </label>
                                    <input
                                        value={proofUrl}
                                        onChange={e => setProofUrl(e.target.value)}
                                        placeholder="https://... (photo or document)"
                                        className="w-full text-sm h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                                    />
                                    <p className="text-xs text-slate-400">A confirmation code will be sent to the victim to verify receipt.</p>
                                </div>
                            )}

                            {actionRequest.nextStatus === 'completed' && (
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1">
                                        <KeyRound className="w-3 h-3" /> Victim confirmation code
                                    </label>
                                    <input
                                        value={deliveryCode}
                                        onChange={e => setDeliveryCode(e.target.value)}
                                        placeholder="Enter code provided by victim"
                                        className="w-full text-sm h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                                    />
                                </div>
                            )}

                            {updateMutation.isError && (
                                <p className="text-xs text-red-500">{(updateMutation.error as any)?.message || 'Update failed'}</p>
                            )}
                        </div>

                        <div className="flex gap-2">
                            <button onClick={() => setActionRequest(null)}
                                className="flex-1 h-10 rounded-xl bg-slate-100 dark:bg-white/5 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
                                Cancel
                            </button>
                            <button
                                onClick={() => updateMutation.mutate({ requestId: actionRequest.id, newStatus: actionRequest.nextStatus })}
                                disabled={updateMutation.isPending}
                                className="flex-1 h-10 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 flex items-center justify-center gap-2 transition-colors disabled:opacity-50">
                                {updateMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                                Confirm
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}