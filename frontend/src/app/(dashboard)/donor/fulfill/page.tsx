'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { createClient } from '@/lib/supabase/client'
import { cn } from '@/lib/utils'
import {
    Loader2, Search, Package, Heart, DollarSign,
    CheckCircle2, MapPin, Clock, ChevronLeft, ChevronRight,
    AlertTriangle, HandHeart, RefreshCw
} from 'lucide-react'

const PRIORITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-green-500',
}

export default function DonorFulfillPage() {
    const { profile } = useAuth()
    const qc = useQueryClient()
    const [search, setSearch] = useState('')
    const [pledgeModal, setPledgeModal] = useState<any | null>(null)
    const [pledgeNote, setPledgeNote] = useState('')
    const [page, setPage] = useState(1)

    // Fetch approved / needs-help requests
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['donor-fulfill', page],
        queryFn: () => api.getAdminRequests({ status: 'approved', page, page_size: 20 }),
        refetchInterval: 30000,
    })

    // Realtime
    useEffect(() => {
        const supabase = createClient()
        const channel = supabase
            .channel('donor-requests')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'resource_requests' }, () => {
                qc.invalidateQueries({ queryKey: ['donor-fulfill'] })
            })
            .subscribe()
        return () => { supabase.removeChannel(channel) }
    }, [qc])

    const requests = data?.requests || []
    const total = data?.total || 0

    const filtered = search
        ? requests.filter((r: any) =>
            (r.description || r.resource_type || '').toLowerCase().includes(search.toLowerCase())
        )
        : requests

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-pink-500 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Heart className="w-6 h-6 text-pink-500" />
                        Sponsor a Request
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Browse approved requests and pledge resources to help victims
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <AlertTriangle className="w-6 h-6 text-amber-500 mb-2" />
                    <p className="text-2xl font-bold text-slate-900 dark:text-white">{total}</p>
                    <p className="text-xs text-slate-500">Requests Needing Help</p>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <Package className="w-6 h-6 text-purple-500 mb-2" />
                    <p className="text-2xl font-bold text-slate-900 dark:text-white">
                        {requests.filter((r: any) => r.priority === 'critical' || r.priority === 'high').length}
                    </p>
                    <p className="text-xs text-slate-500">Urgent Requests</p>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <HandHeart className="w-6 h-6 text-pink-500 mb-2" />
                    <p className="text-2xl font-bold text-slate-900 dark:text-white">
                        {new Set(requests.map((r: any) => r.resource_type)).size}
                    </p>
                    <p className="text-xs text-slate-500">Resource Types</p>
                </div>
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search requests by type, description..."
                    className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-pink-500 focus:outline-none" />
            </div>

            {/* Request cards - grid layout */}
            {filtered.length === 0 ? (
                <div className="text-center py-16">
                    <CheckCircle2 className="w-12 h-12 text-green-300 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">All requests are being fulfilled!</p>
                    <p className="text-sm text-slate-400 mt-1">Check back later for new requests that need support</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {filtered.map((req: any) => (
                        <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg transition-all group">
                            <div className="flex items-start gap-3">
                                <div className={cn('w-3 h-3 rounded-full mt-1 shrink-0', PRIORITY_COLORS[req.priority] || 'bg-slate-400')} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{req.resource_type || 'Resource'}</h3>
                                        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 capitalize">{req.priority}</span>
                                    </div>
                                    {req.description && (
                                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{req.description}</p>
                                    )}
                                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                                        {req.victim_name && <span>👤 {req.victim_name}</span>}
                                        <span>Qty: {req.quantity || 1}</span>
                                        {req.address_text && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{req.address_text}</span>}
                                    </div>
                                </div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between">
                                <span className="text-[10px] text-slate-400">{new Date(req.created_at).toLocaleDateString()}</span>
                                <button
                                    onClick={() => setPledgeModal(req)}
                                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 text-white text-xs font-semibold hover:from-pink-600 hover:to-rose-600 shadow-lg shadow-pink-500/20 transition-all group-hover:scale-105">
                                    <Heart className="w-3.5 h-3.5" /> Pledge Support
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Pledge Modal */}
            {pledgeModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-950 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Pledge Support</h2>
                        <p className="text-sm text-slate-500 mb-4">
                            You're pledging to help with: <span className="font-semibold text-slate-700 dark:text-slate-300">{pledgeModal.resource_type}</span> (Qty: {pledgeModal.quantity || 1})
                        </p>
                        <textarea value={pledgeNote} onChange={e => setPledgeNote(e.target.value)}
                            placeholder="Add a note about your pledge (optional)..."
                            rows={3}
                            className="w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm mb-4 focus:ring-2 focus:ring-pink-500 focus:outline-none resize-none" />
                        <div className="flex gap-3">
                            <button onClick={() => { setPledgeModal(null); setPledgeNote('') }}
                                className="flex-1 h-10 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    // Create a donation record linked to this request
                                    api.createDonation({
                                        disaster_id: pledgeModal.disaster_id || null,
                                        request_id: pledgeModal.id,
                                        amount: 0,
                                        status: 'pending',
                                        notes: pledgeNote
                                    }).then(() => {
                                        setPledgeModal(null)
                                        setPledgeNote('')
                                        refetch()
                                    }).catch(() => {
                                        setPledgeModal(null)
                                        setPledgeNote('')
                                    })
                                }}
                                className="flex-1 h-10 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 text-white text-sm font-semibold hover:from-pink-600 hover:to-rose-600">
                                Confirm Pledge
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Pagination */}
            {Math.ceil(total / 20) > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500">Page {page} of {Math.ceil(total / 20)}</p>
                    <div className="flex gap-2">
                        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40">
                            <ChevronLeft className="w-3.5 h-3.5" /> Prev
                        </button>
                        <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40">
                            Next <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
