'use client'

import { useEffect, useState, useCallback, memo, useMemo, useRef } from 'react'
import Map, { Source, Layer, Marker, Popup, NavigationControl, ViewStateChangeEvent, MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────
export interface VictimMarkerData {
    id: string
    latitude: number
    longitude: number
    priority: string
    resource_type: string
    status: string
    description: string
    head_count: number
    disaster_id?: string
    address_text?: string
}

export interface SpreadMapViewProps {
    center: [number, number]
    bounds: {
        xRange: [number, number]
        yRange: [number, number]
    }
    grid: number[][]
    height?: string
    onCellHover?: (row: number, col: number, val: number) => void
    onCellLeave?: () => void
    epicenters?: Array<{lat: number, lon: number}>
    victimMarkers?: VictimMarkerData[]
    showMarkers?: boolean
    smoothImage?: string
}

// ─── Priority colors ─────────────────────────────────────────────────────────
const PRIORITY_COLORS: Record<string, string> = {
    critical: '#ef4444',
    urgent: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#22c55e',
}

const RESOURCE_ICONS: Record<string, string> = {
    food: '🍚',
    water: '💧',
    medical: '🏥',
    shelter: '🏠',
    personnel: '👥',
    equipment: '🔧',
    other: '📦',
}

// ─── Epicenter SVG ─────────────────────────────────────────────────────────
const EpicenterMarker = memo(function EpicenterMarker() {
    return (
        <div style={{ position: 'relative', width: 40, height: 40, pointerEvents: 'none', transform: 'translate(-50%, -50%)' }}>
            <svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feComposite in="SourceGraphic" in2="blur" operator="over" />
                    </filter>
                </defs>
                <circle cx="20" cy="20" r="18" fill="none" stroke="#ef4444" strokeWidth="2" strokeDasharray="4 2" opacity="0.6" filter="url(#glow)">
                    <animateTransform attributeName="transform" type="rotate" from="0 20 20" to="360 20 20" dur="8s" repeatCount="indefinite"/>
                </circle>
                <circle cx="20" cy="20" r="12" fill="none" stroke="#ef4444" strokeWidth="1.5" opacity="0.3" filter="url(#glow)">
                    <animate attributeName="r" values="8;16;8" dur="2s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2s" repeatCount="indefinite"/>
                </circle>
                <circle cx="20" cy="20" r="8" fill="#ef4444" opacity="0.8" filter="url(#glow)"/>
                <circle cx="20" cy="20" r="4" fill="white"/>
            </svg>
        </div>
    )
})

// ─── Victim Marker Component (Interactive) ───────────────────────────────────
function VictimMarkerItem({ marker, isActive, onToggle, onClose }: { marker: VictimMarkerData, isActive: boolean, onToggle: () => void, onClose: () => void }) {
    const priorityColor = PRIORITY_COLORS[marker.priority] || PRIORITY_COLORS.medium
    const resourceIcon = RESOURCE_ICONS[marker.resource_type] || RESOURCE_ICONS.other

    return (
        <>
            <Marker
                longitude={marker.longitude}
                latitude={marker.latitude}
                anchor="bottom"
                onClick={e => {
                    e.originalEvent.stopPropagation()
                    onToggle()
                }}
                style={{ zIndex: marker.priority === 'critical' ? 1000 : 0, cursor: 'pointer' }}
            >
                <motion.div 
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    style={{ position: 'relative', width: 32, height: 38, transform: 'translate(0, 0)' }}
                >
                    <svg width="32" height="38" viewBox="0 0 32 38" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <filter id={`drop-shadow-${marker.id}`} x="-20%" y="-20%" width="140%" height="140%">
                                <feDropShadow dx="0" dy="2" stdDeviation="2" floodOpacity="0.5" floodColor={priorityColor} />
                            </filter>
                        </defs>
                        <path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 22 16 22s16-10 16-22C32 7.16 24.84 0 16 0z"
                              fill={priorityColor} opacity="0.95" filter={`url(#drop-shadow-${marker.id})`}/>
                        <circle cx="16" cy="14" r="10" fill="white" opacity="0.95"/>
                    </svg>
                    <span style={{
                        position: 'absolute',
                        top: 4,
                        left: '50%',
                        transform: 'translateX(-50%)',
                        fontSize: 14,
                        lineHeight: 1,
                        pointerEvents: 'none',
                    }}>{resourceIcon}</span>
                </motion.div>
            </Marker>
            
            {isActive && (
                <Popup
                    longitude={marker.longitude}
                    latitude={marker.latitude}
                    anchor="bottom"
                    offset={[0, -42]}
                    onClose={onClose}
                    closeButton={false}
                    closeOnClick={true}
                    className="custom-glass-popup"
                    maxWidth="280px"
                    style={{ zIndex: 2000 }}
                >
                    <motion.div 
                        initial={{ opacity: 0, y: 10, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ duration: 0.2, ease: "easeOut" }}
                        className="bg-slate-900/80 backdrop-blur-xl border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-xl"
                        style={{ fontFamily: 'Inter, system-ui, sans-serif', padding: '12px' }}
                    >
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            borderBottom: '1px solid rgba(255,255,255,0.1)',
                            paddingBottom: '8px',
                            marginBottom: '8px',
                        }}>
                            <div className="flex items-center justify-center w-8 h-8 rounded-full bg-white/10 text-lg shadow-inner">
                                {resourceIcon}
                            </div>
                            <div>
                                <div style={{ fontWeight: 600, textTransform: 'capitalize', fontSize: '14px', color: '#f8fafc' }}>
                                    {marker.resource_type}
                                </div>
                                <div style={{
                                    fontSize: '11px',
                                    color: priorityColor,
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.5px',
                                }}>
                                    {marker.priority} PRIORITY
                                </div>
                            </div>
                        </div>
                        {marker.description && (
                            <p style={{ color: '#cbd5e1', margin: '0 0 8px 0', fontSize: '12px', lineHeight: 1.4 }}>
                                {marker.description}
                            </p>
                        )}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                            <span style={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                                {marker.head_count} {marker.head_count > 1 ? 'people' : 'person'}
                            </span>
                            <span style={{
                                padding: '2px 8px',
                                borderRadius: '6px',
                                background: marker.status === 'pending' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(34, 197, 94, 0.2)',
                                color: marker.status === 'pending' ? '#fcd34d' : '#86efac',
                                border: `1px solid ${marker.status === 'pending' ? 'rgba(245,158,11,0.3)' : 'rgba(34,197,94,0.3)'}`,
                                fontWeight: 600,
                                textTransform: 'capitalize',
                            }}>
                                {marker.status.replace(/_/g, ' ')}
                            </span>
                        </div>
                    </motion.div>
                </Popup>
            )}
        </>
    )
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

// 3D GeoJSON Feature Extractor. We drop tiny intensities to save geometry & render time.
function gridToGeoJSON(grid: number[][], bounds: SpreadMapViewProps['bounds']) {
    const features: any[] = []
    if (!grid?.length) return { type: 'FeatureCollection' as const, features }
    
    const rows = grid.length
    const cols = grid[0].length

    const minLat = bounds.yRange[0]
    const maxLat = bounds.yRange[1]
    const minLon = bounds.xRange[0]
    const maxLon = bounds.xRange[1]

    const dLat = (maxLat - minLat) / (rows - 1)
    const dLon = (maxLon - minLon) / (cols - 1)

    // Higher threshold: Only render cells > 0.15 intensity for performance
    const THRESHOLD = 0.25 

    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const val = grid[r][c]
            if (val < THRESHOLD) continue 

            const lat = minLat + r * dLat // Row 0 is South
            const btmLat = lat - (dLat / 2)
            const topLat = lat + (dLat / 2)
            const leftLon = minLon + c * dLon - (dLon / 2)
            const rightLon = minLon + c * dLon + (dLon / 2)

            features.push({
                type: 'Feature',
                properties: { val },
                geometry: {
                    type: 'Polygon',
                    coordinates: [[
                        [leftLon, btmLat], [rightLon, btmLat],
                        [rightLon, topLat], [leftLon, topLat],
                        [leftLon, btmLat]
                    ]]
                }
            })
        }
    }
    return { type: 'FeatureCollection' as const, features }
}

const HEATMAP_COLORS = [
    'interpolate',
    ['linear'],
    ['get', 'val'],
    0.0, 'rgba(0,0,4,0)',
    0.2, '#3b0f70',
    0.5, '#dd4968',
    0.8, '#fd9f6c',
    1.0, '#fcffa4'
]

const glassPopupStyles = `
.custom-glass-popup .maplibregl-popup-content {
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
}
.custom-glass-popup .maplibregl-popup-tip {
    border-top-color: rgba(15, 23, 42, 0.8) !important;
}
`

// ─── Main Component ──────────────────────────────────────────────────────────
function SpreadMapView({
    center,
    bounds,
    grid,
    height = '500px',
    onCellHover,
    onCellLeave,
    epicenters = [],
    victimMarkers = [],
    showMarkers = true,
    smoothImage,
}: SpreadMapViewProps) {
    const mapRef = useRef<MapRef | null>(null)
    const [viewState, setViewState] = useState({
        longitude: center[1],
        latitude: center[0],
        zoom: 10,
        pitch: 60, // Pitched by default to show 3D mountains
        bearing: 0
    })

    const [is3D, setIs3D] = useState(true)
    const [activePopupId, setActivePopupId] = useState<string | null>(null)

    // Reset center on demand if it drastically moved. Usually controlled by user though.
    useEffect(() => {
        setViewState(prev => ({
            ...prev,
            longitude: center[1],
            latitude: center[0]
        }))
        mapRef.current?.flyTo({ center: [center[1], center[0]], duration: 1000 })
    }, [center[0], center[1]])

    const toggle3D = useCallback(() => {
        const next3D = !is3D
        setIs3D(next3D)
        mapRef.current?.easeTo({
            pitch: next3D ? 60 : 0,
            duration: 1000,
        })
    }, [is3D])

    const [geoJsonData, setGeoJsonData] = useState<any>({ type: 'FeatureCollection', features: [] })
    
    // Throttled update – prevents lagging on every mini-step
    useEffect(() => {
        const timeout = setTimeout(() => {
            setGeoJsonData(gridToGeoJSON(grid, bounds))
        }, 150) // Reduced lag: update every 150ms instead of every 80ms
        return () => clearTimeout(timeout)
    }, [grid, bounds])

    // Interaction handler to replace mapMouseTracker
    const handleMouseMove = useCallback((e: any) => {
        if (!onCellHover || !grid?.length) return
        
        const lat = e.lngLat.lat
        const lng = e.lngLat.lng

        if (
            lat < bounds.yRange[0] || lat > bounds.yRange[1] ||
            lng < bounds.xRange[0] || lng > bounds.xRange[1]
        ) {
            onCellLeave?.()
            return
        }

        const rows = grid.length
        const cols = grid[0]?.length || 0

        // Correct Mapping: Bottom-up
        const row = Math.floor(((lat - bounds.yRange[0]) / (bounds.yRange[1] - bounds.yRange[0])) * rows)
        const col = Math.floor(((lng - bounds.xRange[0]) / (bounds.xRange[1] - bounds.xRange[0])) * cols)

        const clampedRow = Math.max(0, Math.min(rows - 1, row))
        const clampedCol = Math.max(0, Math.min(cols - 1, col))
        const val = grid[clampedRow]?.[clampedCol] ?? 0

        onCellHover(clampedRow, clampedCol, val)
    }, [bounds, grid, onCellHover, onCellLeave])

    const handleMouseLeave = useCallback(() => {
        if (onCellLeave) onCellLeave()
    }, [onCellLeave])

    // Compute paint height expression
    const extrusionHeight = useMemo(() => {
        return is3D 
            ? ['*', ['*', ['get', 'val'], ['get', 'val']], 15000] // Slightly higher peaks for better 3D effect
            : 0
    }, [is3D])

    // Image source coordinates [TL, TR, BR, BL]
    const imageCoordinates = useMemo(() => {
        return [
            [bounds.xRange[0], bounds.yRange[1]],
            [bounds.xRange[1], bounds.yRange[1]],
            [bounds.xRange[1], bounds.yRange[0]],
            [bounds.xRange[0], bounds.yRange[0]]
        ] as [[number, number], [number, number], [number, number], [number, number]]
    }, [bounds])

    return (
        <div style={{ height, width: '100%' }} className="relative bg-[#1a1a1a]">
            {/* MapLibre 3D Canvas */}
            <Map
                ref={mapRef}
                {...viewState}
                onMove={evt => setViewState(evt.viewState)}
                mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
                onMouseMove={handleMouseMove}
                onMouseOut={handleMouseLeave}
                maxPitch={85}
                renderWorldCopies={false}
            >
                <NavigationControl position="bottom-right" visualizePitch={true} />

                {/* Smooth Raster Heatmap Base */}
                {smoothImage && (
                    <Source id="smooth-heatmap-source" type="image" url={smoothImage} coordinates={imageCoordinates}>
                        <Layer
                            id="smooth-heatmap-layer"
                            type="raster"
                            paint={{
                                'raster-opacity': is3D ? 0.6 : 0.85,
                                'raster-fade-duration': 300
                            }}
                        />
                    </Source>
                )}

                {/* 3D Heatmap Peaks (slightly more transparent to see smooth base) */}
                <Source id="heatmap-data" type="geojson" data={geoJsonData}>
                    <Layer
                        id="heatmap-extrusion-layer"
                        type="fill-extrusion"
                        paint={{
                            'fill-extrusion-color': HEATMAP_COLORS as any,
                            'fill-extrusion-height': extrusionHeight as any,
                            'fill-extrusion-base': 0,
                            'fill-extrusion-opacity': is3D ? 0.5 : 0, // Lower opacity if 3D to see the smooth raster underneath
                            'fill-extrusion-height-transition': { duration: 400 } as any,
                            'fill-extrusion-color-transition': { duration: 400 } as any
                        }}
                    />
                </Source>

                {/* Epicenter markers */}
                {epicenters.length > 0 ? (
                    epicenters.map((ep, idx) => (
                        <Marker key={`ep-${idx}`} longitude={ep.lon} latitude={ep.lat} anchor="center" style={{ pointerEvents: 'none' }}>
                            <EpicenterMarker />
                        </Marker>
                    ))
                ) : (
                    <Marker longitude={center[1]} latitude={center[0]} anchor="center" style={{ pointerEvents: 'none' }}>
                        <EpicenterMarker />
                    </Marker>
                )}

                {/* Victim request markers */}
                {showMarkers && victimMarkers.map((marker) => (
                    <VictimMarkerItem 
                        key={marker.id} 
                        marker={marker} 
                        isActive={activePopupId === marker.id}
                        onToggle={() => setActivePopupId(activePopupId === marker.id ? null : marker.id)}
                        onClose={() => setActivePopupId(null)}
                    />
                ))}
            </Map>

            {/* Context styles for Popup */}
            <style dangerouslySetInnerHTML={{ __html: glassPopupStyles }} />

            {/* Subtle vignette overlay for premium look */}
            <div
                className="absolute inset-0 pointer-events-none z-[400]"
                style={{
                    boxShadow: 'inset 0 0 60px rgba(0,0,0,0.15)',
                    borderRadius: 'inherit',
                }}
            />

            {/* Victim markers count badge */}
            <AnimatePresence>
                {showMarkers && victimMarkers.length > 0 && (
                    <motion.div 
                        initial={{ opacity: 0, y: -20, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -20, scale: 0.9 }}
                        className="absolute top-4 left-4 z-[1000] bg-slate-900/60 backdrop-blur-md rounded-xl px-4 py-3 border border-white/10 shadow-[0_4px_24px_rgba(0,0,0,0.4)]"
                    >
                        <div className="flex items-center gap-3">
                            <span className="relative flex h-3 w-3">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>
                            </span>
                            <span className="text-xs font-bold text-white tracking-widest uppercase">
                                {victimMarkers.length} Active {victimMarkers.length === 1 ? 'Request' : 'Requests'}
                            </span>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
            
            {/* 2D/3D Toggle Button */}
            <motion.div 
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute top-4 right-4 z-[1000]"
            >
                <button
                    onClick={toggle3D}
                    className="bg-slate-900/60 hover:bg-slate-800/80 backdrop-blur-md rounded-xl px-4 py-3 border border-white/10 shadow-[0_4px_24px_rgba(0,0,0,0.4)] transition-all flex items-center gap-3 group cursor-pointer"
                >
                    <div className={cn("w-2.5 h-2.5 rounded-full transition-all duration-300", is3D ? "bg-orange-500 shadow-[0_0_12px_rgba(249,115,22,0.9)]" : "bg-blue-400 shadow-[0_0_12px_rgba(96,165,250,0.9)]")} />
                    <span className="text-xs font-bold text-white uppercase tracking-widest group-hover:text-orange-200 transition-colors">
                        {is3D ? '3D Extrusion' : '2D Heatmap'}
                    </span>
                </button>
            </motion.div>
        </div>
    )
}

export default memo(SpreadMapView)
