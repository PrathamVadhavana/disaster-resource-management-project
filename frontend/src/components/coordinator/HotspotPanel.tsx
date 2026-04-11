'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    MapPin, Loader2, RefreshCw, AlertTriangle, Users, Filter,
    ChevronDown, X, Send, Package, Eye, FileText, Zap, Shield,
    TrendingUp, Activity, Clock, CheckCircle2, Bell, Layers,
    Target, BarChart3, ArrowRight, Sparkles, ExternalLink
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Types ────────────────────────────────────────────────────────────────────

interface ClusterData {
    cluster_id: string
    priority: string
    event_count: number
    total_people: number
    dominant_type: string
    avg_severity: number
    centroid: { lat: number; lng: number } | null
    detected_at: string
    boundary: any
    request_ids?: string[]
}

interface Insight {
    summary: string
    risk_score: number
    risk_level: string
    resource_breakdown: { type: string; count: number }[]
    priority_breakdown: { priority: string; count: number }[]
    recommendations: { action: string; title: string; description: string; urgency: string }[]
    stats: any
}

// ── Constants ────────────────────────────────────────────────────────────────

const PRIORITY_CONFIG: Record<string, { bg: string; text: string; dot: string; border: string; glow: string }> = {
    critical: {
        bg: 'bg-red-50 dark:bg-red-500/10',
        text: 'text-red-700 dark:text-red-400',
        dot: 'bg-red-500',
        border: 'border-red-200 dark:border-red-500/20',
        glow: 'shadow-red-500/10',
    },
    high: {
        bg: 'bg-orange-50 dark:bg-orange-500/10',
        text: 'text-orange-700 dark:text-orange-400',
        dot: 'bg-orange-500',
        border: 'border-orange-200 dark:border-orange-500/20',
        glow: 'shadow-orange-500/10',
    },
    medium: {
        bg: 'bg-yellow-50 dark:bg-yellow-500/10',
        text: 'text-yellow-700 dark:text-yellow-400',
        dot: 'bg-yellow-500',
        border: 'border-yellow-200 dark:border-yellow-500/20',
        glow: 'shadow-yellow-500/10',
    },
    low: {
        bg: 'bg-green-50 dark:bg-green-500/10',
        text: 'text-green-700 dark:text-green-400',
        dot: 'bg-green-500',
        border: 'border-green-200 dark:border-green-500/20',
        glow: 'shadow-green-500/10',
    },
}

const RESOURCE_ICONS: Record<string, string> = {
    Food: '🍲',
    Water: '💧',
    Medical: '🏥',
    Shelter: '🏠',
    Clothing: '👕',
    Evacuation: '🚁',
    Volunteers: '🙋',
    'Financial Aid': '💰',
    Custom: '📦',
    Multiple: '📋',
}

// ── Helper functions ─────────────────────────────────────────────────────────

function parseClusters(hotspots: any): ClusterData[] {
    if (!hotspots) return []
    const raw = hotspots?.features
        ? hotspots.features.map((f: any) => {
            const p = f.properties || {}
            const coords = p.centroid?.coordinates || f.geometry?.coordinates
            return {
                cluster_id: p.id ?? p.cluster_id ?? f.id,
                priority: p.priority_label || p.priority || 'medium',
                event_count: p.request_count ?? p.event_count ?? p.size ?? 0,
                total_people: p.total_people ?? 0,
                dominant_type: p.dominant_type ?? 'Unknown',
                avg_severity: p.avg_priority ?? p.avg_severity ?? 0,
                centroid: coords ? { lat: coords[1], lng: coords[0] } : null,
                detected_at: p.detected_at ?? '',
                boundary: f.geometry,
                request_ids: p.request_ids,
            }
        })
        : Array.isArray(hotspots) ? hotspots : hotspots?.clusters || []
    return raw
}

function timeAgo(dateStr: string): string {
    if (!dateStr) return ''
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function HotspotPanel({ selectedDisasterId }: { selectedDisasterId?: string | null }) {
    const qc = useQueryClient()
    const [priorityFilter, setPriorityFilter] = useState<string>('all')
    const [showFilterDropdown, setShowFilterDropdown] = useState(false)
    const [autoRefresh, setAutoRefresh] = useState(true)

    // Modal state
    const [selectedCluster, setSelectedCluster] = useState<ClusterData | null>(null)
    const [modalMode, setModalMode] = useState<'detail' | 'map' | 'assign' | 'alert' | null>(null)

    // Assign form state
    const [assignForm, setAssignForm] = useState({ resource_type: 'Food', quantity: 1, notes: '' })

    // Alert form state
    const [alertForm, setAlertForm] = useState({ channel: 'in_app', recipient_role: 'ngo', severity: 'high', subject: '', body: '' })

    // ── Queries ──────────────────────────────────────────────────────────────

    const { data: hotspots, isLoading, refetch } = useQuery({
        queryKey: ['hotspots', selectedDisasterId, priorityFilter],
        queryFn: () => {
            const params: any = {}
            if (priorityFilter !== 'all') params.min_priority = priorityFilter
            return selectedDisasterId
                ? api.getDisasterHotspots(selectedDisasterId)
                : api.getHotspots(params)
        },
        retry: false,
        refetchInterval: autoRefresh ? 30000 : false,
    })

    const { data: insights, isLoading: insightsLoading } = useQuery({
        queryKey: ['hotspot-insights', selectedCluster?.cluster_id],
        queryFn: () => selectedCluster ? api.getHotspotInsights(selectedCluster.cluster_id) : null,
        enabled: !!selectedCluster && modalMode === 'detail',
        retry: false,
    })

    // ── Mutations ────────────────────────────────────────────────────────────

    const triggerMutation = useMutation({
        mutationFn: () => api.triggerClustering(),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['hotspots'] })
        },
    })

    const assignMutation = useMutation({
        mutationFn: (data: { clusterId: string; resource_type: string; quantity: number; notes?: string }) =>
            api.assignHotspotResources(data.clusterId, { resource_type: data.resource_type, quantity: data.quantity, notes: data.notes }),
        onSuccess: (data: any) => {
            setModalMode(null)
            setSelectedCluster(null)
            setAssignForm({ resource_type: 'Food', quantity: 1, notes: '' })
            qc.invalidateQueries({ queryKey: ['hotspots'] })
            qc.invalidateQueries({ queryKey: ['admin-requests'] })
        },
    })

    const alertMutation = useMutation({
        mutationFn: (data: { clusterId: string; channel: string; recipient_role: string; severity: string; subject?: string; body?: string }) =>
            api.sendHotspotAlert(data.clusterId, {
                channel: data.channel,
                recipient_role: data.recipient_role,
                severity: data.severity,
                subject: data.subject,
                body: data.body,
            }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notifications'] })
            qc.invalidateQueries({ queryKey: ['hotspots'] })
            setModalMode(null)
            setSelectedCluster(null)
        },
    })

    const statusMutation = useMutation({
        mutationFn: (data: { clusterId: string; status: string }) =>
            api.updateHotspotStatus(data.clusterId, data.status),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['hotspots'] })
        },
    })

    // ── Derived data ─────────────────────────────────────────────────────────

    const clusters = parseClusters(hotspots)
    const totalPeople = clusters.reduce((s, c) => s + (c.total_people || 0), 0)
    const criticalCount = clusters.filter(c => c.priority === 'critical' || c.priority === 'high').length
    const totalEvents = clusters.reduce((s, c) => s + (c.event_count || 0), 0)

    // ── Handler helpers ──────────────────────────────────────────────────────

    const openModal = (cluster: ClusterData, mode: 'detail' | 'map' | 'assign' | 'alert') => {
        setSelectedCluster(cluster)
        setModalMode(mode)
    }

    const closeModal = () => {
        setSelectedCluster(null)
        setModalMode(null)
    }

    // ── Render ────────────────────────────────────────────────────────────────

    return (
        <div className="space-y-5">
            {/* ── KPI Summary ──────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                    { label: 'Active Hotspots', value: clusters.length, icon: Target, color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-500/10' },
                    { label: 'Critical / High', value: criticalCount, icon: AlertTriangle, color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-50 dark:bg-orange-500/10' },
                    { label: 'People Affected', value: totalPeople, icon: Users, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-500/10' },
                    { label: 'Total Events', value: totalEvents, icon: Activity, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-500/10' },
                ].map((kpi) => (
                    <div key={kpi.label} className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/2 p-4">
                        <div className="flex items-center gap-2 mb-2">
                            <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", kpi.bg)}>
                                <kpi.icon className={cn("w-4 h-4", kpi.color)} />
                            </div>
                        </div>
                        <p className="text-2xl font-black text-slate-900 dark:text-white tabular-nums">{kpi.value}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{kpi.label}</p>
                    </div>
                ))}
            </div>

            {/* ── Action Bar ───────────────────────────────────────────────── */}
            <div className="flex flex-wrap items-center gap-2">
                <button
                    onClick={() => triggerMutation.mutate()}
                    disabled={triggerMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-linear-to-r from-red-600 to-orange-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-red-600/20 transition-all"
                >
                    {triggerMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                    {triggerMutation.isPending ? 'Clustering...' : 'Re-Cluster Now'}
                </button>

                <button
                    onClick={() => refetch()}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Refresh
                </button>

                {/* Priority filter */}
                <div className="relative">
                    <button
                        onClick={() => setShowFilterDropdown(!showFilterDropdown)}
                        className={cn(
                            "flex items-center gap-1.5 px-3 py-2 rounded-xl border text-sm transition-colors",
                            priorityFilter !== 'all'
                                ? "bg-purple-50 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20 text-purple-700 dark:text-purple-400"
                                : "border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                        )}
                    >
                        <Filter className="w-3.5 h-3.5" />
                        {priorityFilter === 'all' ? 'All Priorities' : priorityFilter.charAt(0).toUpperCase() + priorityFilter.slice(1) + '+'}
                        <ChevronDown className="w-3 h-3" />
                    </button>
                    {showFilterDropdown && (
                        <>
                            <div className="fixed inset-0 z-10" onClick={() => setShowFilterDropdown(false)} />
                            <div className="absolute left-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-xl z-20 py-1 min-w-37.5">
                                {['all', 'low', 'medium', 'high', 'critical'].map(p => (
                                    <button
                                        key={p}
                                        onClick={() => { setPriorityFilter(p); setShowFilterDropdown(false) }}
                                        className={cn(
                                            "flex items-center gap-2 w-full px-4 py-2 text-sm text-left transition-colors capitalize",
                                            priorityFilter === p
                                                ? "bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400"
                                                : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                                        )}
                                    >
                                        {p !== 'all' && <div className={cn("w-2 h-2 rounded-full", PRIORITY_CONFIG[p]?.dot || 'bg-slate-400')} />}
                                        {p === 'all' ? 'All Priorities' : `${p}+`}
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                </div>

                {/* Auto-refresh toggle */}
                <label className="flex items-center gap-2 ml-auto cursor-pointer select-none">
                    <span className="text-xs text-slate-400">Auto-refresh</span>
                    <div
                        onClick={() => setAutoRefresh(!autoRefresh)}
                        className={cn(
                            "w-8 h-4.5 rounded-full transition-colors relative cursor-pointer",
                            autoRefresh ? "bg-green-500" : "bg-slate-300 dark:bg-slate-600"
                        )}
                        style={{ height: '18px' }}
                    >
                        <div className={cn(
                            "absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white shadow transition-transform",
                            autoRefresh ? "translate-x-4" : "translate-x-0.5"
                        )} style={{ width: '14px', height: '14px' }} />
                    </div>
                </label>

                {triggerMutation.isSuccess && (
                    <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        {(triggerMutation.data as any)?.message || 'Done'}
                    </span>
                )}
            </div>

            {/* ── Cluster Cards ─────────────────────────────────────────────── */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/2 overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center gap-2">
                    <MapPin className="w-5 h-5 text-red-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Hotspot Clusters</h3>
                    <span className="text-xs text-slate-400 ml-1">DBSCAN-based spatial clustering of disaster events</span>
                </div>

                {isLoading ? (
                    <div className="py-16 text-center">
                        <Loader2 className="w-8 h-8 animate-spin text-red-500 mx-auto mb-3" />
                        <p className="text-sm text-slate-500">Computing hotspot clusters...</p>
                    </div>
                ) : clusters.length === 0 ? (
                    <div className="py-16 text-center">
                        <div className="w-16 h-16 rounded-2xl bg-slate-100 dark:bg-white/5 flex items-center justify-center mx-auto mb-4">
                            <MapPin className="w-8 h-8 text-slate-300 dark:text-slate-600" />
                        </div>
                        <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-1">No hotspot clusters detected</p>
                        <p className="text-xs text-slate-400 dark:text-slate-500">Try triggering a re-cluster or ensure disaster data is seeded</p>
                        <button
                            onClick={() => triggerMutation.mutate()}
                            disabled={triggerMutation.isPending}
                            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-sm font-medium hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                        >
                            <Zap className="w-4 h-4" />
                            Run Clustering
                        </button>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {clusters.map((cluster, i) => {
                            const config = PRIORITY_CONFIG[cluster.priority] || PRIORITY_CONFIG.medium
                            const icon = RESOURCE_ICONS[cluster.dominant_type] || '📦'
                            return (
                                <div key={cluster.cluster_id || i} className="p-4 hover:bg-slate-50/50 dark:hover:bg-white/1 transition-colors">
                                    {/* Card Header */}
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex items-center gap-3 min-w-0">
                                            <div className={cn("w-3 h-3 rounded-full shrink-0 ring-2 ring-offset-2 dark:ring-offset-slate-900", config.dot, `ring-${cluster.priority === 'critical' ? 'red' : cluster.priority === 'high' ? 'orange' : cluster.priority === 'medium' ? 'yellow' : 'green'}-200 dark:ring-${cluster.priority === 'critical' ? 'red' : cluster.priority === 'high' ? 'orange' : cluster.priority === 'medium' ? 'yellow' : 'green'}-500/20`)} />
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="text-sm font-bold text-slate-900 dark:text-white">
                                                        Cluster #{(cluster.cluster_id || '').slice(0, 8)}
                                                    </span>
                                                    <span className={cn(
                                                        "text-[10px] px-2 py-0.5 rounded-full font-bold uppercase",
                                                        config.bg, config.text
                                                    )}>
                                                        {cluster.priority}
                                                    </span>
                                                </div>
                                                {cluster.detected_at && (
                                                    <p className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                                                        <Clock className="w-3 h-3" />
                                                        Detected {timeAgo(cluster.detected_at)}
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="text-right shrink-0">
                                            <span className="text-lg font-black text-slate-900 dark:text-white tabular-nums">{cluster.event_count}</span>
                                            <p className="text-[10px] text-slate-400 uppercase tracking-wider">Events</p>
                                        </div>
                                    </div>

                                    {/* Card Details */}
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 ml-6">
                                        {cluster.centroid && (
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Centroid</p>
                                                <p className="text-xs text-slate-700 dark:text-slate-300 tabular-nums">
                                                    {cluster.centroid.lat?.toFixed(4)}, {cluster.centroid.lng?.toFixed(4)}
                                                </p>
                                            </div>
                                        )}
                                        <div>
                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Avg Severity</p>
                                            <p className="text-xs text-slate-700 dark:text-slate-300 tabular-nums">{(cluster.avg_severity || 0).toFixed(2)} / 4.0</p>
                                        </div>
                                        <div>
                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Resource Type</p>
                                            <p className="text-xs text-slate-700 dark:text-slate-300 flex items-center gap-1">
                                                <span>{icon}</span> {cluster.dominant_type}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">People</p>
                                            <p className="text-xs text-slate-700 dark:text-slate-300 tabular-nums font-semibold">{cluster.total_people}</p>
                                        </div>
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="flex flex-wrap gap-2 mt-3 ml-6">
                                        <button
                                            onClick={() => openModal(cluster, 'map')}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                                        >
                                            <Eye className="w-3.5 h-3.5" />
                                            View on Map
                                        </button>
                                        <button
                                            onClick={() => openModal(cluster, 'assign')}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-blue-200 dark:border-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors"
                                        >
                                            <Package className="w-3.5 h-3.5" />
                                            Assign Resources
                                        </button>
                                        <button
                                            onClick={() => openModal(cluster, 'alert')}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-orange-200 dark:border-orange-500/20 text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-500/10 transition-colors"
                                        >
                                            <Bell className="w-3.5 h-3.5" />
                                            Send Alert
                                        </button>
                                        <button
                                            onClick={() => openModal(cluster, 'detail')}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-purple-200 dark:border-purple-500/20 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10 transition-colors"
                                        >
                                            <Sparkles className="w-3.5 h-3.5" />
                                            AI Insights
                                        </button>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>

            {/* ══════════════════════════════════════════════════════════════════
               MODALS
               ══════════════════════════════════════════════════════════════════ */}

            {modalMode && selectedCluster && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeModal} />

                    {/* ── Detail / AI Insights Modal ──────────────────────────── */}
                    {modalMode === 'detail' && (
                        <div className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10">
                            <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-white/10 px-6 py-4 flex items-center justify-between z-10">
                                <div className="flex items-center gap-3">
                                    <div className={cn("w-3 h-3 rounded-full", PRIORITY_CONFIG[selectedCluster.priority]?.dot || 'bg-slate-400')} />
                                    <h3 className="font-bold text-slate-900 dark:text-white">Cluster #{(selectedCluster.cluster_id || '').slice(0, 8)}</h3>
                                    <span className={cn(
                                        "text-[10px] px-2 py-0.5 rounded-full font-bold uppercase",
                                        PRIORITY_CONFIG[selectedCluster.priority]?.bg,
                                        PRIORITY_CONFIG[selectedCluster.priority]?.text
                                    )}>
                                        {selectedCluster.priority}
                                    </span>
                                </div>
                                <button onClick={closeModal} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                    <X className="w-5 h-5 text-slate-500" />
                                </button>
                            </div>

                            <div className="p-6 space-y-6">
                                {/* Cluster Stats */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Events</p>
                                        <p className="text-xl font-black text-slate-900 dark:text-white">{selectedCluster.event_count}</p>
                                    </div>
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">People</p>
                                        <p className="text-xl font-black text-slate-900 dark:text-white">{selectedCluster.total_people}</p>
                                    </div>
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Severity</p>
                                        <p className="text-xl font-black text-slate-900 dark:text-white">{(selectedCluster.avg_severity || 0).toFixed(1)}</p>
                                    </div>
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Resource</p>
                                        <p className="text-sm font-bold text-slate-900 dark:text-white">{RESOURCE_ICONS[selectedCluster.dominant_type] || '📦'} {selectedCluster.dominant_type}</p>
                                    </div>
                                </div>

                                {/* AI Insights */}
                                <div>
                                    <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2 mb-3">
                                        <Sparkles className="w-4 h-4 text-purple-500" />
                                        AI Intelligence & Recommendations
                                    </h4>
                                    {insightsLoading ? (
                                        <div className="rounded-xl border border-purple-200 dark:border-purple-500/20 bg-purple-50/50 dark:bg-purple-500/5 p-6 text-center">
                                            <Loader2 className="w-5 h-5 animate-spin text-purple-500 mx-auto mb-2" />
                                            <p className="text-xs text-slate-500">Analyzing hotspot data...</p>
                                        </div>
                                    ) : insights ? (
                                        <div className="space-y-4">
                                            {/* Risk Score */}
                                            <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/2 p-4">
                                                <div className="flex items-center justify-between mb-2">
                                                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Risk Score</p>
                                                    <span className={cn(
                                                        "text-xs px-2 py-0.5 rounded-full font-bold uppercase",
                                                        (insights as Insight).risk_level === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                                            (insights as Insight).risk_level === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                                                'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                                                    )}>
                                                        {(insights as Insight).risk_level}
                                                    </span>
                                                </div>
                                                <div className="flex items-end gap-2">
                                                    <span className="text-3xl font-black text-slate-900 dark:text-white">{(insights as Insight).risk_score}</span>
                                                    <span className="text-sm text-slate-400 mb-1">/ 100</span>
                                                </div>
                                                <div className="mt-2 w-full bg-slate-200 dark:bg-white/10 rounded-full h-2 overflow-hidden">
                                                    <div
                                                        className={cn(
                                                            "h-full rounded-full transition-all",
                                                            (insights as Insight).risk_score >= 75 ? 'bg-red-500' :
                                                                (insights as Insight).risk_score >= 50 ? 'bg-orange-500' :
                                                                    (insights as Insight).risk_score >= 25 ? 'bg-yellow-500' : 'bg-green-500'
                                                        )}
                                                        style={{ width: `${(insights as Insight).risk_score}%` }}
                                                    />
                                                </div>
                                                <p className="text-xs text-slate-500 mt-2">{(insights as Insight).summary}</p>
                                            </div>

                                            {/* Resource Breakdown */}
                                            {(insights as Insight).resource_breakdown?.length > 0 && (
                                                <div className="rounded-xl border border-slate-200 dark:border-white/10 p-4">
                                                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Resource Breakdown</p>
                                                    <div className="space-y-2">
                                                        {(insights as Insight).resource_breakdown.map((rb: any) => (
                                                            <div key={rb.type} className="flex items-center justify-between">
                                                                <span className="text-xs text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
                                                                    {RESOURCE_ICONS[rb.type] || '📦'} {rb.type}
                                                                </span>
                                                                <div className="flex items-center gap-2">
                                                                    <div className="w-20 bg-slate-100 dark:bg-white/10 rounded-full h-1.5">
                                                                        <div className="h-full bg-purple-500 rounded-full" style={{ width: `${Math.min(100, (rb.count / selectedCluster.event_count) * 100)}%` }} />
                                                                    </div>
                                                                    <span className="text-xs font-bold text-slate-900 dark:text-white tabular-nums w-6 text-right">{rb.count}</span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Recommendations */}
                                            {(insights as Insight).recommendations?.length > 0 && (
                                                <div>
                                                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Recommendations</p>
                                                    <div className="space-y-2">
                                                        {(insights as Insight).recommendations.map((rec: any, idx: number) => (
                                                            <div
                                                                key={idx}
                                                                className={cn(
                                                                    "rounded-xl border p-4",
                                                                    rec.urgency === 'critical' ? 'border-red-200 dark:border-red-500/20 bg-red-50/50 dark:bg-red-500/5' :
                                                                        rec.urgency === 'high' ? 'border-orange-200 dark:border-orange-500/20 bg-orange-50/50 dark:bg-orange-500/5' :
                                                                            'border-slate-200 dark:border-white/10 bg-slate-50/50 dark:bg-white/2'
                                                                )}
                                                            >
                                                                <div className="flex items-center gap-2 mb-1">
                                                                    <Shield className={cn(
                                                                        "w-4 h-4",
                                                                        rec.urgency === 'critical' ? 'text-red-500' :
                                                                            rec.urgency === 'high' ? 'text-orange-500' : 'text-slate-400'
                                                                    )} />
                                                                    <p className="text-sm font-bold text-slate-900 dark:text-white">{rec.title}</p>
                                                                </div>
                                                                <p className="text-xs text-slate-500 dark:text-slate-400 ml-6">{rec.description}</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <p className="text-xs text-slate-500">No insights available</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── Map Modal ───────────────────────────────────────────── */}
                    {modalMode === 'map' && (
                        <div className="relative w-full max-w-3xl max-h-[85vh] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10 overflow-hidden">
                            <div className="border-b border-slate-200 dark:border-white/10 px-6 py-4 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Eye className="w-5 h-5 text-blue-500" />
                                    <h3 className="font-bold text-slate-900 dark:text-white">Hotspot Map — Cluster #{(selectedCluster.cluster_id || '').slice(0, 8)}</h3>
                                </div>
                                <button onClick={closeModal} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                    <X className="w-5 h-5 text-slate-500" />
                                </button>
                            </div>
                            <div className="p-6">
                                <HotspotMapEmbed cluster={selectedCluster} />
                                <div className="mt-4 grid grid-cols-3 gap-3">
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3 text-center">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase">Centroid</p>
                                        <p className="text-xs text-slate-700 dark:text-slate-300 tabular-nums mt-1">
                                            {selectedCluster.centroid ? `${selectedCluster.centroid.lat.toFixed(4)}, ${selectedCluster.centroid.lng.toFixed(4)}` : 'N/A'}
                                        </p>
                                    </div>
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3 text-center">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase">Events</p>
                                        <p className="text-lg font-black text-slate-900 dark:text-white mt-0.5">{selectedCluster.event_count}</p>
                                    </div>
                                    <div className="rounded-xl bg-slate-50 dark:bg-white/5 p-3 text-center">
                                        <p className="text-[10px] font-bold text-slate-400 uppercase">Priority</p>
                                        <p className={cn(
                                            "text-sm font-bold mt-0.5 uppercase",
                                            PRIORITY_CONFIG[selectedCluster.priority]?.text
                                        )}>{selectedCluster.priority}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── Assign Resources Modal ─────────────────────────────── */}
                    {modalMode === 'assign' && (
                        <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10">
                            <div className="border-b border-slate-200 dark:border-white/10 px-6 py-4 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Package className="w-5 h-5 text-blue-500" />
                                    <h3 className="font-bold text-slate-900 dark:text-white">Assign Resources</h3>
                                </div>
                                <button onClick={closeModal} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                    <X className="w-5 h-5 text-slate-500" />
                                </button>
                            </div>
                            <div className="p-6 space-y-4">
                                <div className="rounded-xl bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 p-3">
                                    <p className="text-xs text-blue-700 dark:text-blue-400">
                                        Assigning to <strong>Cluster #{(selectedCluster.cluster_id || '').slice(0, 8)}</strong> — {selectedCluster.event_count} events, {selectedCluster.total_people} people affected
                                    </p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Resource Type</label>
                                    <select
                                        value={assignForm.resource_type}
                                        onChange={e => setAssignForm(f => ({ ...f, resource_type: e.target.value }))}
                                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
                                    >
                                        {['Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Financial Aid', 'Evacuation', 'Volunteers'].map(t => (
                                            <option key={t} value={t}>{RESOURCE_ICONS[t] || '📦'} {t}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Quantity</label>
                                    <input
                                        type="number"
                                        min={1}
                                        value={assignForm.quantity}
                                        onChange={e => setAssignForm(f => ({ ...f, quantity: parseInt(e.target.value) || 1 }))}
                                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Notes (optional)</label>
                                    <textarea
                                        value={assignForm.notes}
                                        onChange={e => setAssignForm(f => ({ ...f, notes: e.target.value }))}
                                        rows={2}
                                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white resize-none"
                                        placeholder="Additional details..."
                                    />
                                </div>
                                <button
                                    onClick={() => assignMutation.mutate({
                                        clusterId: selectedCluster.cluster_id,
                                        resource_type: assignForm.resource_type,
                                        quantity: assignForm.quantity,
                                        notes: assignForm.notes || undefined,
                                    })}
                                    disabled={assignMutation.isPending}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-linear-to-r from-blue-600 to-cyan-600 text-white font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-blue-600/20"
                                >
                                    {assignMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Package className="w-4 h-4" />}
                                    {assignMutation.isPending ? 'Assigning...' : 'Assign Resources'}
                                </button>
                                {assignMutation.isError && (
                                    <p className="text-xs text-red-500 text-center">{(assignMutation.error as any)?.message || 'Assignment failed'}</p>
                                )}
                            </div>
                        </div>
                    )}

                    {/* ── Send Alert Modal ────────────────────────────────────── */}
                    {modalMode === 'alert' && (
                        <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-white/10">
                            <div className="border-b border-slate-200 dark:border-white/10 px-6 py-4 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Bell className="w-5 h-5 text-orange-500" />
                                    <h3 className="font-bold text-slate-900 dark:text-white">Send Alert</h3>
                                </div>
                                <button onClick={closeModal} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                    <X className="w-5 h-5 text-slate-500" />
                                </button>
                            </div>
                            <div className="p-6 space-y-4">
                                <div className="rounded-xl bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 p-3">
                                    <p className="text-xs text-orange-700 dark:text-orange-400">
                                        Alert for <strong>Cluster #{(selectedCluster.cluster_id || '').slice(0, 8)}</strong> — {selectedCluster.priority.toUpperCase()} priority, {selectedCluster.dominant_type} needs
                                    </p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Recipient Role</label>
                                    <div className="grid grid-cols-3 gap-2">
                                        {['ngo', 'volunteer', 'admin'].map(role => (
                                            <button
                                                key={role}
                                                onClick={() => setAlertForm(f => ({ ...f, recipient_role: role }))}
                                                className={cn(
                                                    "px-3 py-2 rounded-lg text-sm font-medium border transition-all capitalize",
                                                    alertForm.recipient_role === role
                                                        ? "bg-orange-600 text-white border-orange-600"
                                                        : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-white/10 hover:border-orange-300"
                                                )}
                                            >
                                                {role === 'ngo' ? 'NGOs' : role === 'volunteer' ? 'Volunteers' : 'Admins'}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Channel</label>
                                    <select
                                        value={alertForm.channel}
                                        onChange={e => setAlertForm(f => ({ ...f, channel: e.target.value }))}
                                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white"
                                    >
                                        <option value="in_app">In-App Notification</option>
                                        <option value="email">Email</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Severity</label>
                                    <div className="grid grid-cols-4 gap-1">
                                        {['low', 'medium', 'high', 'critical'].map(s => (
                                            <button
                                                key={s}
                                                onClick={() => setAlertForm(f => ({ ...f, severity: s }))}
                                                className={cn(
                                                    "px-2 py-1.5 rounded-lg text-xs font-medium border transition-all capitalize",
                                                    alertForm.severity === s
                                                        ? cn("text-white border-transparent", s === 'critical' ? 'bg-red-600' : s === 'high' ? 'bg-orange-600' : s === 'medium' ? 'bg-yellow-500' : 'bg-green-600')
                                                        : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-white/10"
                                                )}
                                            >
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <button
                                    onClick={() => alertMutation.mutate({
                                        clusterId: selectedCluster.cluster_id,
                                        ...alertForm,
                                    })}
                                    disabled={alertMutation.isPending}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-linear-to-r from-orange-600 to-red-600 text-white font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-orange-600/20"
                                >
                                    {alertMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                    {alertMutation.isPending ? 'Sending...' : `Send Alert to ${alertForm.recipient_role === 'ngo' ? 'NGOs' : alertForm.recipient_role === 'volunteer' ? 'Volunteers' : 'Admins'}`}
                                </button>
                                {alertMutation.isSuccess && (
                                    <p className="text-xs text-green-600 dark:text-green-400 text-center flex items-center justify-center gap-1">
                                        <CheckCircle2 className="w-3 h-3" />
                                        {(alertMutation.data as any)?.message || 'Alert sent successfully'}
                                    </p>
                                )}
                                {alertMutation.isError && (
                                    <p className="text-xs text-red-500 text-center">{(alertMutation.error as any)?.message || 'Alert failed'}</p>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

// ── Map Embed Component ──────────────────────────────────────────────────────

function HotspotMapEmbed({ cluster }: { cluster: ClusterData }) {
    const mapRef = useRef<HTMLDivElement>(null)
    const mapInstanceRef = useRef<any>(null)

    useEffect(() => {
        if (!mapRef.current || !cluster.centroid) return

        // Dynamically load Leaflet
        const loadLeaflet = async () => {
            if (typeof window === 'undefined') return

            // Add Leaflet CSS if not present
            if (!document.getElementById('leaflet-css')) {
                const link = document.createElement('link')
                link.id = 'leaflet-css'
                link.rel = 'stylesheet'
                link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
                document.head.appendChild(link)
            }

            // Load Leaflet JS
            const L = await import('leaflet')

            // Clean up previous instance
            if (mapInstanceRef.current) {
                mapInstanceRef.current.remove()
                mapInstanceRef.current = null
            }

            const lat = cluster.centroid!.lat
            const lng = cluster.centroid!.lng

            const map = L.map(mapRef.current!, {
                center: [lat, lng],
                zoom: 13,
                attributionControl: false,
            })

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
            }).addTo(map)

            // Cluster centroid marker
            const priorityColor = cluster.priority === 'critical' ? '#ef4444' :
                cluster.priority === 'high' ? '#f97316' :
                    cluster.priority === 'medium' ? '#eab308' : '#22c55e'

            const icon = L.divIcon({
                html: `<div style="background:${priorityColor};width:16px;height:16px;border-radius:50%;border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3)"></div>`,
                className: '',
                iconSize: [16, 16],
                iconAnchor: [8, 8],
            })

            L.marker([lat, lng], { icon }).addTo(map)
                .bindPopup(`<strong>Cluster #${(cluster.cluster_id || '').slice(0, 8)}</strong><br/>${cluster.event_count} events · ${cluster.total_people} people<br/>${cluster.dominant_type}`)
                .openPopup()

            // Draw boundary polygon if available
            if (cluster.boundary && cluster.boundary.coordinates) {
                try {
                    const coords = cluster.boundary.coordinates[0]
                    if (coords && coords.length > 0) {
                        const latlngs = coords.map((c: number[]) => [c[1], c[0]] as [number, number])
                        L.polygon(latlngs, {
                            color: priorityColor,
                            fillColor: priorityColor,
                            fillOpacity: 0.15,
                            weight: 2,
                        }).addTo(map)
                    }
                } catch (e) {
                    // Draw a circle as fallback
                    L.circle([lat, lng], {
                        radius: 500,
                        color: priorityColor,
                        fillColor: priorityColor,
                        fillOpacity: 0.15,
                        weight: 2,
                    }).addTo(map)
                }
            } else {
                // Fallback circle
                L.circle([lat, lng], {
                    radius: 500,
                    color: priorityColor,
                    fillColor: priorityColor,
                    fillOpacity: 0.15,
                    weight: 2,
                }).addTo(map)
            }

            mapInstanceRef.current = map

            // Fix Leaflet's tile display issues
            setTimeout(() => map.invalidateSize(), 100)
        }

        loadLeaflet()

        return () => {
            if (mapInstanceRef.current) {
                mapInstanceRef.current.remove()
                mapInstanceRef.current = null
            }
        }
    }, [cluster])

    if (!cluster.centroid) {
        return (
            <div className="h-80 rounded-xl bg-slate-100 dark:bg-white/5 flex items-center justify-center">
                <p className="text-sm text-slate-400">No coordinates available for this cluster</p>
            </div>
        )
    }

    return (
        <div
            ref={mapRef}
            className="h-80 rounded-xl overflow-hidden border border-slate-200 dark:border-white/10"
            style={{ minHeight: '320px' }}
        />
    )
}
