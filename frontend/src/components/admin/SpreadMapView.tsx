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

// ─── Map tile styles ──────────────────────────────────────────────────────────
const MAP_STYLE_DARK = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const MAP_STYLE_LIGHT = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'

// ─── Hook: detect theme ───────────────────────────────────────────────────────
function useIsDarkMode() {
    const [isDark, setIsDark] = useState(() => {
        if (typeof window === 'undefined') return true
        return document.documentElement.classList.contains('dark')
    })

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'))
        })
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => observer.disconnect()
    }, [])

    return isDark
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
function VictimMarkerItem({ marker, isActive, onToggle, onClose, isDark }: { marker: VictimMarkerData, isActive: boolean, onToggle: () => void, onClose: () => void, isDark: boolean }) {
    const priorityColor = PRIORITY_COLORS[marker.priority] || PRIORITY_COLORS.medium
    const resourceIcon = RESOURCE_ICONS[marker.resource_type] || RESOURCE_ICONS.other

    // Popup background & text adapt to theme
    const popupBg = isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255, 255, 255, 0.95)'
    const popupBorder = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'
    const titleColor = isDark ? '#f8fafc' : '#0f172a'
    const descColor = isDark ? '#cbd5e1' : '#475569'
    const metaColor = isDark ? '#94a3b8' : '#64748b'

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
                    offset={[0, -42] as any}
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
                        style={{
                            background: popupBg,
                            backdropFilter: 'blur(16px)',
                            WebkitBackdropFilter: 'blur(16px)',
                            border: `1px solid ${popupBorder}`,
                            boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
                            borderRadius: '12px',
                            fontFamily: 'Inter, system-ui, sans-serif',
                            padding: '12px',
                        }}
                    >
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            borderBottom: `1px solid ${popupBorder}`,
                            paddingBottom: '8px',
                            marginBottom: '8px',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: '50%', background: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)', fontSize: 18 }}>
                                {resourceIcon}
                            </div>
                            <div>
                                <div style={{ fontWeight: 600, textTransform: 'capitalize', fontSize: '14px', color: titleColor }}>
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
                            <p style={{ color: descColor, margin: '0 0 8px 0', fontSize: '12px', lineHeight: 1.4 }}>
                                {marker.description}
                            </p>
                        )}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                            <span style={{ color: metaColor, display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                                {marker.head_count} {marker.head_count > 1 ? 'people' : 'person'}
                            </span>
                            <span style={{
                                padding: '2px 8px',
                                borderRadius: '6px',
                                background: marker.status === 'pending'
                                    ? (isDark ? 'rgba(245, 158, 11, 0.2)' : 'rgba(245, 158, 11, 0.15)')
                                    : (isDark ? 'rgba(34, 197, 94, 0.2)' : 'rgba(34, 197, 94, 0.15)'),
                                color: marker.status === 'pending'
                                    ? (isDark ? '#fcd34d' : '#b45309')
                                    : (isDark ? '#86efac' : '#166534'),
                                border: `1px solid ${marker.status === 'pending'
                                    ? (isDark ? 'rgba(245,158,11,0.3)' : 'rgba(245,158,11,0.4)')
                                    : (isDark ? 'rgba(34,197,94,0.3)' : 'rgba(34,197,94,0.4)')}`,
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

    const THRESHOLD = 0.25 

    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const val = grid[r][c]
            if (val < THRESHOLD) continue 

            const lat = minLat + r * dLat
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

// Light-mode friendly heatmap palette (more vivid to stand out on light tiles)
const HEATMAP_COLORS_LIGHT = [
    'interpolate',
    ['linear'],
    ['get', 'val'],
    0.0, 'rgba(255,200,0,0)',
    0.2, 'rgba(200,50,180,0.7)',
    0.5, 'rgba(220,40,40,0.85)',
    0.8, 'rgba(255,120,0,0.9)',
    1.0, 'rgba(255,220,0,0.95)'
]

function getGlassPopupStyles(isDark: boolean) {
    return `
.custom-glass-popup .maplibregl-popup-content {
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
}
.custom-glass-popup .maplibregl-popup-tip {
    border-top-color: ${isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255, 255, 255, 0.95)'} !important;
}
`
}

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
    const isDark = useIsDarkMode()

    const [viewState, setViewState] = useState({
        longitude: center[1],
        latitude: center[0],
        zoom: 10,
        pitch: 60,
        bearing: 0
    })

    const [is3D, setIs3D] = useState(true)
    const [activePopupId, setActivePopupId] = useState<string | null>(null)

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
    
    useEffect(() => {
        const timeout = setTimeout(() => {
            setGeoJsonData(gridToGeoJSON(grid, bounds))
        }, 150)
        return () => clearTimeout(timeout)
    }, [grid, bounds])

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

    const extrusionHeight = useMemo(() => {
        return is3D 
            ? ['*', ['*', ['get', 'val'], ['get', 'val']], 15000]
            : 0
    }, [is3D])

    const imageCoordinates = useMemo(() => {
        return [
            [bounds.xRange[0], bounds.yRange[1]],
            [bounds.xRange[1], bounds.yRange[1]],
            [bounds.xRange[1], bounds.yRange[0]],
            [bounds.xRange[0], bounds.yRange[0]]
        ] as [[number, number], [number, number], [number, number], [number, number]]
    }, [bounds])

    // Theme-aware colors
    const bgColor = isDark ? '#1a1a1a' : '#f8fafc'
    const badgeBg = isDark ? 'rgba(15,23,42,0.7)' : 'rgba(255,255,255,0.92)'
    const badgeBorder = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.12)'
    const badgeText = isDark ? '#fff' : '#0f172a'
    const dotColor = isDark ? '#f87171' : '#ef4444'
    const toggleBg = isDark ? 'rgba(15,23,42,0.7)' : 'rgba(255,255,255,0.92)'
    const toggleText = isDark ? '#fff' : '#1e293b'

    const heatmapColors = isDark ? HEATMAP_COLORS : HEATMAP_COLORS_LIGHT

    return (
        <div style={{ height, width: '100%', backgroundColor: bgColor }} className="relative">
            <Map
                ref={mapRef}
                {...viewState}
                onMove={evt => setViewState(evt.viewState)}
                mapStyle={isDark ? MAP_STYLE_DARK : MAP_STYLE_LIGHT}
                onMouseMove={handleMouseMove}
                onMouseOut={handleMouseLeave}
                maxPitch={85}
                renderWorldCopies={false}
            >
                <NavigationControl position="bottom-right" visualizePitch={true} />

                {smoothImage && (
                    <Source id="smooth-heatmap-source" type="image" url={smoothImage} coordinates={imageCoordinates}>
                        <Layer
                            id="smooth-heatmap-layer"
                            type="raster"
                            paint={{
                                'raster-opacity': is3D ? (isDark ? 0.6 : 0.5) : (isDark ? 0.85 : 0.7),
                                'raster-fade-duration': 300
                            }}
                        />
                    </Source>
                )}

                <Source id="heatmap-data" type="geojson" data={geoJsonData}>
                    <Layer
                        id="heatmap-extrusion-layer"
                        type="fill-extrusion"
                        paint={{
                            'fill-extrusion-color': heatmapColors as any,
                            'fill-extrusion-height': extrusionHeight as any,
                            'fill-extrusion-base': 0,
                            'fill-extrusion-opacity': is3D ? (isDark ? 0.5 : 0.65) : 0,
                            'fill-extrusion-height-transition': { duration: 400 } as any,
                            'fill-extrusion-color-transition': { duration: 400 } as any
                        }}
                    />
                </Source>

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

                {showMarkers && victimMarkers.map((marker) => (
                    <VictimMarkerItem 
                        key={marker.id} 
                        marker={marker} 
                        isActive={activePopupId === marker.id}
                        onToggle={() => setActivePopupId(activePopupId === marker.id ? null : marker.id)}
                        onClose={() => setActivePopupId(null)}
                        isDark={isDark}
                    />
                ))}
            </Map>

            <style dangerouslySetInnerHTML={{ __html: getGlassPopupStyles(isDark) }} />

            {/* Vignette overlay */}
            <div
                className="absolute inset-0 pointer-events-none z-[400]"
                style={{
                    boxShadow: 'inset 0 0 60px rgba(0,0,0,0.10)',
                    borderRadius: 'inherit',
                }}
            />

            {/* Active requests badge */}
            <AnimatePresence>
                {showMarkers && victimMarkers.length > 0 && (
                    <motion.div 
                        initial={{ opacity: 0, y: -20, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -20, scale: 0.9 }}
                        className="absolute top-4 left-4 z-[1000] rounded-xl px-4 py-3 border shadow-lg"
                        style={{
                            background: badgeBg,
                            borderColor: badgeBorder,
                            backdropFilter: 'blur(12px)',
                            WebkitBackdropFilter: 'blur(12px)',
                        }}
                    >
                        <div className="flex items-center gap-3">
                            <span className="relative flex h-3 w-3">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>
                            </span>
                            <span className="text-xs font-bold tracking-widest uppercase" style={{ color: badgeText }}>
                                {victimMarkers.length} Active {victimMarkers.length === 1 ? 'Request' : 'Requests'}
                            </span>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
            
            {/* 2D/3D Toggle */}
            <motion.div 
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute top-4 right-4 z-[1000]"
            >
                <button
                    onClick={toggle3D}
                    className="rounded-xl px-4 py-3 border transition-all flex items-center gap-3 group cursor-pointer"
                    style={{
                        background: toggleBg,
                        borderColor: badgeBorder,
                        backdropFilter: 'blur(12px)',
                        WebkitBackdropFilter: 'blur(12px)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
                    }}
                >
                    <div className={cn("w-2.5 h-2.5 rounded-full transition-all duration-300", is3D ? "bg-orange-500 shadow-[0_0_12px_rgba(249,115,22,0.9)]" : "bg-blue-400 shadow-[0_0_12px_rgba(96,165,250,0.9)]")} />
                    <span className="text-xs font-bold uppercase tracking-widest" style={{ color: toggleText }}>
                        {is3D ? '3D Extrusion' : '2D Heatmap'}
                    </span>
                </button>
            </motion.div>
        </div>
    )
}

export default memo(SpreadMapView)