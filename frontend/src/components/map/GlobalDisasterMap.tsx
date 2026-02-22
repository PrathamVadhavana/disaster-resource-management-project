'use client'

import { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents, ZoomControl } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L, { DivIcon } from 'leaflet'
import { useQuery } from '@tanstack/react-query'
import 'leaflet/dist/leaflet.css'

// ── Types ─────────────────────────────────────────────────────────────────

interface GlobalDisasterEvent {
    id: string
    source: string
    type: string
    title: string
    description?: string
    severity: string
    magnitude?: number
    latitude: number
    longitude: number
    location_name?: string
    url?: string
    timestamp?: string
    alert_level?: string
    affected_population?: number
    depth_km?: number
}

interface GlobalDisasterResponse {
    events: GlobalDisasterEvent[]
    total: number
    sources: Record<string, { status: string; count: number; error?: string }>
    stats: {
        by_type: Record<string, number>
        by_severity: Record<string, number>
        by_source: Record<string, number>
    }
    fetched_at: string
}

// ── Constants ─────────────────────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
    critical: '#EF4444',
    high: '#F97316',
    medium: '#EAB308',
    low: '#22C55E',
}

const SEVERITY_GLOW: Record<string, string> = {
    critical: '0 0 12px 4px rgba(239,68,68,0.5)',
    high: '0 0 10px 3px rgba(249,115,22,0.4)',
    medium: '0 0 8px 2px rgba(234,179,8,0.3)',
    low: '0 0 6px 2px rgba(34,197,94,0.25)',
}

const TYPE_ICONS: Record<string, string> = {
    earthquake: '🔴',
    flood: '🌊',
    cyclone: '🌀',
    wildfire: '🔥',
    volcanic_eruption: '🌋',
    drought: '☀️',
    tsunami: '🌊',
    epidemic: '🦠',
    landslide: '⛰️',
    other: '⚠️',
}

const TYPE_LABELS: Record<string, string> = {
    earthquake: 'Earthquake',
    flood: 'Flood',
    cyclone: 'Cyclone / Storm',
    wildfire: 'Wildfire',
    volcanic_eruption: 'Volcano',
    drought: 'Drought',
    tsunami: 'Tsunami',
    epidemic: 'Epidemic',
    landslide: 'Landslide',
    other: 'Other',
}

const SOURCE_COLORS: Record<string, string> = {
    USGS: '#3B82F6',
    'NASA EONET': '#10B981',
    GDACS: '#F59E0B',
    ReliefWeb: '#8B5CF6',
}

// ── Memoised icon cache ──────────────────────────────────────────────────

const iconCache = new Map<string, DivIcon>()

function getMarkerIcon(severity: string, type: string): DivIcon {
    const key = `${severity}-${type}`
    if (iconCache.has(key)) return iconCache.get(key)!

    const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.medium
    const glow = SEVERITY_GLOW[severity] || ''
    const emoji = TYPE_ICONS[type] || '⚠️'
    const size = severity === 'critical' ? 34 : severity === 'high' ? 30 : 26

    const icon = new DivIcon({
        className: 'disaster-marker-icon',
        html: `<div style="
            width:${size}px;height:${size}px;
            border-radius:50%;
            background:${color};
            border:2.5px solid rgba(255,255,255,0.9);
            box-shadow:${glow};
            display:flex;align-items:center;justify-content:center;
            font-size:${size * 0.42}px;
            transition:transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s ease;
            cursor:pointer;
        " class="marker-dot"><span style="filter:grayscale(0)">${emoji}</span></div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2 - 4],
    })

    iconCache.set(key, icon)
    return icon
}

// ── Cluster icon factory ─────────────────────────────────────────────────

function createClusterIcon(cluster: any): DivIcon {
    const count = cluster.getChildCount()
    const children = cluster.getAllChildMarkers()

    // Determine dominant severity in cluster
    const severityCounts: Record<string, number> = {}
    children.forEach((m: any) => {
        const sev = m.options?.severity || 'medium'
        severityCounts[sev] = (severityCounts[sev] || 0) + 1
    })
    const dominant = Object.entries(severityCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'medium'
    const color = SEVERITY_COLORS[dominant] || SEVERITY_COLORS.medium

    const size = count > 100 ? 56 : count > 30 ? 48 : 40

    return new DivIcon({
        html: `<div style="
            width:${size}px;height:${size}px;
            border-radius:50%;
            background:radial-gradient(circle at 30% 30%, ${color}dd, ${color}99);
            border:3px solid rgba(255,255,255,0.85);
            box-shadow:0 2px 12px ${color}66, 0 0 0 4px ${color}22;
            display:flex;align-items:center;justify-content:center;
            color:white;font-weight:700;font-size:${size > 48 ? 15 : 13}px;
            font-family:-apple-system,BlinkMacSystemFont,sans-serif;
            letter-spacing:-0.3px;
            transition:transform 0.2s cubic-bezier(.4,0,.2,1);
            cursor:pointer;
        "><span>${count > 999 ? `${(count / 1000).toFixed(1)}k` : count}</span></div>`,
        className: 'disaster-cluster-icon',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
    })
}

// ── Map smooth zoom handler ──────────────────────────────────────────────

function SmoothZoom() {
    const map = useMap()
    useEffect(() => {
        map.options.zoomSnap = 0.25
        map.options.zoomDelta = 0.5
        map.options.wheelPxPerZoomLevel = 120
    }, [map])
    return null
}

// ── Track zoom level ─────────────────────────────────────────────────────

function ZoomTracker({ onZoomChange }: { onZoomChange: (z: number) => void }) {
    useMapEvents({
        zoomend: (e) => onZoomChange(e.target.getZoom()),
    })
    return null
}

// ── Helpers ──────────────────────────────────────────────────────────────

function formatTime(ts?: string) {
    if (!ts) return 'Unknown'
    try {
        return new Date(ts).toLocaleDateString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
        })
    } catch { return ts }
}

function timeAgo(ts?: string) {
    if (!ts) return ''
    const diff = Date.now() - new Date(ts).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
}

// ── Main Component ────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function GlobalDisasterMap() {
    const [typeFilter, setTypeFilter] = useState<string>('all')
    const [severityFilter, setSeverityFilter] = useState<string>('all')
    const [sourceFilter, setSourceFilter] = useState<string>('all')
    const [currentZoom, setCurrentZoom] = useState(2)
    const [showFilters, setShowFilters] = useState(false)
    const mapRef = useRef<L.Map | null>(null)

    // Fetch global disaster data
    const { data, isLoading, error, refetch } = useQuery<GlobalDisasterResponse>({
        queryKey: ['global-disasters'],
        queryFn: async () => {
            const r = await fetch(`${API_BASE}/api/global-disasters/?limit=1000`)
            if (!r.ok) throw new Error('Failed to fetch global disasters')
            return r.json()
        },
        refetchInterval: 300_000,
        staleTime: 240_000,
    })

    const events = data?.events ?? []
    const stats = data?.stats
    const sources = data?.sources

    // Apply filters
    const filteredEvents = useMemo(() => {
        let result = events
        if (typeFilter !== 'all') result = result.filter((e) => e.type === typeFilter)
        if (severityFilter !== 'all') result = result.filter((e) => e.severity === severityFilter)
        if (sourceFilter !== 'all') result = result.filter((e) => e.source === sourceFilter)
        return result
    }, [events, typeFilter, severityFilter, sourceFilter])

    // Stats for current filters
    const filteredStats = useMemo(() => {
        const bySeverity: Record<string, number> = {}
        const bySource: Record<string, number> = {}
        for (const e of filteredEvents) {
            bySeverity[e.severity] = (bySeverity[e.severity] || 0) + 1
            bySource[e.source] = (bySource[e.source] || 0) + 1
        }
        return { bySeverity, bySource, total: filteredEvents.length }
    }, [filteredEvents])

    const activeFiltersCount = [typeFilter, severityFilter, sourceFilter].filter(f => f !== 'all').length

    const clearFilters = useCallback(() => {
        setTypeFilter('all')
        setSeverityFilter('all')
        setSourceFilter('all')
    }, [])

    const flyToEvent = useCallback((event: GlobalDisasterEvent) => {
        mapRef.current?.flyTo([event.latitude, event.longitude], 8, {
            duration: 1.2,
            easeLinearity: 0.25,
        })
    }, [])

    return (
        <div className="relative w-full h-full rounded-2xl overflow-hidden border border-white/10 shadow-2xl bg-slate-950">
            {/* ── Global CSS for markers ── */}
            <style jsx global>{`
                .disaster-marker-icon { background: none !important; border: none !important; }
                .disaster-cluster-icon { background: none !important; border: none !important; }
                .marker-dot:hover { transform: scale(1.25) !important; z-index: 9999 !important; }
                .disaster-cluster-icon > div:hover { transform: scale(1.12) !important; }
                .leaflet-popup-content-wrapper {
                    border-radius: 16px !important;
                    padding: 0 !important;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.08) !important;
                    background: rgba(15, 23, 42, 0.95) !important;
                    backdrop-filter: blur(20px) !important;
                    -webkit-backdrop-filter: blur(20px) !important;
                    border: 1px solid rgba(255,255,255,0.1) !important;
                    overflow: hidden;
                }
                .leaflet-popup-content { margin: 0 !important; color: #e2e8f0 !important; }
                .leaflet-popup-tip { background: rgba(15, 23, 42, 0.95) !important; }
                .leaflet-popup-close-button {
                    color: #94a3b8 !important;
                    font-size: 20px !important;
                    top: 8px !important; right: 10px !important;
                }
                .leaflet-popup-close-button:hover { color: white !important; }
                .leaflet-control-zoom { border: none !important; }
                .leaflet-control-zoom a {
                    background: rgba(15,23,42,0.9) !important;
                    backdrop-filter: blur(10px) !important;
                    color: #e2e8f0 !important;
                    border: 1px solid rgba(255,255,255,0.1) !important;
                    border-radius: 10px !important;
                    width: 36px !important; height: 36px !important;
                    line-height: 36px !important; font-size: 18px !important;
                    margin-bottom: 4px !important;
                    transition: all 0.2s ease !important;
                }
                .leaflet-control-zoom a:hover {
                    background: rgba(30,41,59,0.95) !important;
                    border-color: rgba(255,255,255,0.2) !important;
                }
                .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large { background: none !important; }
                .leaflet-container { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
            `}</style>

            {/* Loading overlay */}
            {isLoading && (
                <div className="absolute inset-0 z-[2000] bg-slate-950/90 backdrop-blur-sm flex items-center justify-center">
                    <div className="flex flex-col items-center gap-4">
                        <div className="relative">
                            <div className="w-12 h-12 border-3 border-blue-500/30 rounded-full" />
                            <div className="absolute inset-0 w-12 h-12 border-3 border-blue-500 border-t-transparent rounded-full animate-spin" />
                        </div>
                        <div className="text-center">
                            <p className="text-white text-sm font-semibold">Loading live disaster data</p>
                            <p className="text-slate-400 text-xs mt-1">Aggregating from USGS, NASA EONET, GDACS &amp; ReliefWeb</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Error banner */}
            {error && (
                <div className="absolute top-0 left-0 right-0 z-[2000] bg-red-500/90 backdrop-blur-sm text-white px-4 py-2.5 text-sm flex items-center justify-between">
                    <span className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                        Failed to load disaster data
                    </span>
                    <button onClick={() => refetch()} className="px-3 py-1 rounded-lg bg-white/20 hover:bg-white/30 text-xs font-medium transition-colors">Retry</button>
                </div>
            )}

            {/* ── Map ── */}
            <MapContainer
                center={[20, 0]}
                zoom={2}
                minZoom={2}
                maxZoom={18}
                scrollWheelZoom
                zoomControl={false}
                attributionControl={false}
                style={{ height: '100%', width: '100%' }}
                className="z-0"
                ref={mapRef}
                preferCanvas
                // @ts-ignore
                zoomSnap={0.25}
                zoomDelta={0.5}
                wheelPxPerZoomLevel={120}
                inertia
                inertiaDeceleration={3000}
                zoomAnimation
                markerZoomAnimation
                fadeAnimation
            >
                <SmoothZoom />
                <ZoomTracker onZoomChange={setCurrentZoom} />
                <ZoomControl position="bottomright" />

                {/* High-quality dark tile layer */}
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://carto.com/">CARTO</a>'
                    maxZoom={20}
                    // @ts-ignore
                    updateWhenZooming={false}
                    updateWhenIdle={true}
                />

                {/* ── Clustered markers ── */}
                <MarkerClusterGroup
                    chunkedLoading
                    maxClusterRadius={50}
                    spiderfyOnMaxZoom
                    showCoverageOnHover={false}
                    zoomToBoundsOnClick
                    animate
                    animateAddingMarkers={false}
                    disableClusteringAtZoom={12}
                    iconCreateFunction={createClusterIcon}
                    spiderfyDistanceMultiplier={1.8}
                    // @ts-ignore
                    removeOutsideVisibleBounds
                >
                    {filteredEvents.map((event) => (
                        <Marker
                            key={event.id}
                            position={[event.latitude, event.longitude]}
                            icon={getMarkerIcon(event.severity, event.type)}
                            // @ts-ignore - pass severity for cluster icon calculation
                            severity={event.severity}
                        >
                            <Popup maxWidth={360} minWidth={260} closeButton>
                                <div className="p-0">
                                    {/* Popup header with gradient */}
                                    <div className="px-4 pt-4 pb-3" style={{
                                        background: `linear-gradient(135deg, ${SEVERITY_COLORS[event.severity]}22, transparent)`,
                                    }}>
                                        <div className="flex items-start gap-3">
                                            <span className="text-2xl flex-shrink-0 mt-0.5">{TYPE_ICONS[event.type] || '⚠️'}</span>
                                            <div className="flex-1 min-w-0">
                                                <h3 className="font-bold text-sm leading-snug text-white pr-4">{event.title}</h3>
                                                <div className="flex items-center gap-2 mt-2 flex-wrap">
                                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white tracking-wide"
                                                        style={{ backgroundColor: SEVERITY_COLORS[event.severity] }}>
                                                        {event.severity.toUpperCase()}
                                                    </span>
                                                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/10 text-slate-300"
                                                        style={{ borderLeft: `3px solid ${SOURCE_COLORS[event.source] || '#888'}` }}>
                                                        {event.source}
                                                    </span>
                                                    {event.timestamp && (
                                                        <span className="text-[10px] text-slate-400 ml-auto">{timeAgo(event.timestamp)}</span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Popup body */}
                                    <div className="px-4 pb-4 space-y-3">
                                        {event.description && (
                                            <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">{event.description.slice(0, 200)}</p>
                                        )}

                                        <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                                            {event.magnitude != null && (
                                                <div className="bg-white/5 rounded-lg px-2.5 py-1.5">
                                                    <span className="text-slate-500 text-[10px] block">Magnitude</span>
                                                    <span className="font-bold text-orange-400">{event.magnitude}</span>
                                                </div>
                                            )}
                                            {event.depth_km != null && (
                                                <div className="bg-white/5 rounded-lg px-2.5 py-1.5">
                                                    <span className="text-slate-500 text-[10px] block">Depth</span>
                                                    <span className="font-semibold text-slate-200">{event.depth_km.toFixed(1)} km</span>
                                                </div>
                                            )}
                                            {event.location_name && (
                                                <div className="col-span-2 bg-white/5 rounded-lg px-2.5 py-1.5">
                                                    <span className="text-slate-500 text-[10px] block">Location</span>
                                                    <span className="font-medium text-slate-200">{event.location_name}</span>
                                                </div>
                                            )}
                                            {event.affected_population != null && event.affected_population > 0 && (
                                                <div className="col-span-2 bg-white/5 rounded-lg px-2.5 py-1.5">
                                                    <span className="text-slate-500 text-[10px] block">Affected Population</span>
                                                    <span className="font-bold text-red-400">{event.affected_population.toLocaleString()} people</span>
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex items-center justify-between pt-1 border-t border-white/5">
                                            <span className="text-[10px] text-slate-500">{formatTime(event.timestamp)}</span>
                                            {event.url && (
                                                <a href={event.url} target="_blank" rel="noopener noreferrer"
                                                    className="text-[11px] text-blue-400 hover:text-blue-300 font-medium transition-colors">
                                                    View Source →
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </Popup>
                        </Marker>
                    ))}
                </MarkerClusterGroup>
            </MapContainer>

            {/* ── Top-left: Live feed ── */}
            <div className="absolute top-3 left-3 z-[1000] w-[280px]">
                <div className="bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden">
                    <div className="px-4 py-3 flex items-center justify-between border-b border-white/[0.06]">
                        <div className="flex items-center gap-2">
                            <span className="relative flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
                            </span>
                            <span className="text-xs font-semibold text-white tracking-wide">LIVE FEED</span>
                        </div>
                        <span className="text-[10px] text-slate-500 font-mono">{filteredStats.total} events</span>
                    </div>
                    <div className="max-h-[280px] overflow-y-auto overflow-x-hidden" style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.1) transparent' }}>
                        {filteredEvents.slice(0, 15).map((e) => (
                            <button key={e.id} onClick={() => flyToEvent(e)}
                                className="w-full text-left px-4 py-2.5 hover:bg-white/[0.04] transition-colors duration-150 border-b border-white/[0.03] last:border-0 group">
                                <div className="flex items-start gap-2.5">
                                    <span className="text-sm mt-0.5 flex-shrink-0">{TYPE_ICONS[e.type] || '⚠️'}</span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-[11px] font-medium text-slate-200 truncate group-hover:text-white transition-colors">{e.title}</p>
                                        <div className="flex items-center gap-1.5 mt-1">
                                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full text-white"
                                                style={{ backgroundColor: SEVERITY_COLORS[e.severity] }}>
                                                {e.severity.toUpperCase()}
                                            </span>
                                            <span className="text-[9px] text-slate-500">{e.source}</span>
                                            {e.timestamp && <span className="text-[9px] text-slate-600 ml-auto">{timeAgo(e.timestamp)}</span>}
                                        </div>
                                    </div>
                                </div>
                            </button>
                        ))}
                        {filteredEvents.length === 0 && (
                            <div className="py-8 text-center">
                                <p className="text-xs text-slate-500">No events matching filters</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Top-right: Status + Filters ── */}
            <div className="absolute top-3 right-3 z-[1000] flex flex-col gap-2 w-[200px]">
                {/* Status card */}
                <div className="bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl px-4 py-3 shadow-2xl">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="relative flex h-2 w-2">
                            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${data ? 'bg-green-400' : 'bg-yellow-400'} opacity-75`} />
                            <span className={`relative inline-flex rounded-full h-2 w-2 ${data ? 'bg-green-500' : 'bg-yellow-500'}`} />
                        </span>
                        <span className="text-xs font-bold text-white">{data ? 'Live' : 'Connecting...'}</span>
                        <span className="text-xs font-mono text-slate-400 ml-auto">{filteredStats.total}</span>
                    </div>
                    {data?.fetched_at && (
                        <p className="text-[10px] text-slate-500">Updated {formatTime(data.fetched_at)}</p>
                    )}
                </div>

                {/* Filter toggle */}
                <button onClick={() => setShowFilters(!showFilters)}
                    className={`bg-slate-900/80 backdrop-blur-xl border rounded-2xl px-4 py-2.5 shadow-2xl text-xs font-medium flex items-center justify-between transition-colors ${showFilters ? 'border-blue-500/40 text-blue-400' : 'border-white/[0.08] text-slate-300 hover:text-white'
                        }`}>
                    <span className="flex items-center gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                            <path fillRule="evenodd" d="M2.628 1.601C5.028 1.206 7.49 1 10 1s4.973.206 7.372.601a.75.75 0 01.628.74v2.288a2.25 2.25 0 01-.659 1.59l-4.682 4.683a2.25 2.25 0 00-.659 1.59v3.037c0 .684-.31 1.33-.844 1.757l-1.937 1.55A.75.75 0 018 18.25v-5.757a2.25 2.25 0 00-.659-1.591L2.659 6.22A2.25 2.25 0 012 4.629V2.34a.75.75 0 01.628-.74z" clipRule="evenodd" />
                        </svg>
                        Filters
                    </span>
                    {activeFiltersCount > 0 && (
                        <span className="bg-blue-500 text-white text-[9px] font-bold w-4 h-4 rounded-full flex items-center justify-center">{activeFiltersCount}</span>
                    )}
                </button>

                {/* Filters panel */}
                {showFilters && (
                    <div className="bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden">
                        {/* Source */}
                        <div className="px-4 py-3 border-b border-white/[0.05]">
                            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-1.5">Source</label>
                            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}
                                className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-blue-500/50 transition-colors appearance-none cursor-pointer">
                                <option value="all" className="bg-slate-800">All Sources ({events.length})</option>
                                {Object.entries(stats?.by_source || {}).map(([src, count]) => (
                                    <option key={src} value={src} className="bg-slate-800">{src} ({count})</option>
                                ))}
                            </select>
                        </div>
                        {/* Type */}
                        <div className="px-4 py-3 border-b border-white/[0.05]">
                            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-1.5">Type</label>
                            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
                                className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-blue-500/50 transition-colors appearance-none cursor-pointer">
                                <option value="all" className="bg-slate-800">All Types</option>
                                {Object.entries(stats?.by_type || {}).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                                    <option key={type} value={type} className="bg-slate-800">{TYPE_LABELS[type] || type} ({count})</option>
                                ))}
                            </select>
                        </div>
                        {/* Severity */}
                        <div className="px-4 py-3 border-b border-white/[0.05]">
                            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block mb-1.5">Severity</label>
                            <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
                                className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-blue-500/50 transition-colors appearance-none cursor-pointer">
                                <option value="all" className="bg-slate-800">All Severities</option>
                                {['critical', 'high', 'medium', 'low'].map((sev) => (
                                    <option key={sev} value={sev} className="bg-slate-800">{sev.charAt(0).toUpperCase() + sev.slice(1)} ({stats?.by_severity?.[sev] || 0})</option>
                                ))}
                            </select>
                        </div>
                        {/* Clear */}
                        {activeFiltersCount > 0 && (
                            <button onClick={clearFilters}
                                className="w-full px-4 py-2.5 text-[11px] font-medium text-red-400 hover:text-red-300 hover:bg-white/[0.03] transition-colors">
                                Clear all filters
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* ── Bottom-right: Severity legend ── */}
            <div className="absolute bottom-14 right-3 z-[1000] bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl px-4 py-3 shadow-2xl">
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Severity</h4>
                <div className="space-y-1.5">
                    {Object.entries(SEVERITY_COLORS).map(([level, color]) => (
                        <button key={level} onClick={() => setSeverityFilter(severityFilter === level ? 'all' : level)}
                            className={`flex items-center gap-2.5 w-full text-left rounded-lg px-1.5 py-0.5 -mx-1.5 transition-colors ${severityFilter === level ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'}`}>
                            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}66` }} />
                            <span className="text-[11px] capitalize text-slate-300 flex-1">{level}</span>
                            <span className="text-[10px] text-slate-500 font-mono">{filteredStats.bySeverity[level] || 0}</span>
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Bottom-left: Data sources ── */}
            <div className="absolute bottom-3 left-3 z-[1000] bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] rounded-2xl shadow-2xl px-4 py-3">
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Data Sources</h4>
                <div className="space-y-1.5">
                    {Object.entries(sources || {}).map(([name, info]) => (
                        <button key={name} onClick={() => setSourceFilter(sourceFilter === name ? 'all' : name)}
                            className={`flex items-center gap-2.5 w-full text-left rounded-lg px-1.5 py-0.5 -mx-1.5 transition-colors ${sourceFilter === name ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'}`}>
                            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${(info as any).status === 'ok' ? 'bg-green-500' : 'bg-red-500'}`}
                                style={(info as any).status === 'ok' ? { boxShadow: '0 0 6px rgba(34,197,94,0.5)' } : {}} />
                            <span className="text-[11px] font-medium text-slate-300 flex-1">{name}</span>
                            <span className="text-[10px] text-slate-500 font-mono">{(info as any).count}</span>
                        </button>
                    ))}
                </div>
                {data?.fetched_at && (
                    <p className="text-[9px] text-slate-600 mt-2 pt-2 border-t border-white/[0.05]">
                        Real-time from USGS, NASA, GDACS &amp; ReliefWeb
                    </p>
                )}
            </div>

            {/* ── Attribution ── */}
            <div className="absolute bottom-1 right-1/2 translate-x-1/2 z-[1000] text-[9px] text-slate-600">
                © <a href="https://carto.com/" target="_blank" rel="noopener" className="hover:text-slate-400 transition-colors">CARTO</a> · <a href="https://www.openstreetmap.org/" target="_blank" rel="noopener" className="hover:text-slate-400 transition-colors">OpenStreetMap</a>
            </div>
        </div>
    )
}
