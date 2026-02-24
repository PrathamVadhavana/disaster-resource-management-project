'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { createClient } from '@/lib/supabase/client'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
    Loader2, Clock, CheckCircle2, XCircle, Package, MapPin,
    ArrowRight, AlertTriangle, FileText, MessageSquare,
    ChevronDown, ChevronUp, Timer, Truck
} from 'lucide-react'
import { NotificationBell } from '@/components/shared/NotificationBell'
import { getResourceRequests } from '@/lib/api/victim'

const STEPS = [
    { key: 'pending', label: 'Submitted', icon: FileText, color: 'text-slate-500' },
    { key: 'approved', label: 'Approved', icon: CheckCircle2, color: 'text-green-500' },
    { key: 'assigned', label: 'Assigned', icon: Package, color: 'text-blue-500' },
    { key: 'in_progress', label: 'In Progress', icon: Truck, color: 'text-purple-500' },
    { key: 'completed', label: 'Completed', icon: CheckCircle2, color: 'text-emerald-500' },
]

const STATUS_INDEX: Record<string, number> = {
    pending: 0, approved: 1, assigned: 2, in_progress: 3, completed: 4, rejected: -1,
}

function StatusTracker({ status }: { status: string }) {
    const currentIndex = STATUS_INDEX[status] ?? 0
    const isRejected = status === 'rejected'

    if (isRejected) {
        return (
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20">
                <XCircle className="w-5 h-5 text-red-500" />
                <span className="text-sm font-semibold text-red-600 dark:text-red-400">Request Rejected</span>
            </div>
        )
    }

    return (
        <div className="flex items-center gap-1 overflow-x-auto py-2">
            {STEPS.map((step, i) => {
                const done = i <= currentIndex
                const current = i === currentIndex
                const Icon = step.icon
                return (
                    <div key={step.key} className="flex items-center">
                        <div className={cn(
                            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all',
                            done ? current ? 'bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 ring-1 ring-purple-300 dark:ring-purple-500/30' : 'bg-green-50 dark:bg-green-500/5 text-green-600 dark:text-green-400' : 'bg-slate-50 dark:bg-white/5 text-slate-400'
                        )}>
                            <Icon className={cn('w-3.5 h-3.5', done ? current ? 'text-purple-500' : 'text-green-500' : 'text-slate-300')} />
                            <span className="whitespace-nowrap">{step.label}</span>
                        </div>
                        {i < STEPS.length - 1 && (
                            <div className={cn('w-6 h-0.5 mx-0.5', i < currentIndex ? 'bg-green-400' : 'bg-slate-200 dark:bg-slate-700')} />
                        )}
                    </div>
                )
            })}
        </div>
    )
}

function TimeCountdown({ targetDate }: { targetDate: string }) {
    const [remaining, setRemaining] = useState('')

    useEffect(() => {
        const update = () => {
            const diff = new Date(targetDate).getTime() - Date.now()
            if (diff <= 0) { setRemaining('Overdue'); return }
            const hours = Math.floor(diff / 3600000)
            const mins = Math.floor((diff % 3600000) / 60000)
            setRemaining(hours > 24 ? `${Math.floor(hours / 24)}d ${hours % 24}h` : `${hours}h ${mins}m`)
        }
        update()
        const timer = setInterval(update, 60000)
        return () => clearInterval(timer)
    }, [targetDate])

    return (
        <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400 font-medium">
            <Timer className="w-3 h-3" /> ETA: {remaining}
        </span>
    )
}

export default function VictimRequestStatusPage() {
    const { profile } = useAuth()
    const [expanded, setExpanded] = useState<string | null>(null)

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['victim-requests-status'],
        queryFn: async () => {
            return getResourceRequests({ page_size: 50 })
        },
        refetchInterval: 15000,
    })

    // Realtime subscription for instant updates
    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('victim-request-updates')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'resource_requests' }, () => {
                refetch()
            })
            .subscribe()
        return () => { supabase.removeChannel(channel) }
    }, [refetch])

    const requests = data?.requests || (Array.isArray(data) ? data : [])

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header with notification bell */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Requests</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Track the status of your resource requests in real-time
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <NotificationBell />
                    <Link href="/victim/requests/new"
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 transition-colors shadow-md">
                        + New Request
                    </Link>
                </div>
            </div>

            {/* Request Cards */}
            {requests.length === 0 ? (
                <div className="text-center py-20">
                    <Package className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-lg font-semibold text-slate-700 dark:text-white">No requests yet</p>
                    <p className="text-sm text-slate-500 mt-1">Create your first resource request to get started</p>
                    <Link href="/victim/requests/new"
                        className="inline-flex items-center gap-2 px-5 py-2.5 mt-4 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700">
                        <FileText className="w-4 h-4" /> Create Request
                    </Link>
                </div>
            ) : (
                <div className="space-y-4">
                    {requests.map((req: any) => {
                        const isExpanded = expanded === req.id
                        const isRejected = req.status === 'rejected'
                        const isCompleted = req.status === 'completed'

                        return (
                            <div key={req.id} className={cn(
                                'rounded-2xl border bg-white dark:bg-white/[0.02] overflow-hidden transition-all',
                                isRejected ? 'border-red-200 dark:border-red-500/20' :
                                    isCompleted ? 'border-emerald-200 dark:border-emerald-500/20' :
                                        'border-slate-200 dark:border-white/10'
                            )}>
                                {/* Main row */}
                                <div className="p-5">
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                                    {req.resource_type || req.title || 'Resource Request'}
                                                </h3>
                                                <span className={cn(
                                                    'text-[10px] px-2 py-0.5 rounded-full font-semibold capitalize',
                                                    req.priority === 'critical' ? 'bg-red-100 dark:bg-red-500/10 text-red-600' :
                                                        req.priority === 'high' ? 'bg-orange-100 dark:bg-orange-500/10 text-orange-600' :
                                                            'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                                                )}>
                                                    {req.priority}
                                                </span>
                                            </div>
                                            {req.description && (
                                                <p className="text-xs text-slate-500 mt-1 line-clamp-1">{req.description}</p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {req.estimated_delivery && !isCompleted && !isRejected && (
                                                <TimeCountdown targetDate={req.estimated_delivery} />
                                            )}
                                            <button onClick={() => setExpanded(isExpanded ? null : req.id)}
                                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                                {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                                            </button>
                                        </div>
                                    </div>

                                    {/* Status Tracker */}
                                    <div className="mt-3">
                                        <StatusTracker status={req.status} />
                                    </div>
                                </div>

                                {/* Expanded Details */}
                                {isExpanded && (
                                    <div className="px-5 pb-5 pt-0 space-y-4 border-t border-slate-100 dark:border-white/5">
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4">
                                            <div>
                                                <p className="text-[10px] text-slate-400 uppercase tracking-wider">Quantity</p>
                                                <p className="text-sm font-semibold text-slate-900 dark:text-white">{req.quantity || 1}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] text-slate-400 uppercase tracking-wider">Created</p>
                                                <p className="text-sm font-semibold text-slate-900 dark:text-white">{new Date(req.created_at).toLocaleDateString()}</p>
                                            </div>
                                            {req.address_text && (
                                                <div>
                                                    <p className="text-[10px] text-slate-400 uppercase tracking-wider">Location</p>
                                                    <p className="text-sm text-slate-700 dark:text-slate-300 flex items-center gap-1"><MapPin className="w-3 h-3" />{req.address_text}</p>
                                                </div>
                                            )}
                                            {req.estimated_delivery && (
                                                <div>
                                                    <p className="text-[10px] text-slate-400 uppercase tracking-wider">Est. Delivery</p>
                                                    <p className="text-sm font-semibold text-amber-600">{new Date(req.estimated_delivery).toLocaleDateString()}</p>
                                                </div>
                                            )}
                                        </div>

                                        {/* Assigned Organization Info */}
                                        {req.assigned_user && (
                                            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5">
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                                            <Package className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                                        </div>
                                                        <div>
                                                            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">Handled By</p>
                                                            <p className="text-sm font-bold text-slate-900 dark:text-white">
                                                                {req.assigned_user.full_name || 'Organization'}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    {req.assigned_user.metadata?.verification_status === 'verified' && (
                                                        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20">
                                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                                                            <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-tight">Verified Entity</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {/* Admin feedback */}
                                        {req.admin_note && (
                                            <div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-500/5 border border-blue-200 dark:border-blue-500/20">
                                                <p className="text-[10px] text-blue-600 dark:text-blue-400 font-semibold uppercase tracking-wider mb-1">Admin Note</p>
                                                <p className="text-sm text-blue-700 dark:text-blue-300">{req.admin_note}</p>
                                            </div>
                                        )}

                                        {/* Rejection reason */}
                                        {isRejected && req.rejection_reason && (
                                            <div className="p-3 rounded-xl bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20">
                                                <p className="text-[10px] text-red-600 dark:text-red-400 font-semibold uppercase tracking-wider mb-1">Rejection Reason</p>
                                                <p className="text-sm text-red-700 dark:text-red-300">{req.rejection_reason}</p>
                                                <Link href="/victim/requests/new"
                                                    className="inline-flex items-center gap-1 mt-2 text-xs font-medium text-red-600 hover:underline">
                                                    Resubmit with changes <ArrowRight className="w-3 h-3" />
                                                </Link>
                                            </div>
                                        )}

                                        {/* Items list */}
                                        {req.items && req.items.length > 0 && (
                                            <div>
                                                <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Requested Items</p>
                                                <div className="space-y-1">
                                                    {req.items.map((item: any, i: number) => (
                                                        <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-slate-50 dark:bg-white/5">
                                                            <span className="text-xs text-slate-700 dark:text-slate-300">{item.name || item.type}</span>
                                                            <span className="text-xs font-semibold text-slate-900 dark:text-white">×{item.quantity || 1}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
