'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { subscribeToTable } from '@/lib/realtime'
import { cn } from '@/lib/utils'
import {
    Loader2, Search, Package, Heart, DollarSign,
    CheckCircle2, MapPin, Clock, ChevronLeft, ChevronRight,
    AlertTriangle, HandHeart, RefreshCw, Navigation, Users
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
    const [donationType, setDonationType] = useState<'money' | 'resource' | 'both'>('resource')
    const [pledgeAmount, setPledgeAmount] = useState(0)
    const [resourceItems, setResourceItems] = useState<{ resource_type: string; quantity: number; unit: string }[]>([])
    const [page, setPage] = useState(1)
    const [sortBy, setSortBy] = useState<'priority' | 'distance'>('priority')
    const [gps, setGps] = useState<{ lat: number; lon: number } | null>(null)
    const [poolModal, setPoolModal] = useState<string | null>(null)
    const [gpsStatus, setGpsStatus] = useState<'detecting' | 'success' | 'error'>('detecting')
    const [pledgeError, setPledgeError] = useState('')

    // Auto-detect GPS on mount
    useEffect(() => {
        if (typeof navigator !== 'undefined' && navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    setGps({ lat: pos.coords.latitude, lon: pos.coords.longitude })
                    setGpsStatus('success')
                },
                () => setGpsStatus('error'),
                { enableHighAccuracy: true, timeout: 15000 }
            )
        } else {
            setGpsStatus('error')
        }
    }, [])

    // Fetch approved / needs-help requests (donor-accessible endpoint)
    const { data, isLoading, refetch } = useQuery({
        queryKey: ['donor-fulfill', page, gps?.lat, gps?.lon, sortBy],
        queryFn: () => api.getDonorApprovedRequests({
            page,
            page_size: 20,
            donor_latitude: gps?.lat,
            donor_longitude: gps?.lon,
            sort: sortBy,
        }),
        refetchInterval: 30000,
    })

    // Realtime
    useEffect(() => {
        const unsub = subscribeToTable('resource_requests', () => {
            qc.invalidateQueries({ queryKey: ['donor-fulfill'] })
        })
        return () => { unsub() }
    }, [qc])

    const requests = data?.requests || []
    const total = data?.total || 0

    const { data: poolData } = useQuery({
        queryKey: ['donor-request-pool', poolModal],
        queryFn: () => poolModal ? api.getDonorRequestPool(poolModal) : null,
        enabled: !!poolModal,
    })

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

            {/* Search + Sort Controls */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search requests by type, description..."
                        className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-pink-500 focus:outline-none" />
                </div>
                <div className="flex gap-2 items-center">
                    <button onClick={() => setSortBy('priority')}
                        className={cn('px-3 py-2 rounded-lg text-xs font-medium border transition-all',
                            sortBy === 'priority' ? 'bg-pink-600 text-white border-pink-600' : 'bg-white dark:bg-slate-900 text-slate-600 border-slate-200 dark:border-slate-700')}>
                        By Priority
                    </button>
                    <button onClick={() => setSortBy('distance')}
                        disabled={gpsStatus !== 'success'}
                        className={cn('px-3 py-2 rounded-lg text-xs font-medium border transition-all',
                            sortBy === 'distance' ? 'bg-pink-600 text-white border-pink-600' : 'bg-white dark:bg-slate-900 text-slate-600 border-slate-200 dark:border-slate-700',
                            gpsStatus !== 'success' && 'opacity-40 cursor-not-allowed')}>
                        <span className="flex items-center gap-1"><Navigation className="w-3 h-3" /> By Distance</span>
                    </button>
                    {gpsStatus === 'success' && (
                        <span className="text-[10px] text-green-600 flex items-center gap-1"><Navigation className="w-3 h-3" /> GPS active</span>
                    )}
                    {gpsStatus === 'error' && (
                        <span className="text-[10px] text-amber-500">GPS unavailable</span>
                    )}
                </div>
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
                                        {req.distance_km !== null && req.distance_km !== undefined && (
                                            <span className="flex items-center gap-1 text-cyan-600 font-medium">
                                                <Navigation className="w-3 h-3" /> {req.distance_km} km
                                            </span>
                                        )}
                                    </div>
                                    {/* Fulfillment progress */}
                                    {(req.fulfillment_pct != null && req.fulfillment_pct > 0) && (
                                        <div className="mt-2">
                                            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                                                <span>Fulfilled</span>
                                                <span className="font-semibold text-emerald-600">{req.fulfillment_pct}%</span>
                                            </div>
                                            <div className="w-full h-1.5 rounded-full bg-slate-100 dark:bg-white/10">
                                                <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${Math.min(req.fulfillment_pct, 100)}%` }} />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-slate-400">{new Date(req.created_at).toLocaleDateString()}</span>
                                    {(req.fulfillment_pct > 0 || req.fulfillment_entries?.length > 0) && (
                                        <button
                                            onClick={() => setPoolModal(req.id)}
                                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 text-[10px] font-medium hover:bg-blue-100 dark:hover:bg-blue-500/20 transition-colors"
                                        >
                                            <Users className="w-3 h-3" /> Pool
                                        </button>
                                    )}
                                </div>
                                {req.already_pledged ? (
                                    <span className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-green-100 dark:bg-green-500/10 text-green-600 text-xs font-semibold">
                                        <CheckCircle2 className="w-3.5 h-3.5" /> Pledged
                                    </span>
                                ) : (
                                    <button
                                        onClick={() => {
                                            // Auto-populate resource items with request's resource type and remaining quantity
                                            const totalRequested = req.quantity || 1
                                            const alreadyFulfilled = Math.round((req.fulfillment_pct || 0) * totalRequested / 100)
                                            const remaining = Math.max(1, totalRequested - alreadyFulfilled)
                                            setResourceItems([{ resource_type: req.resource_type || 'Resource', quantity: remaining, unit: 'units' }])
                                            setDonationType('resource')
                                            setPledgeAmount(0)
                                            setPledgeNote('')
                                            setPledgeError('')
                                            setPledgeModal(req)
                                        }}
                                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-500 text-white text-xs font-semibold hover:from-pink-600 hover:to-rose-600 shadow-lg shadow-pink-500/20 transition-all group-hover:scale-105">
                                        <Heart className="w-3.5 h-3.5" /> Pledge Support
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Pledge Modal */}
            {pledgeModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-950 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Pledge Support</h2>
                        <p className="text-sm text-slate-500 mb-4">
                            Helping with: <span className="font-semibold text-slate-700 dark:text-slate-300">{pledgeModal.resource_type}</span> (Qty: {pledgeModal.quantity || 1})
                            {pledgeModal.fulfillment_pct > 0 && (
                                <span className="ml-2 text-xs text-emerald-600">
                                    ({pledgeModal.fulfillment_pct}% fulfilled — {Math.max(1, (pledgeModal.quantity || 1) - Math.round((pledgeModal.fulfillment_pct || 0) * (pledgeModal.quantity || 1) / 100))} remaining)
                                </span>
                            )}
                        </p>
                        {pledgeError && (
                            <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                                <p className="text-xs text-red-600 dark:text-red-400 font-medium">{pledgeError}</p>
                            </div>
                        )}

                        {/* Donation type selector */}
                        <div className="mb-4">
                            <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-2 block">Donation Type</label>
                            <div className="flex gap-2">
                                {(['resource', 'money', 'both'] as const).map(t => (
                                    <button key={t} onClick={() => {
                                        setDonationType(t)
                                        // Repopulate resource items when switching to resource/both
                                        if (t === 'resource' || t === 'both') {
                                            if (resourceItems.length === 0) {
                                                const totalReq = pledgeModal.quantity || 1
                                                const alreadyDone = Math.round((pledgeModal.fulfillment_pct || 0) * totalReq / 100)
                                                const rem = Math.max(1, totalReq - alreadyDone)
                                                setResourceItems([{ resource_type: pledgeModal.resource_type || 'Resource', quantity: rem, unit: 'units' }])
                                            }
                                        } else {
                                            setResourceItems([])
                                        }
                                    }}
                                        className={cn('flex-1 px-3 py-2 rounded-lg text-xs font-medium border transition-all capitalize',
                                            donationType === t ? 'bg-pink-600 text-white border-pink-600' : 'bg-white dark:bg-slate-900 text-slate-600 border-slate-200 dark:border-slate-700')}>
                                        {t === 'both' ? 'Money + Resources' : t === 'money' ? '💰 Money' : '📦 Resources'}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Money amount */}
                        {(donationType === 'money' || donationType === 'both') && (
                            <div className="mb-4">
                                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-1 block">Amount (USD)</label>
                                <input type="number" min={0} value={pledgeAmount} onChange={e => setPledgeAmount(Number(e.target.value))}
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-pink-500 focus:outline-none" />
                            </div>
                        )}

                        {/* Resource items */}
                        {(donationType === 'resource' || donationType === 'both') && (
                            <div className="mb-4">
                                <div className="flex items-center justify-between mb-2">
                                    <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Resource Items</label>
                                    <button onClick={() => setResourceItems(prev => [...prev, { resource_type: pledgeModal.resource_type || '', quantity: 1, unit: 'units' }])}
                                        className="text-xs text-pink-600 font-medium hover:text-pink-700">+ Add Item</button>
                                </div>
                                {resourceItems.length === 0 && (
                                    <p className="text-xs text-slate-400 mb-2">Click &quot;+ Add Item&quot; to specify what resources you&apos;re donating</p>
                                )}
                                <div className="space-y-2">
                                    {resourceItems.map((item, idx) => (
                                        <div key={idx} className="flex gap-2 items-center">
                                            <input value={item.resource_type} onChange={e => {
                                                const next = [...resourceItems]; next[idx] = { ...next[idx], resource_type: e.target.value }; setResourceItems(next)
                                            }} placeholder="Type (e.g. Water)"
                                                className="flex-1 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs focus:ring-2 focus:ring-pink-500 focus:outline-none" />
                                            <input type="number" min={1} value={item.quantity} onChange={e => {
                                                const next = [...resourceItems]; next[idx] = { ...next[idx], quantity: Number(e.target.value) }; setResourceItems(next)
                                            }} placeholder="Qty"
                                                className="w-20 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs focus:ring-2 focus:ring-pink-500 focus:outline-none" />
                                            <input value={item.unit} onChange={e => {
                                                const next = [...resourceItems]; next[idx] = { ...next[idx], unit: e.target.value }; setResourceItems(next)
                                            }} placeholder="Unit"
                                                className="w-20 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs focus:ring-2 focus:ring-pink-500 focus:outline-none" />
                                            <button onClick={() => setResourceItems(prev => prev.filter((_, i) => i !== idx))}
                                                className="text-red-400 hover:text-red-500 text-sm">✕</button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <textarea value={pledgeNote} onChange={e => setPledgeNote(e.target.value)}
                            placeholder="Add a note about your pledge (optional)..."
                            rows={2}
                            className="w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm mb-4 focus:ring-2 focus:ring-pink-500 focus:outline-none resize-none" />
                        <div className="flex gap-3">
                            <button onClick={() => { setPledgeModal(null); setPledgeNote(''); setPledgeError(''); setResourceItems([]); setPledgeAmount(0); setDonationType('resource') }}
                                className="flex-1 h-10 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    setPledgeError('')
                                    api.createDonation({
                                        disaster_id: pledgeModal.disaster_id || null,
                                        request_id: pledgeModal.id,
                                        amount: (donationType === 'money' || donationType === 'both') ? pledgeAmount : 0,
                                        status: 'pending',
                                        notes: pledgeNote,
                                        donation_type: donationType,
                                        resource_items: (donationType === 'resource' || donationType === 'both') ? resourceItems : undefined,
                                    }).then(() => {
                                        setPledgeModal(null)
                                        setPledgeNote('')
                                        setPledgeError('')
                                        setResourceItems([])
                                        setPledgeAmount(0)
                                        setDonationType('resource')
                                        refetch()
                                    }).catch((err: any) => {
                                        setPledgeError(err?.message || 'Failed to submit pledge. Please try again.')
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

            {/* Resource Pool Modal */}
            {poolModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-950 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6 max-h-[80vh] overflow-y-auto">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <Users className="w-5 h-5 text-blue-500" /> Resource Pool
                            </h2>
                            <button onClick={() => setPoolModal(null)} className="text-slate-400 hover:text-slate-700 dark:hover:text-white text-sm">✕</button>
                        </div>
                        {!poolData ? (
                            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
                        ) : poolData.total_contributors === 0 ? (
                            <p className="text-sm text-slate-500 text-center py-6">No contributors yet. Be the first to pledge!</p>
                        ) : (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
                                    <span className="text-sm text-slate-600 dark:text-slate-400">Fulfillment</span>
                                    <span className="text-lg font-bold text-emerald-600">{poolData.fulfillment_pct ?? 0}%</span>
                                </div>
                                <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-white/10">
                                    <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${Math.min(poolData.fulfillment_pct ?? 0, 100)}%` }} />
                                </div>

                                {poolData.ngo_contributors?.length > 0 && (
                                    <div>
                                        <p className="text-xs font-semibold text-blue-600 uppercase mb-2">NGOs ({poolData.ngo_contributors.length})</p>
                                        {poolData.ngo_contributors.map((c: any, i: number) => (
                                            <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-blue-50/50 dark:bg-blue-500/5 border border-blue-100 dark:border-blue-500/10 mb-1.5">
                                                <div>
                                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{c.provider_name}</p>
                                                    <p className="text-[10px] text-slate-400">
                                                        {c.resource_items?.map((ri: any) => `${ri.quantity} ${ri.resource_type}`).join(', ') || 'Resources'}
                                                    </p>
                                                </div>
                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-600 font-medium">{c.status?.replace('_', ' ')}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {poolData.donor_contributors?.length > 0 && (
                                    <div>
                                        <p className="text-xs font-semibold text-amber-600 uppercase mb-2">Donors ({poolData.donor_contributors.length})</p>
                                        {poolData.donor_contributors.map((c: any, i: number) => (
                                            <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-amber-50/50 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10 mb-1.5">
                                                <div>
                                                    <p className="text-sm font-medium text-slate-900 dark:text-white">{c.provider_name}</p>
                                                    <p className="text-[10px] text-slate-400">
                                                        {c.donation_type === 'money' ? `$${c.amount?.toLocaleString()}` :
                                                         c.resource_items?.map((ri: any) => `${ri.quantity} ${ri.resource_type}`).join(', ') || 'Resources'}
                                                    </p>
                                                </div>
                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-600 font-medium">{c.status}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
