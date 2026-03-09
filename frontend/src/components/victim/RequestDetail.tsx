'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getResourceRequest, deleteResourceRequest, type ResourceRequest } from '@/lib/api/victim'
import { StatusBadge, PriorityBadge, ResourceTypeIcon } from './StatusBadge'
import { UrgencyTags, ConfidenceBadge } from './UrgencyTags'
import { cn } from '@/lib/utils'
import { ArrowLeft, Edit3, Trash2, Loader2, MapPin, Calendar, User, Package, Brain, Activity, Users } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { format } from 'date-fns'
import { useState } from 'react'
import { api } from '@/lib/api'
import { DeliveryConfirmation } from './DeliveryConfirmation'

const statusSteps = ['pending', 'approved', 'under_review', 'availability_submitted', 'assigned', 'in_progress', 'delivered', 'completed']

export function RequestDetail({ requestId }: { requestId: string }) {
    const router = useRouter()
    const queryClient = useQueryClient()
    const [showDelete, setShowDelete] = useState(false)

    const { data: request, isLoading } = useQuery<ResourceRequest>({
        queryKey: ['victim-request', requestId],
        queryFn: () => getResourceRequest(requestId),
    })

    const { data: timelineData, isLoading: isLoadingTimeline } = useQuery({
        queryKey: ['victim-timeline', requestId],
        queryFn: () => api.getVictimRequestTimeline(requestId),
    })

    const { data: fulfillmentData } = useQuery({
        queryKey: ['victim-fulfillment', requestId],
        queryFn: () => api.getRequestFulfillment(requestId),
        enabled: !!request && ['approved', 'under_review', 'assigned', 'in_progress', 'delivered', 'completed'].includes(request.status),
    })

    const { data: poolData } = useQuery({
        queryKey: ['victim-resource-pool', requestId],
        queryFn: () => api.getResourcePool(requestId),
        enabled: !!request && ['approved', 'under_review', 'assigned', 'in_progress', 'delivered', 'completed'].includes(request.status),
    })

    const deleteMut = useMutation({
        mutationFn: () => deleteResourceRequest(requestId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['victim-requests'] })
            queryClient.invalidateQueries({ queryKey: ['victim-stats'] })
            router.push('/victim/requests')
        },
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    if (!request) {
        return <div className="text-center text-slate-400 py-16">Request not found</div>
    }

    const currentStep = statusSteps.indexOf(request.status)
    const isRejected = request.status === 'rejected'
    const canEdit = request.status === 'pending'
    const canDelete = ['pending', 'approved', 'assigned', 'in_progress', 'under_review', 'availability_submitted'].includes(request.status)

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <Link
                        href="/victim/requests"
                        className="p-2 rounded-xl bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:bg-slate-50 dark:hover:bg-white/10 transition-colors"
                    >
                        <ArrowLeft className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                    </Link>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Request Detail</h1>
                        <p className="text-xs text-slate-400 mt-0.5 font-mono">{request.id.slice(0, 8)}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {canEdit && (
                        <Link
                            href={`/victim/requests/${request.id}/edit`}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/10 transition-colors"
                        >
                            <Edit3 className="w-4 h-4" />
                            Edit
                        </Link>
                    )}
                    {canDelete && (
                        <button
                            onClick={() => setShowDelete(true)}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                        >
                            <Trash2 className="w-4 h-4" />
                            {request.status === 'pending' ? 'Delete' : 'Cancel'}
                        </button>
                    )}
                </div>
            </div>

            {/* Status + Priority */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <div className="flex items-center gap-3 mb-5">
                    <StatusBadge status={request.status} />
                    <PriorityBadge priority={request.priority} />
                </div>

                {/* Status timeline */}
                {!isRejected && (
                    <div className="flex items-center gap-0">
                        {statusSteps.map((step, i) => {
                            const done = i <= currentStep
                            const active = i === currentStep
                            return (
                                <div key={step} className="flex items-center flex-1 last:flex-none">
                                    <div className="flex flex-col items-center">
                                        <div
                                            className={cn(
                                                'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors',
                                                done
                                                    ? 'bg-emerald-500 border-emerald-500 text-white'
                                                    : 'border-slate-200 dark:border-white/10 text-slate-400'
                                            )}
                                        >
                                            {done ? '✓' : i + 1}
                                        </div>
                                        <span className={cn(
                                            'text-[10px] mt-1.5 text-center capitalize',
                                            active ? 'font-semibold text-slate-900 dark:text-white' : 'text-slate-400'
                                        )}>
                                            {step.replace('_', ' ')}
                                        </span>
                                    </div>
                                    {i < statusSteps.length - 1 && (
                                        <div className={cn(
                                            'flex-1 h-0.5 mx-1',
                                            i < currentStep ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-white/10'
                                        )} />
                                    )}
                                </div>
                            )
                        })}
                    </div>
                )}

                {isRejected && request.rejection_reason && (
                    <div className="mt-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-sm text-red-700 dark:text-red-400">
                        <strong>Reason:</strong> {request.rejection_reason}
                    </div>
                )}
            </div>

            {/* Resource Items */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                    <h2 className="font-semibold text-slate-900 dark:text-white">Resources Requested</h2>
                </div>
                <div className="p-5 space-y-3">
                    {request.items?.length ? (
                        request.items.map((item, idx) => (
                            <div key={idx} className="flex items-center gap-4 p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                <ResourceTypeIcon type={item.resource_type} size="sm" />
                                <div className="flex-1">
                                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                                        {item.resource_type === 'Custom' ? item.custom_name || 'Custom' : item.resource_type}
                                    </p>
                                </div>
                                <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                                    ×{item.quantity}
                                </span>
                            </div>
                        ))
                    ) : (
                        <div className="flex items-center gap-4 p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                            <ResourceTypeIcon type={request.resource_type} size="sm" />
                            <div className="flex-1">
                                <p className="text-sm font-medium text-slate-900 dark:text-white">{request.resource_type}</p>
                            </div>
                            <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">×{request.quantity}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Fulfillment Progress */}
            {fulfillmentData && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                        <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                            <Package className="w-4 h-4 text-emerald-500" />
                            Fulfillment Progress
                        </h2>
                        <span className="text-sm font-bold text-emerald-600">{fulfillmentData.fulfillment_pct ?? 0}%</span>
                    </div>
                    <div className="p-5 space-y-4">
                        {/* Overall progress bar */}
                        <div>
                            <div className="w-full h-3 rounded-full bg-slate-100 dark:bg-white/10">
                                <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-600 transition-all"
                                    style={{ width: `${Math.min(fulfillmentData.fulfillment_pct ?? 0, 100)}%` }} />
                            </div>
                        </div>
                        {/* Per-item breakdown */}
                        {fulfillmentData.item_fulfillment && Object.entries(fulfillmentData.item_fulfillment).map(([type, info]: [string, any]) => (
                            <div key={type} className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-sm font-medium text-slate-900 dark:text-white">{type}</span>
                                    <span className="text-xs text-slate-500">{info.fulfilled} / {info.requested}</span>
                                </div>
                                <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-white/10">
                                    <div className="h-full rounded-full bg-emerald-500 transition-all"
                                        style={{ width: `${info.requested > 0 ? Math.min((info.fulfilled / info.requested) * 100, 100) : 0}%` }} />
                                </div>
                                {info.providers?.length > 0 && (
                                    <div className="mt-2 flex flex-wrap gap-1">
                                        {info.providers.map((p: any, i: number) => (
                                            <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                                {p.role}: {p.quantity} {p.unit || 'units'}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                        {fulfillmentData.entries?.length > 0 && (
                            <div className="text-xs text-slate-400">
                                {fulfillmentData.entries.length} contribution(s) from donors and NGOs
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Resource Pool */}
            {poolData && poolData.total_contributors > 0 && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                        <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                            <Users className="w-4 h-4 text-blue-500" />
                            Resource Pool
                        </h2>
                        <span className={cn(
                            'text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide',
                            poolData.pool_type === 'ngo_donor' ? 'bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400' :
                            poolData.pool_type === 'ngo_ngo' ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400' :
                            poolData.pool_type === 'donor_donor' ? 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400' :
                            'bg-slate-50 dark:bg-slate-500/10 text-slate-600 dark:text-slate-400'
                        )}>
                            {poolData.pool_type === 'ngo_donor' ? 'NGO + Donor Pool' :
                             poolData.pool_type === 'ngo_ngo' ? 'Multi-NGO Pool' :
                             poolData.pool_type === 'donor_donor' ? 'Multi-Donor Pool' :
                             `${poolData.total_contributors} Contributor`}
                        </span>
                    </div>
                    <div className="p-5 space-y-4">
                        {/* Per-item pool breakdown */}
                        {poolData.item_pool && Object.entries(poolData.item_pool).map(([type, info]: [string, any]) => (
                            <div key={type} className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-medium text-slate-900 dark:text-white">{type}</span>
                                    <span className="text-xs text-slate-500">{info.total_fulfilled} / {info.requested} fulfilled</span>
                                </div>
                                <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden flex">
                                    {info.requested > 0 && info.fulfilled_by_ngo > 0 && (
                                        <div className="h-full bg-blue-500 transition-all"
                                            style={{ width: `${Math.min((info.fulfilled_by_ngo / info.requested) * 100, 100)}%` }} />
                                    )}
                                    {info.requested > 0 && info.fulfilled_by_donor > 0 && (
                                        <div className="h-full bg-amber-500 transition-all"
                                            style={{ width: `${Math.min((info.fulfilled_by_donor / info.requested) * 100, 100 - (info.fulfilled_by_ngo / info.requested) * 100)}%` }} />
                                    )}
                                </div>
                                <div className="mt-1.5 flex items-center gap-3 text-[10px]">
                                    {info.fulfilled_by_ngo > 0 && (
                                        <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                                            <span className="w-2 h-2 rounded-full bg-blue-500" /> NGO: {info.fulfilled_by_ngo}
                                        </span>
                                    )}
                                    {info.fulfilled_by_donor > 0 && (
                                        <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                                            <span className="w-2 h-2 rounded-full bg-amber-500" /> Donor: {info.fulfilled_by_donor}
                                        </span>
                                    )}
                                    {info.gap > 0 && (
                                        <span className="text-red-500">Gap: {info.gap}</span>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* NGO Contributors */}
                        {poolData.ngo_contributors?.length > 0 && (
                            <div>
                                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-2">NGO Contributors ({poolData.ngo_contributors.length})</p>
                                <div className="space-y-2">
                                    {poolData.ngo_contributors.map((c: any, i: number) => (
                                        <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-blue-50/50 dark:bg-blue-500/5 border border-blue-100 dark:border-blue-500/10">
                                            <div className="flex items-center gap-2">
                                                <div className="w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center text-blue-600 dark:text-blue-400 text-[10px] font-bold">
                                                    NGO
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{c.provider_name}</p>
                                                    <p className="text-[10px] text-slate-400">
                                                        {c.resource_items?.map((ri: any) => `${ri.quantity} ${ri.resource_type}`).join(', ') || 'Resources'}
                                                    </p>
                                                </div>
                                            </div>
                                            <span className={cn(
                                                'text-[10px] px-2 py-0.5 rounded-full font-medium',
                                                c.status === 'availability_submitted' ? 'bg-blue-100 dark:bg-blue-500/10 text-blue-600' : 'bg-slate-100 dark:bg-white/5 text-slate-500'
                                            )}>{c.status?.replace('_', ' ')}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Donor Contributors */}
                        {poolData.donor_contributors?.length > 0 && (
                            <div>
                                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-2">Donor Contributors ({poolData.donor_contributors.length})</p>
                                <div className="space-y-2">
                                    {poolData.donor_contributors.map((c: any, i: number) => (
                                        <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-amber-50/50 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10">
                                            <div className="flex items-center gap-2">
                                                <div className="w-7 h-7 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center text-amber-600 dark:text-amber-400 text-[10px] font-bold">
                                                    DNR
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{c.provider_name}</p>
                                                    <p className="text-[10px] text-slate-400">
                                                        {c.donation_type === 'money' ? `$${c.amount?.toLocaleString()}` :
                                                         c.donation_type === 'both' ? `$${c.amount?.toLocaleString()} + ${c.resource_items?.map((ri: any) => `${ri.quantity} ${ri.resource_type}`).join(', ')}` :
                                                         c.resource_items?.map((ri: any) => `${ri.quantity} ${ri.resource_type}`).join(', ') || 'Resources'}
                                                    </p>
                                                </div>
                                            </div>
                                            <span className={cn(
                                                'text-[10px] px-2 py-0.5 rounded-full font-medium',
                                                c.status === 'pledged' ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-600' : 'bg-slate-100 dark:bg-white/5 text-slate-500'
                                            )}>{c.status}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {poolData.total_money > 0 && (
                            <div className="text-xs text-slate-500 dark:text-slate-400 pt-1 border-t border-slate-100 dark:border-white/5">
                                Total monetary contributions: <span className="font-semibold text-emerald-600">${poolData.total_money?.toLocaleString()}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Details grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Calendar className="w-4 h-4 text-slate-400" />
                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Dates</span>
                    </div>
                    <p suppressHydrationWarning className="text-sm text-slate-700 dark:text-slate-300">Created: {format(new Date(request.created_at), 'MMM d, yyyy h:mm a')}</p>
                    <p suppressHydrationWarning className="text-sm text-slate-700 dark:text-slate-300 mt-1">Updated: {format(new Date(request.updated_at), 'MMM d, yyyy h:mm a')}</p>
                </div>

                {(request.address_text || request.latitude) && (
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                        <div className="flex items-center gap-2 mb-2">
                            <MapPin className="w-4 h-4 text-slate-400" />
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Location</span>
                        </div>
                        {request.address_text && <p className="text-sm text-slate-700 dark:text-slate-300">{request.address_text}</p>}
                        {request.latitude && request.longitude && (
                            <p className="text-xs text-slate-400 mt-1">📍 {request.latitude.toFixed(4)}, {request.longitude.toFixed(4)}</p>
                        )}
                    </div>
                )}

                {request.assigned_to && (
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                        <div className="flex items-center gap-2 mb-2">
                            <User className="w-4 h-4 text-slate-400" />
                            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Assigned To</span>
                        </div>
                        <p className="text-sm text-slate-700 dark:text-slate-300">{request.assigned_role?.toUpperCase() || 'Helper'}</p>
                    </div>
                )}
            </div>

            {request.description && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-2">Description</h3>
                    <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">{request.description}</p>
                </div>
            )}

            {/* Timeline / Audit Trail */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                <div className="flex items-center gap-2 mb-4">
                    <Activity className="w-5 h-5 text-emerald-500" />
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Status Timeline</h3>
                </div>
                {isLoadingTimeline ? (
                    <div className="flex justify-center py-4 text-slate-400">
                        <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                ) : timelineData?.timeline && timelineData.timeline.length > 0 ? (
                    <div className="relative border-l-2 border-slate-100 dark:border-slate-800 ml-3 space-y-6">
                        {timelineData.timeline.map((event: any, idx: number) => (
                            <div key={idx} className="relative pl-6">
                                <span className={cn(
                                    "absolute -left-1.5 top-1.5 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900",
                                    idx === 0 ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-700"
                                )} />
                                <div className="flex items-start justify-between gap-4">
                                    <div>
                                        <p className="text-sm font-semibold text-slate-900 dark:text-white capitalize">
                                            {event.action_type === 'status_change' ? `${event.details?.old_status || 'Pending'} → ${event.details?.new_status}` : event.action_type.replace(/_/g, ' ')}
                                        </p>
                                        <p className="text-xs text-slate-500 mt-1">
                                            {event.actor_role === 'victim' ? 'You' : event.actor_role === 'admin' ? 'NGO Liaison' : event.actor_role} — {event.details?.note || 'No notes'}
                                        </p>
                                    </div>
                                    <span className="text-[10px] text-slate-400 whitespace-nowrap">
                                        {format(new Date(event.created_at), 'MMM d, h:mm a')}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-xs text-slate-500">No timeline data available yet.</p>
                )}
            </div>

            {/* NLP Classification & Urgency Signals (Phase 3) */}
            {(request.urgency_signals?.length || request.ai_confidence != null) && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center gap-2">
                        <Brain className="w-4 h-4 text-amber-500" />
                        <h2 className="font-semibold text-slate-900 dark:text-white">AI Triage Analysis</h2>
                        {request.ai_confidence != null && (
                            <ConfidenceBadge confidence={request.ai_confidence} />
                        )}
                        {request.nlp_overridden && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                Overridden
                            </span>
                        )}
                    </div>
                    <div className="p-5 space-y-3">
                        {request.nlp_classification && (
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-white/[0.03]">
                                    <span className="text-slate-500 dark:text-slate-400">Detected Types</span>
                                    <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                                        {request.nlp_classification.resource_types?.join(', ') || 'N/A'}
                                    </p>
                                </div>
                                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-white/[0.03]">
                                    <span className="text-slate-500 dark:text-slate-400">Recommended Priority</span>
                                    <p className="font-semibold text-slate-900 dark:text-white mt-0.5 capitalize">
                                        {request.nlp_classification.recommended_priority || 'N/A'}
                                        {request.nlp_classification.priority_was_escalated && (
                                            <span className="ml-1 text-red-500">↑ escalated</span>
                                        )}
                                    </p>
                                </div>
                                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-white/[0.03]">
                                    <span className="text-slate-500 dark:text-slate-400">Est. Quantity</span>
                                    <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                                        {request.nlp_classification.estimated_quantity || 'N/A'}
                                    </p>
                                </div>
                            </div>
                        )}
                        {request.urgency_signals && request.urgency_signals.length > 0 && (
                            <div>
                                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">Urgency Signals</p>
                                <UrgencyTags signals={request.urgency_signals} max={10} />
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Delivery Confirmation (shown when status is 'delivered') */}
            {request.status === 'delivered' && (
                <DeliveryConfirmation requestId={request.id} />
            )}

            {/* Delete confirmation modal */}
            {showDelete && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm" onClick={() => setShowDelete(false)}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/10 p-6 max-w-sm w-full mx-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                            {request.status === 'pending' ? 'Delete Request?' : 'Cancel Request?'}
                        </h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">This action cannot be undone.</p>
                        <div className="flex gap-3 mt-5">
                            <button
                                onClick={() => setShowDelete(false)}
                                className="flex-1 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                            >
                                Keep
                            </button>
                            <button
                                onClick={() => deleteMut.mutate()}
                                disabled={deleteMut.isPending}
                                className="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-sm font-semibold hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {deleteMut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                                Confirm
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
