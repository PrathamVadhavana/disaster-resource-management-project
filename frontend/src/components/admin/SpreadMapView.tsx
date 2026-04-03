'use client'

import { useEffect, useState, useCallback, memo, useMemo, useRef } from 'react'
import Map, { Source, Layer, Marker, Popup, NavigationControl, ViewStateChangeEvent, MapRef } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { cn } from '@/lib/utils'

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
                <circle cx="20" cy="20" r="18" fill="none" stroke="#ef4444" strokeWidth="2" strokeDasharray="4 2" opacity="0.6">
                    <animateTransform attributeName="transform" type="rotate" from="0 20 20" to="360 20 20" dur="8s" repeatCount="indefinite"/>
                </circle>
                <circle cx="20" cy="20" r="12" fill="none" stroke="#ef4444" strokeWidth="1.5" opacity="0.3">
                    <animate attributeName="r" values="8;16;8" dur="2s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2s" repeatCount="indefinite"/>
                </circle>
                <circle cx="20" cy="20" r="8" fill="#ef4444" opacity="0.8"/>
                <circle cx="20" cy="20" r="4" fill="white"/>
            </svg>
        </div>
    )
})

// ─── Victim Marker Component (Interactive) ───────────────────────────────────
function VictimMarkerItem({ marker }: { marker: VictimMarkerData }) {
    const [showPopup, setShowPopup] = useState(false)
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
                    setShowPopup(p => !p)
                }}
                style={{ zIndex: marker.priority === 'critical' ? 1000 : 0, cursor: 'pointer' }}
            >
                <div style={{ position: 'relative', width: 32, height: 38, transform: 'translate(0, 0)' }}>
                    <svg width="32" height="38" viewBox="0 0 32 38" xmlns="http://www.w3.org/2000/svg">
                        <path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 22 16 22s16-10 16-22C32 7.16 24.84 0 16 0z"
                              fill={priorityColor} opacity="0.9"/>
                        <circle cx="16" cy="14" r="10" fill="white" opacity="0.9"/>
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
                </div>
            </Marker>
            
            {showPopup && (
                <Popup
                    longitude={marker.longitude}
                    latitude={marker.latitude}
                    anchor="bottom"
                    offset={[0, -40]}
                    onClose={() => setShowPopup(false)}
                    closeOnClick={true}
                    className="victim-popup"
                    maxWidth="240px"
                    style={{ zIndex: 2000 }}
                >
                    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: '12px', lineHeight: 1.5, padding: '4px' }}>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            borderBottom: '1px solid #e2e8f0',
                            paddingBottom: '6px',
                            marginBottom: '6px',
                        }}>
                            <span style={{ fontSize: '18px' }}>{resourceIcon}</span>
                            <div>
                                <div style={{ fontWeight: 700, textTransform: 'capitalize', fontSize: '13px', color: '#0f172a' }}>
                                    {marker.resource_type}
                                </div>
                                <div style={{
                                    fontSize: '10px',
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
                            <p style={{ color: '#64748b', margin: '0 0 4px 0', fontSize: '11px' }}>
                                {marker.description}
                            </p>
                        )}
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#94a3b8' }}>
                            <span>👥 {marker.head_count} {marker.head_count > 1 ? 'people' : 'person'}</span>
                            <span style={{
                                padding: '1px 6px',
                                borderRadius: '4px',
                                background: marker.status === 'pending' ? '#fef3c7' : '#dcfce7',
                                color: marker.status === 'pending' ? '#92400e' : '#166534',
                                fontWeight: 600,
                                textTransform: 'capitalize',
                            }}>
                                {marker.status.replace(/_/g, ' ')}
                            </span>
                        </div>
                        <div style={{ fontSize: '9px', color: '#cbd5e1', marginTop: '4px', fontFamily: 'monospace' }}>
                            {marker.latitude.toFixed(4)}°, {marker.longitude.toFixed(4)}°
                        </div>
                    </div>
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
    const THRESHOLD = 0.15 

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
                    <VictimMarkerItem key={marker.id} marker={marker} />
                ))}
            </Map>

            {/* Subtle vignette overlay for premium look */}
            <div
                className="absolute inset-0 pointer-events-none z-[400]"
                style={{
                    boxShadow: 'inset 0 0 60px rgba(0,0,0,0.15)',
                    borderRadius: 'inherit',
                }}
            />

            {/* Victim markers count badge */}
            {showMarkers && victimMarkers.length > 0 && (
                <div className="absolute top-3 left-3 z-[1000] bg-slate-900/80 backdrop-blur-sm rounded-lg px-3 py-2 border border-white/10 shadow-xl">
                    <div className="flex items-center gap-2">
                        <span className="relative flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-orange-500"></span>
                        </span>
                        <span className="text-[11px] font-bold text-white tracking-wide">
                            {victimMarkers.length} ACTIVE {victimMarkers.length === 1 ? 'REQUEST' : 'REQUESTS'}
                        </span>
                    </div>
                </div>
            )}
            
            {/* 2D/3D Toggle Button */}
            <div className="absolute top-3 right-3 z-[1000]">
                <button
                    onClick={toggle3D}
                    className="bg-slate-900/80 hover:bg-slate-800 backdrop-blur-sm rounded-lg px-3 py-2 border border-white/10 shadow-xl transition-all flex items-center gap-2 group cursor-pointer"
                >
                    <div className={cn("w-2 h-2 rounded-full", is3D ? "bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.8)]" : "bg-blue-400")} />
                    <span className="text-[10px] font-bold text-white uppercase tracking-wider group-hover:text-orange-200 transition-colors">
                        {is3D ? '3D EXTRUSION ACTIVE' : '2D HEATMAP ACTIVE'}
                    </span>
                </button>
            </div>
        </div>
    )
}

export default memo(SpreadMapView)
