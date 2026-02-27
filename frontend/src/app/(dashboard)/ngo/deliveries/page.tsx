'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import {
    Loader2, Truck, Play, CheckCircle2, Package, MapPin,
    RefreshCw, Navigation, Clock, User, Upload,
    FileText, ArrowRight, Search, MessageSquare,
} from 'lucide-react'

const STATUS_STEPS = [
    { key: 'assigned', label: 'Assigned', icon: Package },
    { key: 'in_progress', label: 'In Transit', icon: Truck },
    { key: 'delivered', label: 'Delivered', icon: MapPin },
    { key: 'completed', label: 'Completed', icon: CheckCircle2 },
]

export default function NGODeliveryTrackingPage() {
    const qc = useQueryClient()
    const [search, setSearch] = useState('')
    const [proofModal, setProofModal] = useState<any>(null)
    const [proofUrl, setProofUrl] = useState('')
    const [proofNotes, setProofNotes] = useState('')

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-deliveries'],
        queryFn: () => api.getNgoAssignedRequests({ limit: 50 }),
        refetchInterval: 10000,
    })

    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('ngo-delivery-rt')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'resource_requests' }, () => {
                qc.invalidateQueries({ queryKey: ['ngo-deliveries'] })
            })
            .subscribe()
        return () => { supabase.removeChannel(channel) }
    }, [qc])

    const statusMutation = useMutation({
        mutationFn: ({ id, newStatus }: { id: string; newStatus: string }) =>
            api.updateNgoDeliveryStatus(id, { new_status: newStatus, proof_url: proofUrl || undefined, notes: proofNotes || undefined }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-deliveries'] })
            qc.invalidateQueries({ queryKey: ['ngo-enhanced-stats'] })
            setProofModal(null)
            setProofUrl('')
            setProofNotes('')
        },
    })

    const requests = data?.requests || []

    // Split into active deliveries and completed
    const activeDeliveries = requests.filter((r: any) => ['assigned', 'in_progress', 'delivered'].includes(r.status))
    const completedDeliveries = requests.filter((r: any) => r.status === 'completed')

    const filtered = search
        ? activeDeliveries.filter((r: any) =>
            (r.description || r.resource_type || r.victim_name || '').toLowerCase().includes(search.toLowerCase())
        )
        : activeDeliveries

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
                <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
                <span className="text-sm text-slate-500">Loading deliveries...</span>
            </div>
        )
    }

    const getStepIndex = (status: string) => STATUS_STEPS.findIndex(s => s.key === status)

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Truck className="w-6 h-6 text-purple-500" />
                        Delivery Tracking
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Monitor active deliveries, update statuses, and record proof of delivery.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-4 text-sm">
                        <span className="flex items-center gap-1.5">
                            <div className="w-3 h-3 rounded-full bg-orange-500" />
                            <span className="text-slate-500">{activeDeliveries.filter((r: any) => r.status === 'assigned').length} Awaiting</span>
                        </span>
                        <span className="flex items-center gap-1.5">
                            <div className="w-3 h-3 rounded-full bg-yellow-500 animate-pulse" />
                            <span className="text-slate-500">{activeDeliveries.filter((r: any) => r.status === 'in_progress').length} In Transit</span>
                        </span>
                        <span className="flex items-center gap-1.5">
                            <div className="w-3 h-3 rounded-full bg-green-500" />
                            <span className="text-slate-500">{completedDeliveries.length} Completed</span>
                        </span>
                    </div>
                    <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5">
                        <RefreshCw className="w-4 h-4" /> Refresh
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="relative max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search active deliveries..."
                    className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
            </div>

            {/* Active Deliveries */}
            {filtered.length === 0 ? (
                <div className="text-center py-16 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]">
                    <Truck className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">No active deliveries</p>
                    <p className="text-sm text-slate-400 mt-1">Deliveries will appear here once requests are assigned to you.</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {filtered.map((req: any) => {
                        const currentStep = getStepIndex(req.status)
                        return (
                            <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6 hover:shadow-lg transition-all">
                                {/* Header Row */}
                                <div className="flex items-start justify-between mb-5">
                                    <div>
                                        <div className="flex items-center gap-2 mb-1">
                                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{req.resource_type}</h3>
                                            <span className="text-[10px] text-slate-400 font-mono">{req.id?.slice(0, 8)}</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-slate-400">
                                            <span className="flex items-center gap-1"><User className="w-3 h-3" /> {req.victim_name || 'Unknown'}</span>
                                            {req.address_text && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {req.address_text}</span>}
                                            <span>Qty: {req.quantity}</span>
                                            {req.distance_km && <span className="text-cyan-500 flex items-center gap-1"><Navigation className="w-3 h-3" /> {req.distance_km} km</span>}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => setProofModal(req)}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                                            <Upload className="w-3 h-3" /> Upload Proof
                                        </button>
                                    </div>
                                </div>

                                {/* Progress Steps */}
                                <div className="flex items-center gap-0">
                                    {STATUS_STEPS.map((step, idx) => {
                                        const Icon = step.icon
                                        const isDone = idx <= currentStep
                                        const isCurrent = idx === currentStep
                                        return (
                                            <div key={step.key} className="flex items-center flex-1">
                                                <div className="flex flex-col items-center w-full">
                                                    <div className={cn(
                                                        'w-9 h-9 rounded-full flex items-center justify-center border-2 transition-all',
                                                        isCurrent ? 'border-purple-500 bg-purple-50 dark:bg-purple-500/10 ring-4 ring-purple-500/10' :
                                                            isDone ? 'border-green-500 bg-green-50 dark:bg-green-500/10' :
                                                                'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900'
                                                    )}>
                                                        <Icon className={cn('w-4 h-4',
                                                            isCurrent ? 'text-purple-600 dark:text-purple-400' :
                                                                isDone ? 'text-green-600 dark:text-green-400' :
                                                                    'text-slate-300 dark:text-slate-600'
                                                        )} />
                                                    </div>
                                                    <span className={cn('text-[10px] mt-1.5 font-medium text-center',
                                                        isCurrent ? 'text-purple-600' : isDone ? 'text-green-600' : 'text-slate-400'
                                                    )}>{step.label}</span>
                                                </div>
                                                {idx < STATUS_STEPS.length - 1 && (
                                                    <div className={cn('h-0.5 flex-1 -mt-4 mx-1', isDone && idx < currentStep ? 'bg-green-400' : 'bg-slate-200 dark:bg-slate-700')} />
                                                )}
                                            </div>
                                        )
                                    })}
                                </div>

                                {/* Progress bar */}
                                <div className="mt-4 space-y-1.5">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-400">Overall Progress</span>
                                        <span className="font-bold text-slate-600 dark:text-slate-400">{req.progress_pct}%</span>
                                    </div>
                                    <div className="h-2.5 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <div className="h-full rounded-full bg-gradient-to-r from-purple-500 to-cyan-500 transition-all duration-700"
                                            style={{ width: `${Math.max(4, req.progress_pct)}%` }} />
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Recently Completed */}
            {completedDeliveries.length > 0 && (
                <div>
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2">
                        <CheckCircle2 className="w-5 h-5 text-green-500" /> Recently Completed ({completedDeliveries.length})
                    </h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {completedDeliveries.slice(0, 6).map((req: any) => (
                            <div key={req.id} className="rounded-xl border border-green-200 dark:border-green-500/20 bg-green-50/50 dark:bg-green-500/5 p-4">
                                <div className="flex items-center gap-2 mb-1">
                                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                                    <span className="text-sm font-medium text-slate-900 dark:text-white">{req.resource_type}</span>
                                </div>
                                <p className="text-xs text-slate-500 flex items-center gap-1"><User className="w-3 h-3" /> {req.victim_name || 'Unknown'}</p>
                                <p className="text-[10px] text-slate-400 mt-1">{new Date(req.updated_at).toLocaleString()}</p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Upload Proof Modal */}
            {proofModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Upload Delivery Proof</h2>
                        <div className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Proof URL</label>
                                <input type="url" value={proofUrl} onChange={e => setProofUrl(e.target.value)}
                                    placeholder="https://... (link to photo or document)"
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Delivery Notes</label>
                                <textarea value={proofNotes} onChange={e => setProofNotes(e.target.value)} rows={3}
                                    placeholder="Describe the delivery..."
                                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none resize-none" />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-4">
                            <button onClick={() => { setProofModal(null); setProofUrl(''); setProofNotes('') }}
                                className="flex-1 h-10 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5">
                                Cancel
                            </button>
                            <button onClick={() => {
                                const nextStatus = proofModal.status === 'assigned' ? 'in_progress' : proofModal.status === 'in_progress' ? 'delivered' : proofModal.status === 'delivered' ? 'completed' : null
                                if (nextStatus) statusMutation.mutate({ id: proofModal.id, newStatus: nextStatus })
                            }}
                                disabled={statusMutation.isPending}
                                className="flex-1 h-10 rounded-xl bg-gradient-to-r from-purple-600 to-cyan-600 text-white text-sm font-semibold hover:from-purple-700 hover:to-cyan-700 disabled:opacity-50 flex items-center justify-center gap-2">
                                {statusMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                Save & Advance
                            </button>
                        </div>
                        {statusMutation.error && (
                            <div className="mt-3 p-2 rounded-lg bg-red-50 dark:bg-red-500/10 text-xs text-red-600">{(statusMutation.error as Error).message}</div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
