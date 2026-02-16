'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getResourceRequest, deleteResourceRequest, type ResourceRequest } from '@/lib/api/victim'
import { StatusBadge, PriorityBadge, ResourceTypeIcon } from './StatusBadge'
import { cn } from '@/lib/utils'
import { ArrowLeft, Edit3, Trash2, Loader2, MapPin, Calendar, User, Package } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { format } from 'date-fns'
import { useState } from 'react'

const statusSteps = ['pending', 'approved', 'assigned', 'in_progress', 'completed']

export function RequestDetail({ requestId }: { requestId: string }) {
    const router = useRouter()
    const queryClient = useQueryClient()
    const [showDelete, setShowDelete] = useState(false)

    const { data: request, isLoading } = useQuery<ResourceRequest>({
        queryKey: ['victim-request', requestId],
        queryFn: () => getResourceRequest(requestId),
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
    const canDelete = ['pending', 'approved', 'assigned', 'in_progress'].includes(request.status)

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

            {/* Description */}
            {request.description && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-2">Description</h3>
                    <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">{request.description}</p>
                </div>
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
