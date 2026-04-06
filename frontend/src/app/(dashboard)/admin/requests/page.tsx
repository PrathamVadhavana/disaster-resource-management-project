'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
    Loader2, Search, Filter, CheckCircle2, XCircle, Clock,
    ChevronLeft, ChevronRight, AlertTriangle, Package, User,
    Eye, ThumbsUp, ThumbsDown, RefreshCw, ArrowUpDown,
    Calendar, Inbox, TrendingUp, X, Send, MessageSquare,
    Truck, FileCheck, Archive
} from 'lucide-react'

const STATUS_COLORS: Record<string, { bg: string; text: string; ring: string; icon: any }> = {
    pending: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-500/20', icon: Clock },
    approved: { bg: 'bg-green-500/10', text: 'text-green-600 dark:text-green-400', ring: 'ring-green-500/20', icon: CheckCircle2 },
    under_review: { bg: 'bg-indigo-500/10', text: 'text-indigo-600 dark:text-indigo-400', ring: 'ring-indigo-500/20', icon: Eye },
    availability_submitted: { bg: 'bg-cyan-500/10', text: 'text-cyan-600 dark:text-cyan-400', ring: 'ring-cyan-500/20', icon: FileCheck },
    assigned: { bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', ring: 'ring-blue-500/20', icon: User },
    in_progress: { bg: 'bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400', ring: 'ring-purple-500/20', icon: TrendingUp },
    delivered: { bg: 'bg-teal-500/10', text: 'text-teal-600 dark:text-teal-400', ring: 'ring-teal-500/20', icon: Truck },
    completed: { bg: 'bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400', ring: 'ring-emerald-500/20', icon: CheckCircle2 },
    closed: { bg: 'bg-slate-500/10', text: 'text-slate-600 dark:text-slate-400', ring: 'ring-slate-500/20', icon: Archive },
    rejected: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', ring: 'ring-red-500/20', icon: XCircle },
}

const PRIORITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500/10 text-red-600 dark:text-red-400 ring-red-500/20',
    high: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 ring-orange-500/20',
    medium: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 ring-amber-500/20',
    low: 'bg-green-500/10 text-green-600 dark:text-green-400 ring-green-500/20',
}

const STATUS_LABELS: Record<string, string> = {
    pending: 'Pending',
    approved: 'Approved',
    under_review: 'Under Review',
    availability_submitted: 'Availability Submitted',
    assigned: 'Assigned',
    in_progress: 'In Progress',
    delivered: 'Delivered',
    completed: 'Completed',
    closed: 'Closed',
    rejected: 'Rejected',
}

function StatusBadge({ status }: { status: string }) {
    const s = STATUS_COLORS[status] || STATUS_COLORS.pending
    const Icon = s.icon
    return (
        <span className={cn('inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold ring-1 ring-inset', s.bg, s.text, s.ring)}>
            <Icon className="w-3 h-3" />
            {STATUS_LABELS[status] || status.replace(/_/g, ' ')}
        </span>
    )
}

function PriorityBadge({ priority }: { priority: string }) {
    return (
        <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ring-1 ring-inset', PRIORITY_COLORS[priority] || PRIORITY_COLORS.medium)}>
            {priority}
        </span>
    )
}

const AUDIT_COLORS: Record<string, string> = {
    status_changed_to_approved: 'bg-green-500',
    status_changed_to_rejected: 'bg-red-500',
    status_changed_to_availability_submitted: 'bg-cyan-500',
    status_changed_to_under_review: 'bg-indigo-500',
    status_changed_to_assigned: 'bg-blue-500',
    status_changed_to_in_progress: 'bg-purple-500',
    status_changed_to_delivered: 'bg-teal-500',
    status_changed_to_completed: 'bg-emerald-500',
    status_changed_to_closed: 'bg-slate-500',
    status_changed_to_pending: 'bg-amber-500',
}

function AuditTrailTimeline({ requestId }: { requestId: string }) {
    const { data, isLoading } = useQuery({
        queryKey: ['audit-trail', requestId],
        queryFn: () => api.getRequestAuditTrail(requestId),
        enabled: !!requestId,
    })
    const trail = data?.audit_trail || []
    if (isLoading) return <div className="py-4 text-center"><Loader2 className="w-4 h-4 animate-spin mx-auto text-slate-400" /></div>
    if (trail.length === 0) return null
    return (
        <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Activity Timeline</p>
            <div className="relative pl-6 space-y-4">
                <div className="absolute left-2.5 top-1 bottom-1 w-0.5 bg-slate-200 dark:bg-white/10" />
                {trail.map((entry: any, i: number) => {
                    const dotColor = AUDIT_COLORS[entry.action] || 'bg-slate-400'
                    const label = entry.action?.replace('status_changed_to_', '').replace(/_/g, ' ') || 'Event'
                    return (
                        <div key={entry.id || i} className="relative">
                            <div className={cn('absolute -left-3.5 top-1 w-3 h-3 rounded-full border-2 border-white dark:border-slate-950', dotColor)} />
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-semibold text-slate-900 dark:text-white capitalize">{label}</span>
                                    {entry.old_status && entry.new_status && (
                                        <span className="text-[10px] text-slate-400">{entry.old_status} → {entry.new_status}</span>
                                    )}
                                </div>
                                {entry.details && <p className="text-[11px] text-slate-500 mt-0.5">{entry.details}</p>}
                                <p className="text-[10px] text-slate-400 mt-0.5">
                                    {entry.actor_role !== 'system' ? `By ${entry.actor_role}` : 'System'} • {new Date(entry.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                </p>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function NgoSubmissionsPanel({ requestId, status, onAssign }: { requestId: string; status: string; onAssign: (ngoId: string, role: string) => void }) {
    const { data, isLoading } = useQuery({
        queryKey: ['ngo-submissions', requestId],
        queryFn: () => api.getRequestNgoSubmissions(requestId),
        enabled: !!requestId,
    })
    const submissions = data?.submissions || []
    if (isLoading) return null
    if (submissions.length === 0) return null

    const ROLE_BADGE: Record<string, string> = {
        ngo: 'bg-cyan-100 dark:bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 ring-cyan-500/20',
        donor: 'bg-pink-100 dark:bg-pink-500/10 text-pink-700 dark:text-pink-400 ring-pink-500/20',
    }

    return (
        <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Submissions ({submissions.length})
            </p>
            <div className="space-y-2">
                {submissions.map((s: any) => (
                    <div key={s.id} className={cn(
                        'rounded-xl border p-4 space-y-2',
                        s.role === 'donor'
                            ? 'border-pink-200 dark:border-pink-500/20 bg-pink-50 dark:bg-pink-500/5'
                            : 'border-cyan-200 dark:border-cyan-500/20 bg-cyan-50 dark:bg-cyan-500/5'
                    )}>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <div>
                                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{s.ngo_name}</p>
                                    {s.ngo_email && <p className="text-[11px] text-slate-500">{s.ngo_email}</p>}
                                </div>
                                <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset uppercase',
                                    ROLE_BADGE[s.role] || ROLE_BADGE.ngo)}>
                                    {s.role || 'ngo'}
                                </span>
                            </div>
                            {(status === 'availability_submitted' || status === 'under_review') && (
                                <button
                                    onClick={() => onAssign(s.ngo_id, s.role || 'ngo')}
                                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:opacity-90 shadow-sm"
                                >
                                    Assign
                                </button>
                            )}
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                                {(s.metadata?.available_quantity || (s.metadata?.resource_items?.length > 0)) && (
                                <div>
                                    <span className="text-slate-400">Quantity: </span>
                                    <span className="font-semibold text-slate-700 dark:text-slate-300">
                                        {s.metadata.available_quantity ??
                                            s.metadata.resource_items?.reduce((sum: number, ri: any) => sum + (ri.quantity || 0), 0)}
                                    </span>
                                </div>
                            )}
                            {s.metadata?.estimated_delivery_time && (
                                <div>
                                    <span className="text-slate-400">ETA: </span>
                                    <span className="font-semibold text-slate-700 dark:text-slate-300">{new Date(s.metadata.estimated_delivery_time).toLocaleString()}</span>
                                </div>
                            )}
                            {s.metadata?.vehicle_type && (
                                <div>
                                    <span className="text-slate-400">Vehicle: </span>
                                    <span className="text-slate-700 dark:text-slate-300">{s.metadata.vehicle_type}</span>
                                </div>
                            )}
                            {s.metadata?.distance_km !== null && s.metadata?.distance_km !== undefined && (
                                <div>
                                    <span className="text-slate-400">Distance: </span>
                                    <span className="text-slate-700 dark:text-slate-300">{s.metadata.distance_km} km</span>
                                </div>
                            )}
                        </div>
                        {s.metadata?.notes && (
                            <p className="text-xs text-slate-500 italic">{s.metadata.notes}</p>
                        )}
                        <p className="text-[10px] text-slate-400">Submitted: {new Date(s.submitted_at).toLocaleString()}</p>
                    </div>
                ))}
            </div>
        </div>
    )
}

export default function AdminRequestsPage() {
    const qc = useQueryClient()
    const [filters, setFilters] = useState({
        status: '',
        priority: '',
        resource_type: '',
        search: '',
        page: 1,
        page_size: 15,
    })
    const [selectedRequest, setSelectedRequest] = useState<any>(null)
    const [actionModal, setActionModal] = useState<{ type: 'approve' | 'reject'; requestId: string } | null>(null)
    const [rejectionReason, setRejectionReason] = useState('')
    const [adminNote, setAdminNote] = useState('')

    // Fetch requests
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['admin-requests', filters],
        queryFn: () => api.getAdminRequests({
            ...filters,
            status: filters.status || undefined,
            priority: filters.priority || undefined,
            resource_type: filters.resource_type || undefined,
            search: filters.search || undefined,
        }),
        refetchInterval: 30000,
    })

    // Action mutation
    const actionMutation = useMutation({
        mutationFn: ({ requestId, data }: { requestId: string; data: any }) =>
            api.adminRequestAction(requestId, data),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['admin-requests'] })
            setActionModal(null)
            setRejectionReason('')
            setAdminNote('')
            setSelectedRequest(null)
        },
    })

    // Status mutation
    const statusMutation = useMutation({
        mutationFn: ({ requestId, data }: { requestId: string; data: any }) =>
            api.adminUpdateRequestStatus(requestId, data),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['admin-requests'] })
        },
    })

    const requests = data?.requests || []
    const total = data?.total || 0
    const statusCounts = data?.status_counts || {}
    const totalPages = Math.ceil(total / filters.page_size)

    const handleAction = (type: 'approve' | 'reject') => {
        if (!actionModal) return
        actionMutation.mutate({
            requestId: actionModal.requestId,
            data: {
                action: type,
                rejection_reason: type === 'reject' ? rejectionReason : undefined,
                admin_note: adminNote || undefined,
            }
        })
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Inbox className="w-6 h-6 text-blue-500" />
                        Request Management
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Review, approve, or reject victim resource requests across all users
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <RefreshCw className="w-4 h-4" />
                    Refresh
                </button>
            </div>

            {/* Status Overview Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {['pending', 'approved', 'under_review', 'availability_submitted', 'assigned', 'in_progress', 'delivered', 'completed', 'closed', 'rejected'].map((s) => {
                    const sc = STATUS_COLORS[s]
                    const Icon = sc?.icon || Clock
                    const count = statusCounts[s] || 0
                    const isActive = filters.status === s
                    return (
                        <button
                            key={s}
                            onClick={() => setFilters(f => ({ ...f, status: f.status === s ? '' : s, page: 1 }))}
                            className={cn(
                                'rounded-xl border p-3 text-left transition-all hover:shadow-md',
                                isActive
                                    ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-500/10 shadow-sm'
                                    : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]'
                            )}
                        >
                            <div className="flex items-center gap-2 mb-1">
                                <Icon className={cn('w-4 h-4', sc?.text || '')} />
                                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{STATUS_LABELS[s] || s.replace(/_/g, ' ')}</span>
                            </div>
                            <p className="text-xl font-bold text-slate-900 dark:text-white">{count}</p>
                        </button>
                    )
                })}
            </div>

            {/* Filters */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="relative flex-1 min-w-[200px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            placeholder="Search by description, ID..."
                            value={filters.search}
                            onChange={(e) => setFilters(f => ({ ...f, search: e.target.value, page: 1 }))}
                            className="w-full pl-9 pr-3 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                        />
                    </div>
                    <select
                        value={filters.priority}
                        onChange={(e) => setFilters(f => ({ ...f, priority: e.target.value, page: 1 }))}
                        className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none min-w-[130px]"
                    >
                        <option value="">All Priority</option>
                        <option value="critical">Critical</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                    </select>
                    <select
                        value={filters.resource_type}
                        onChange={(e) => setFilters(f => ({ ...f, resource_type: e.target.value, page: 1 }))}
                        className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none min-w-[150px]"
                    >
                        <option value="">All Types</option>
                        <option value="Food">Food</option>
                        <option value="Water">Water</option>
                        <option value="Medical">Medical</option>
                        <option value="Shelter">Shelter</option>
                        <option value="Clothing">Clothing</option>
                        <option value="Financial Aid">Financial Aid</option>
                        <option value="Evacuation">Evacuation</option>
                    </select>
                    {(filters.status || filters.priority || filters.resource_type || filters.search) && (
                        <button
                            onClick={() => setFilters({ status: '', priority: '', resource_type: '', search: '', page: 1, page_size: 15 })}
                            className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 text-sm text-slate-500 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-1.5 transition-colors"
                        >
                            <X className="w-3.5 h-3.5" />
                            Clear
                        </button>
                    )}
                </div>
            </div>

            {/* Requests Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                    </div>
                ) : requests.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20">
                        <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mb-3" />
                        <p className="text-sm font-medium text-slate-900 dark:text-white">No requests found</p>
                        <p className="text-xs text-slate-500 mt-1">Try adjusting your filters</p>
                    </div>
                ) : (
                    <>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-slate-100 dark:border-white/5 bg-slate-50/80 dark:bg-white/[0.02]">
                                        <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Victim</th>
                                        <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Type</th>
                                        <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Handled By</th>
                                        <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Priority</th>
                                        <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                                        <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Qty</th>
                                        <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Created</th>
                                        <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                                    {requests.map((req: any) => (
                                        <tr key={req.id} className="hover:bg-slate-50/60 dark:hover:bg-white/[0.02] transition-colors group">
                                            <td className="px-4 py-3">
                                                <div>
                                                    <p className="font-medium text-slate-900 dark:text-white text-sm">{req.victim_name || 'Unknown'}</p>
                                                    <p className="text-[11px] text-slate-400 truncate max-w-[180px]">{req.description || 'No description'}</p>
                                                </div>
                                            </td>
                                            <td className="px-3 py-3">
                                                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                                                    {req.resource_type}
                                                </span>
                                            </td>
                                            <td className="px-3 py-3">
                                                {req.assigned_users && req.assigned_users.length > 0 ? (
                                                    <div className="flex flex-col gap-1">
                                                        {req.assigned_users.map((u: any, idx: number) => (
                                                            <div key={u.id || idx} className="flex flex-col">
                                                                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{u.full_name || 'Organization'}</span>
                                                                <span className="text-[10px] text-slate-400 uppercase tracking-tighter">{u.role}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : req.assigned_user ? (
                                                    <div className="flex flex-col">
                                                        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{req.assigned_user.full_name || 'Organization'}</span>
                                                        <span className="text-[10px] text-slate-400 uppercase tracking-tighter">{req.assigned_role}</span>
                                                    </div>
                                                ) : (
                                                    <span className="text-xs text-slate-400 italic">Unassigned</span>
                                                )}
                                            </td>
                                            <td className="px-3 py-3">
                                                <div className="flex items-center gap-1.5">
                                                    <PriorityBadge priority={req.priority} />
                                                    {req.is_verified ? (
                                                        <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ring-1 ring-inset ring-emerald-200 dark:ring-emerald-500/20" title="Field verified">✓ Verified</span>
                                                    ) : (
                                                        <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-slate-50 dark:bg-slate-500/10 text-slate-400 dark:text-slate-500 ring-1 ring-inset ring-slate-200 dark:ring-slate-500/20" title="Pending verification">— Pending</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-3 py-3"><StatusBadge status={req.status} /></td>
                                            <td className="px-3 py-3 text-slate-700 dark:text-slate-300 font-mono text-xs text-right">{req.quantity}</td>
                                            <td className="px-3 py-3 text-xs text-slate-500">
                                                {req.created_at ? new Date(req.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button
                                                        onClick={() => setSelectedRequest(req)}
                                                        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 text-slate-500 transition-colors"
                                                        title="View Details"
                                                    >
                                                        <Eye className="w-4 h-4" />
                                                    </button>
                                                    {req.status === 'pending' && (
                                                        <>
                                                            <button
                                                                onClick={() => setActionModal({ type: 'approve', requestId: req.id })}
                                                                className="p-1.5 rounded-lg hover:bg-green-100 dark:hover:bg-green-500/10 text-green-600 transition-colors"
                                                                title="Approve"
                                                            >
                                                                <ThumbsUp className="w-4 h-4" />
                                                            </button>
                                                            <button
                                                                onClick={() => setActionModal({ type: 'reject', requestId: req.id })}
                                                                className="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-500/10 text-red-600 transition-colors"
                                                                title="Reject"
                                                            >
                                                                <ThumbsDown className="w-4 h-4" />
                                                            </button>
                                                        </>
                                                    )}
                                                    {req.status === 'availability_submitted' && (
                                                        <>
                                                            <button
                                                                onClick={() => setActionModal({ type: 'approve', requestId: req.id })}
                                                                className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-cyan-100 dark:bg-cyan-500/10 text-cyan-600 hover:opacity-80 transition-opacity"
                                                                title="Assign to NGO"
                                                            >
                                                                Assign NGO
                                                            </button>
                                                            <button
                                                                onClick={() => statusMutation.mutate({ requestId: req.id, data: { status: 'approved' } })}
                                                                className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-amber-100 dark:bg-amber-500/10 text-amber-600 hover:opacity-80 transition-opacity"
                                                                title="Revert to approved"
                                                            >
                                                                Revert
                                                            </button>
                                                        </>
                                                    )}
                                                    {req.status === 'approved' && (
                                                        <button
                                                            onClick={() => statusMutation.mutate({ requestId: req.id, data: { status: 'in_progress' } })}
                                                            className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-purple-100 dark:bg-purple-500/10 text-purple-600 hover:opacity-80 transition-opacity"
                                                        >
                                                            Start
                                                        </button>
                                                    )}
                                                    {(req.status === 'in_progress' || req.status === 'assigned') && (
                                                        <button
                                                            onClick={() => statusMutation.mutate({ requestId: req.id, data: { status: 'completed' } })}
                                                            className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 hover:opacity-80 transition-opacity"
                                                        >
                                                            Complete
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination */}
                        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 dark:border-white/5">
                            <p className="text-xs text-slate-500">
                                Showing {Math.min((filters.page - 1) * filters.page_size + 1, total)}–{Math.min(filters.page * filters.page_size, total)} of {total}
                            </p>
                            <div className="flex items-center gap-1">
                                <button
                                    onClick={() => setFilters(f => ({ ...f, page: Math.max(1, f.page - 1) }))}
                                    disabled={filters.page <= 1}
                                    className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                                >
                                    <ChevronLeft className="w-4 h-4" />
                                </button>
                                <span className="text-xs font-medium text-slate-600 dark:text-slate-400 px-2">
                                    Page {filters.page} of {totalPages || 1}
                                </span>
                                <button
                                    onClick={() => setFilters(f => ({ ...f, page: Math.min(totalPages, f.page + 1) }))}
                                    disabled={filters.page >= totalPages}
                                    className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 disabled:opacity-30 transition-colors"
                                >
                                    <ChevronRight className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Detail Drawer */}
            {selectedRequest && (
                <div className="fixed inset-0 z-50 flex justify-end">
                    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setSelectedRequest(null)} />
                    <div className="relative w-full max-w-lg bg-white dark:bg-slate-950 border-l border-slate-200 dark:border-white/10 overflow-y-auto animate-in slide-in-from-right">
                        <div className="sticky top-0 z-10 bg-white/95 dark:bg-slate-950/95 backdrop-blur-xl border-b border-slate-200 dark:border-white/5 px-6 py-4">
                            <div className="flex items-center justify-between">
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Request Details</h2>
                                <button onClick={() => setSelectedRequest(null)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                    <X className="w-5 h-5 text-slate-500" />
                                </button>
                            </div>
                        </div>

                        <div className="p-6 space-y-5">
                            {/* Status + Priority */}
                            <div className="flex items-center gap-3">
                                <StatusBadge status={selectedRequest.status} />
                                <PriorityBadge priority={selectedRequest.priority} />
                            </div>

                            {/* Victim Info */}
                            <div className="rounded-xl border border-slate-200 dark:border-white/10 p-4 space-y-2">
                                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Victim</p>
                                <p className="text-sm font-medium text-slate-900 dark:text-white">{selectedRequest.victim_name || 'Unknown'}</p>
                                {selectedRequest.victim_email && <p className="text-xs text-slate-500">{selectedRequest.victim_email}</p>}
                            </div>

                            {/* Resource Info */}
                            <div className="grid grid-cols-2 gap-3">
                                <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3">
                                    <p className="text-[10px] font-semibold text-slate-400 uppercase mb-1">Type</p>
                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{selectedRequest.resource_type}</p>
                                </div>
                                <div className="rounded-xl border border-slate-200 dark:border-white/10 p-3">
                                    <p className="text-[10px] font-semibold text-slate-400 uppercase mb-1">Quantity</p>
                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{selectedRequest.quantity}</p>
                                </div>
                            </div>

                            {/* Description */}
                            {selectedRequest.description && (
                                <div>
                                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Description</p>
                                    <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-white/[0.03] rounded-xl p-4 border border-slate-100 dark:border-white/5">
                                        {selectedRequest.description}
                                    </p>
                                </div>
                            )}

                            {/* NLP Classification */}
                            {selectedRequest.nlp_classification && Object.keys(selectedRequest.nlp_classification).length > 0 && (
                                <div>
                                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">AI Classification</p>
                                    <div className="bg-purple-50 dark:bg-purple-500/5 border border-purple-200 dark:border-purple-500/20 rounded-xl p-4 text-sm space-y-1">
                                        <p className="text-purple-700 dark:text-purple-300">
                                            <strong>Types:</strong> {(selectedRequest.nlp_classification.resource_types || []).join(', ')}
                                        </p>
                                        <p className="text-purple-700 dark:text-purple-300">
                                            <strong>Confidence:</strong> {((selectedRequest.nlp_classification.confidence || 0) * 100).toFixed(0)}%
                                        </p>
                                        <p className="text-purple-700 dark:text-purple-300">
                                            <strong>Priority:</strong> {selectedRequest.nlp_classification.recommended_priority}
                                            {selectedRequest.nlp_classification.priority_was_escalated && ' (escalated ⚠️)'}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {/* Location */}
                            {(selectedRequest.latitude || selectedRequest.address_text) && (
                                <div>
                                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Location</p>
                                    <p className="text-sm text-slate-700 dark:text-slate-300">
                                        {selectedRequest.address_text || `${selectedRequest.latitude}, ${selectedRequest.longitude}`}
                                    </p>
                                </div>
                            )}

                            {/* Rejection reason */}
                            {selectedRequest.rejection_reason && (
                                <div className="bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20 rounded-xl p-4">
                                    <p className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase mb-1">Rejection Reason</p>
                                    <p className="text-sm text-red-700 dark:text-red-300">{selectedRequest.rejection_reason}</p>
                                </div>
                            )}

                            {/* NGO Availability Submissions */}
                            <NgoSubmissionsPanel requestId={selectedRequest.id} status={selectedRequest.status} onAssign={(ngoId: string, role: string) => {
                                actionMutation.mutate({
                                    requestId: selectedRequest.id,
                                    data: { action: 'approve', assigned_to: ngoId, assigned_role: role }
                                })
                            }} />

                            {/* Audit Trail / Timeline */}
                            <AuditTrailTimeline requestId={selectedRequest.id} />

                            {/* Timestamps */}
                            <div className="text-xs text-slate-400 space-y-1 pt-2 border-t border-slate-100 dark:border-white/5">
                                <p>Created: {selectedRequest.created_at ? new Date(selectedRequest.created_at).toLocaleString() : '—'}</p>
                                <p>Updated: {selectedRequest.updated_at ? new Date(selectedRequest.updated_at).toLocaleString() : '—'}</p>
                                <p className="font-mono text-[10px] text-slate-300 dark:text-slate-600">ID: {selectedRequest.id}</p>
                            </div>

                            {/* Action Buttons */}
                            {selectedRequest.status === 'pending' && (
                                <div className="flex gap-3 pt-2">
                                    <button
                                        onClick={() => setActionModal({ type: 'approve', requestId: selectedRequest.id })}
                                        className="flex-1 flex items-center justify-center gap-2 h-11 rounded-xl bg-gradient-to-r from-green-500 to-emerald-600 text-white font-medium text-sm hover:opacity-90 shadow-lg shadow-green-600/20"
                                    >
                                        <CheckCircle2 className="w-4 h-4" />
                                        Approve
                                    </button>
                                    <button
                                        onClick={() => setActionModal({ type: 'reject', requestId: selectedRequest.id })}
                                        className="flex-1 flex items-center justify-center gap-2 h-11 rounded-xl bg-gradient-to-r from-red-500 to-rose-600 text-white font-medium text-sm hover:opacity-90 shadow-lg shadow-red-600/20"
                                    >
                                        <XCircle className="w-4 h-4" />
                                        Reject
                                    </button>
                                </div>
                            )}
                            {selectedRequest.status === 'availability_submitted' && (
                                <div className="flex gap-3 pt-2">
                                    <button
                                        onClick={() => setActionModal({ type: 'approve', requestId: selectedRequest.id })}
                                        className="flex-1 flex items-center justify-center gap-2 h-11 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-medium text-sm hover:opacity-90 shadow-lg shadow-cyan-600/20"
                                    >
                                        <CheckCircle2 className="w-4 h-4" />
                                        Assign to NGO
                                    </button>
                                    <button
                                        onClick={() => statusMutation.mutate({ requestId: selectedRequest.id, data: { status: 'approved' } })}
                                        className="flex-1 flex items-center justify-center gap-2 h-11 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 font-medium text-sm hover:bg-slate-50 dark:hover:bg-white/5"
                                    >
                                        <X className="w-4 h-4" />
                                        Revert to Approved
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Approve/Reject Modal */}
            {actionModal && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center">
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setActionModal(null)} />
                    <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10 p-6 space-y-4 animate-in zoom-in-95">
                        <div className="flex items-center gap-3">
                            {actionModal.type === 'approve' ? (
                                <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                                </div>
                            ) : (
                                <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                                    <XCircle className="w-5 h-5 text-red-600" />
                                </div>
                            )}
                            <div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white capitalize">{actionModal.type} Request</h3>
                                <p className="text-xs text-slate-500">This action will notify the victim</p>
                            </div>
                        </div>

                        {actionModal.type === 'reject' && (
                            <div>
                                <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                                    Rejection Reason <span className="text-red-500">*</span>
                                </label>
                                <textarea
                                    value={rejectionReason}
                                    onChange={(e) => setRejectionReason(e.target.value)}
                                    placeholder="Explain why this request is being rejected..."
                                    rows={3}
                                    className="w-full mt-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-red-500 focus:outline-none resize-none"
                                />
                            </div>
                        )}

                        <div>
                            <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Admin Note (optional)</label>
                            <textarea
                                value={adminNote}
                                onChange={(e) => setAdminNote(e.target.value)}
                                placeholder="Add an internal note..."
                                rows={2}
                                className="w-full mt-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none"
                            />
                        </div>

                        <div className="flex gap-3 pt-2">
                            <button
                                onClick={() => setActionModal(null)}
                                className="flex-1 h-10 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => handleAction(actionModal.type)}
                                disabled={actionMutation.isPending || (actionModal.type === 'reject' && !rejectionReason.trim())}
                                className={cn(
                                    'flex-1 h-10 rounded-xl text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2',
                                    actionModal.type === 'approve'
                                        ? 'bg-gradient-to-r from-green-500 to-emerald-600 hover:opacity-90'
                                        : 'bg-gradient-to-r from-red-500 to-rose-600 hover:opacity-90'
                                )}
                            >
                                {actionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                Confirm {actionModal.type === 'approve' ? 'Approval' : 'Rejection'}
                            </button>
                        </div>

                        {actionMutation.isError && (
                            <p className="text-xs text-red-500 text-center">Error: {(actionMutation.error as Error).message}</p>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
