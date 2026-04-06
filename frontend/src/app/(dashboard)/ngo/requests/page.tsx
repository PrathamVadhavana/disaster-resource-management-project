'use client'

import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { subscribeToTable } from '@/lib/realtime'
import { SubmitAvailabilityModal } from '@/components/ngo/SubmitAvailabilityModal'
import {
    Loader2, Search, MapPin, Package, ChevronLeft, ChevronRight,
    ArrowRight, AlertTriangle, CheckCircle2, Eye, Send,
    RefreshCw, Navigation, Calendar, User, Users, Building2,
} from 'lucide-react'

const PRIORITY_DOT: Record<string, string> = {
    critical: 'bg-red-500 animate-pulse', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-green-500',
}

const PRIORITY_BADGE: Record<string, string> = {
    critical: 'bg-red-100 dark:bg-red-500/10 text-red-600 ring-red-500/20',
    high: 'bg-orange-100 dark:bg-orange-500/10 text-orange-600 ring-orange-500/20',
    medium: 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 ring-amber-500/20',
    low: 'bg-green-100 dark:bg-green-500/10 text-green-600 ring-green-500/20',
}

export default function NGOApprovedRequestsPage() {
    const qc = useQueryClient()
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [priorityFilter, setPriorityFilter] = useState('')
    const [selectedRequest, setSelectedRequest] = useState<any>(null)
    const [showAvailabilityModal, setShowAvailabilityModal] = useState<any>(null)
    const [sortBy, setSortBy] = useState<'priority' | 'distance'>('priority')
    const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null)
    const [gpsSource, setGpsSource] = useState<'detecting' | 'browser' | 'profile' | 'unavailable'>('detecting')
    const [poolModal, setPoolModal] = useState<string | null>(null)

    // Fetch NGO profile to get stored coordinates
    const { data: ngoProfile } = useQuery({
        queryKey: ['my-profile'],
        queryFn: () => api.getMyProfile(),
    })

    // Auto-detect GPS, then fall back to stored registration coordinates
    useEffect(() => {
        if (!navigator.geolocation) {
            // No browser GPS — use stored coordinates if available
            if (ngoProfile?.latitude && ngoProfile?.longitude) {
                setGps({ lat: Number(ngoProfile.latitude), lng: Number(ngoProfile.longitude) })
                setGpsSource('profile')
            } else {
                setGpsSource('unavailable')
            }
            return
        }
        navigator.geolocation.getCurrentPosition(
            pos => {
                setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude })
                setGpsSource('browser')
            },
            () => {
                // Browser GPS failed — fall back to stored coordinates
                if (ngoProfile?.latitude && ngoProfile?.longitude) {
                    setGps({ lat: Number(ngoProfile.latitude), lng: Number(ngoProfile.longitude) })
                    setGpsSource('profile')
                } else {
                    setGpsSource('unavailable')
                }
            },
            { enableHighAccuracy: true, timeout: 10000 }
        )
    }, [ngoProfile])

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-fulfillment', page, priorityFilter, sortBy, gps?.lat, gps?.lng],
        queryFn: () => api.getNgoAvailableRequests({
            limit: 20,
            offset: (page - 1) * 20,
            priority: priorityFilter || undefined,
            ngo_latitude: gps?.lat,
            ngo_longitude: gps?.lng,
            sort: sortBy,
        }),
    })

    // Realtime
    useEffect(() => {
        const unsub = subscribeToTable('resource_requests', () => {
            qc.invalidateQueries({ queryKey: ['ngo-fulfillment'] })
        })
        return () => { unsub() }
    }, [qc])

    const requests = data?.requests || []
    const total = data?.total || 0
    const totalPages = Math.max(1, Math.ceil(total / 20))

    const { data: poolData } = useQuery({
        queryKey: ['ngo-request-pool', poolModal],
        queryFn: () => poolModal ? api.getNgoRequestPool(poolModal) : null,
        enabled: !!poolModal,
    })

    const filtered = search
        ? requests.filter((r: any) => {
            const term = search.toLowerCase()
            return [r.id, r.description, r.resource_type, r.victim_name, r.address_text, r.victim_email]
                .filter(Boolean).some(f => f.toLowerCase().includes(term))
        })
        : requests

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <span className="text-sm text-slate-500">Loading approved requests...</span>
            </div>
        )
    }

    const gpsLabel = gpsSource === 'browser' ? 'Live GPS'
        : gpsSource === 'profile' ? 'Registered Address'
        : gpsSource === 'detecting' ? 'Detecting…'
        : 'Location Unavailable'

    const gpsColor = gpsSource === 'browser' ? 'bg-green-100 dark:bg-green-500/10 text-green-600'
        : gpsSource === 'profile' ? 'bg-blue-100 dark:bg-blue-500/10 text-blue-600'
        : gpsSource === 'detecting' ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-600'
        : 'bg-red-100 dark:bg-red-500/10 text-red-500'

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <CheckCircle2 className="w-6 h-6 text-blue-500" />
                        Approved Requests
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        View admin-approved requests and submit your availability to fulfill them.
                    </p>
                </div>
                <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Search by resource, victim, location..."
                        className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <div className="flex gap-2">
                    {['', 'critical', 'high', 'medium', 'low'].map(p => (
                        <button key={p} onClick={() => { setPriorityFilter(p); setPage(1) }}
                            className={cn(
                                'px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all border',
                                priorityFilter === p
                                    ? 'bg-blue-600 text-white border-blue-600'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5'
                            )}>
                            {p === '' ? 'All' : p.charAt(0).toUpperCase() + p.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {/* Sort + GPS */}
            <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs font-medium text-slate-500">Sort:</span>
                {(['priority', 'distance'] as const).map(s => (
                    <button key={s} onClick={() => setSortBy(s)} disabled={s === 'distance' && !gps}
                        className={cn('px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
                            sortBy === s ? 'bg-cyan-600 text-white border-cyan-600' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5',
                            s === 'distance' && !gps && 'opacity-40 cursor-not-allowed'
                        )}>
                        {s === 'priority' ? 'By Priority' : 'By Distance'}
                    </button>
                ))}
                <span className={cn('ml-auto text-[10px] font-medium px-2.5 py-1 rounded-full flex items-center gap-1', gpsColor)}>
                    {gpsSource === 'profile' ? <Building2 className="w-3 h-3" /> : <Navigation className="w-3 h-3" />}
                    {gpsLabel}
                </span>
            </div>

            {/* Results Count */}
            <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">{total} approved request{total !== 1 ? 's' : ''} available</p>
            </div>

            {/* Request Cards */}
            {filtered.length === 0 ? (
                <div className="text-center py-16">
                    <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">No approved requests available</p>
                    <p className="text-sm text-slate-400 mt-1">Requests will appear here after admin approval.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {filtered.map((req: any) => (
                        <div key={req.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg transition-all duration-300 group">
                            <div className="flex items-start gap-4">
                                <div className={cn('w-3 h-3 rounded-full mt-1.5 shrink-0', PRIORITY_DOT[req.priority] || 'bg-slate-400')} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap mb-1">
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                            {req.resource_type || 'Resource Request'}
                                        </h3>
                                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset',
                                            req.status === 'under_review'
                                                ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 ring-amber-500/20'
                                                : 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 ring-blue-500/20')}>
                                            {req.status === 'under_review' ? 'Under Review' : req.status === 'availability_submitted' ? 'Availability Submitted' : 'Approved'}
                                        </span>
                                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset capitalize',
                                            PRIORITY_BADGE[req.priority] || '')}>
                                            {req.priority}
                                        </span>
                                        {req.availability_submitted && (
                                            <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold bg-purple-100 dark:bg-purple-500/10 text-purple-600 ring-1 ring-inset ring-purple-500/20">
                                                ✓ Availability Sent
                                            </span>
                                        )}
                                    </div>

                                    {req.description && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mb-2">{req.description}</p>
                                    )}

                                    <div className="flex items-center gap-4 text-xs text-slate-400 flex-wrap">
                                        {req.victim_name && (
                                            <span className="flex items-center gap-1">
                                                <User className="w-3 h-3" /> {req.victim_name}
                                            </span>
                                        )}
                                        {req.address_text && (
                                            <span className="flex items-center gap-1">
                                                <MapPin className="w-3 h-3" /> {req.address_text}
                                            </span>
                                        )}
                                        {req.latitude && req.longitude && (
                                            <span className="flex items-center gap-1 text-blue-500">
                                                <Navigation className="w-3 h-3" /> {req.latitude.toFixed(4)}, {req.longitude.toFixed(4)}
                                            </span>
                                        )}
                                        <span>Qty: {req.quantity || 1}</span>
                                        <span className="flex items-center gap-1">
                                            <Calendar className="w-3 h-3" /> {new Date(req.created_at).toLocaleDateString()}
                                        </span>
                                    </div>

                                    {req.distance_km !== null && req.distance_km !== undefined && (
                                        <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-500/10 px-2.5 py-1 rounded-lg">
                                            <Navigation className="w-3 h-3" /> {req.distance_km} km from your location
                                        </div>
                                    )}

                                    {req.fulfillment_pct != null && req.fulfillment_pct > 0 && (
                                        <div className="mt-2">
                                            <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                                                <span>Fulfilled</span>
                                                <span className="font-semibold">{req.fulfillment_pct}%</span>
                                            </div>
                                            <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                                                <div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-green-500 transition-all" style={{ width: `${Math.min(req.fulfillment_pct, 100)}%` }} />
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="flex flex-col items-end gap-2 shrink-0">
                                    <span className="text-[10px] text-slate-400 font-mono">{req.id?.slice(0, 8)}</span>
                                    <div className="flex gap-2">
                                        {(req.fulfillment_pct > 0 || req.fulfillment_entries?.length > 0) && (
                                            <button
                                                onClick={() => setPoolModal(req.id)}
                                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-blue-200 dark:border-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors">
                                                <Users className="w-3 h-3" /> Pool
                                            </button>
                                        )}
                                        <button
                                            onClick={() => setSelectedRequest(selectedRequest?.id === req.id ? null : req)}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                                            <Eye className="w-3 h-3" /> Details
                                        </button>
                                        <button
                                            onClick={() => setShowAvailabilityModal(req)}
                                            disabled={req.availability_submitted}
                                            className={cn(
                                                'flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                                                req.availability_submitted
                                                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                                                    : 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white hover:from-blue-700 hover:to-cyan-700 shadow-sm'
                                            )}>
                                            <Send className="w-3 h-3" /> {req.availability_submitted ? 'Submitted' : 'Submit Availability'}
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* Expanded Details */}
                            {selectedRequest?.id === req.id && (
                                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-white/5 grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Request ID</p>
                                        <p className="font-mono text-slate-700 dark:text-slate-300">{req.id}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Victim Contact</p>
                                        <p className="text-slate-700 dark:text-slate-300">{req.victim_email || req.victim_phone || 'N/A'}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Resource Type</p>
                                        <p className="text-slate-700 dark:text-slate-300 capitalize">{req.resource_type}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Quantity Needed</p>
                                        <p className="text-slate-700 dark:text-slate-300 font-semibold">{req.quantity}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">GPS Location</p>
                                        <p className="text-slate-700 dark:text-slate-300">
                                            {req.latitude && req.longitude ? `${req.latitude.toFixed(6)}, ${req.longitude.toFixed(6)}` : 'Not available'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Distance</p>
                                        <p className="text-slate-700 dark:text-slate-300 font-semibold">
                                            {req.distance_km !== null ? `${req.distance_km} km` : 'N/A'}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Address</p>
                                        <p className="text-slate-700 dark:text-slate-300">{req.address_text || 'Not provided'}</p>
                                    </div>
                                    <div>
                                        <p className="text-slate-400 mb-0.5">Created</p>
                                        <p className="text-slate-700 dark:text-slate-300">{new Date(req.created_at).toLocaleString()}</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-500">Page {page} of {totalPages} ({total} total)</p>
                    <div className="flex gap-2">
                        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-white/5">
                            <ChevronLeft className="w-3.5 h-3.5" /> Previous
                        </button>
                        <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-white/5">
                            Next <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            )}

            {/* Availability Modal */}
            {showAvailabilityModal && (
                <SubmitAvailabilityModal
                    request={showAvailabilityModal}
                    onClose={() => setShowAvailabilityModal(null)}
                />
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
                            <p className="text-sm text-slate-500 text-center py-6">No contributors yet. Be the first to submit availability!</p>
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
