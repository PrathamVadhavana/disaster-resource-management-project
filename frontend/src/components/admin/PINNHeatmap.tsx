'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSpreadHeatmap } from '@/lib/api/workflow'
import type { VictimMarker } from '@/lib/api/workflow'
import { api } from '@/lib/api'
import {
    Flame, Loader2, Clock, MapPin, Play, Pause, SkipForward,
    Layers, Wind, Activity, ArrowRight, Maximize2, Minimize2,
    AlertTriangle, ChevronDown, Info, Gauge,
    Users, Eye, EyeOff, Zap, Droplets, Mountain,
    CloudLightning, Waves, TreePine
} from 'lucide-react'
import { cn } from '@/lib/utils'
import dynamic from 'next/dynamic'
import type { SpreadMapViewProps, VictimMarkerData } from './SpreadMapView'

// ─── Dynamically imported map (SSR-safe) ────────────────────────────────────
const SpreadMapView = dynamic<SpreadMapViewProps>(() => import('./SpreadMapView'), {
    ssr: false,
    loading: () => (
        <div className="h-[500px] rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
        </div>
    ),
})

// ─── Inferno-inspired perceptually uniform colormap ─────────────────────────
const INFERNO_STOPS = [
    [0, 0, 4],
    [40, 11, 84],
    [101, 21, 110],
    [159, 42, 99],
    [212, 72, 66],
    [245, 125, 21],
    [250, 193, 39],
    [252, 255, 164],
]

export function infernoColor(t: number, alpha: number = 1): string {
    const clamped = Math.max(0, Math.min(1, t))
    const segments = INFERNO_STOPS.length - 1
    const segIndex = Math.min(Math.floor(clamped * segments), segments - 1)
    const segFrac = (clamped * segments) - segIndex

    const [r1, g1, b1] = INFERNO_STOPS[segIndex]
    const [r2, g2, b2] = INFERNO_STOPS[segIndex + 1]

    const r = Math.round(r1 + (r2 - r1) * segFrac)
    const g = Math.round(g1 + (g2 - g1) * segFrac)
    const b = Math.round(b1 + (b2 - b1) * segFrac)

    return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// ─── Grid interpolation for smooth animation ────────────────────────────────
function lerpGrids(gridA: number[][], gridB: number[][], t: number): number[][] {
    if (!gridA.length || !gridB.length) return gridA || gridB || []
    const clamped = Math.max(0, Math.min(1, t))
    return gridA.map((row, i) =>
        row.map((valA, j) => {
            const valB = gridB[i]?.[j] ?? valA
            return valA + (valB - valA) * clamped
        })
    )
}

// ─── Canvas heatmap renderer ────────────────────────────────────────────────
export function gridToCanvasDataUrl(
    grid: number[][],
    width: number = 512,
    height: number = 512,
    drawContours: boolean = true,
): string {
    if (typeof document === 'undefined') return ''
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return ''

    const rows = grid.length
    const cols = grid[0]?.length || 0
    if (!rows || !cols) return ''

    const cellW = width / cols
    const cellH = height / rows

    ctx.filter = 'blur(12px)'

    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            const val = grid[i][j]
            const alpha = val < 0.02 ? 0 : Math.max(0.15, Math.min(0.88, val * 0.9 + 0.05))
            ctx.fillStyle = infernoColor(val, alpha)
            const yPos = (rows - 1 - i) * cellH
            ctx.fillRect(j * cellW, yPos, cellW + 1, cellH + 1)
        }
    }

    ctx.filter = 'none'

    if (drawContours && rows > 2 && cols > 2) {
        const contourThresholds = [0.25, 0.5, 0.75]
        const contourColors = [
            'rgba(255,255,255,0.3)',
            'rgba(255,255,255,0.5)',
            'rgba(255,255,255,0.7)',
        ]

        contourThresholds.forEach((threshold, tIdx) => {
            ctx.strokeStyle = contourColors[tIdx]
            ctx.lineWidth = 1.5
            ctx.setLineDash([4, 3])
            ctx.beginPath()

            for (let i = 0; i < rows - 1; i++) {
                for (let j = 0; j < cols - 1; j++) {
                    const tl = grid[i][j]
                    const tr = grid[i][j + 1]
                    const bl = grid[i + 1][j]
                    const br = grid[i + 1][j + 1]

                    const edges: [number, number, number, number][] = []
                    const canvasY = (idx: number) => (rows - 1 - idx) * cellH

                    if ((tl < threshold) !== (tr < threshold)) {
                         const frac = (threshold - tl) / (tr - tl)
                         edges.push([
                             (j + frac) * cellW, canvasY(i+1),
                             (j + frac) * cellW, canvasY(i+1),
                         ])
                     }
                     if ((tl < threshold) !== (bl < threshold)) {
                         const frac = (threshold - bl) / (tl - bl)
                         edges.push([
                             j * cellW, canvasY(i + frac),
                             j * cellW, canvasY(i + frac),
                         ])
                     }
                     if ((bl < threshold) !== (br < threshold)) {
                         const frac = (threshold - bl) / (br - bl)
                         edges.push([
                             (j + frac) * cellW, canvasY(i),
                             (j + frac) * cellW, canvasY(i),
                         ])
                     }
                     if ((tr < threshold) !== (br < threshold)) {
                         const frac = (threshold - br) / (tr - br)
                         edges.push([
                             (j + 1) * cellW, canvasY(i + frac),
                             (j + 1) * cellW, canvasY(i + frac),
                         ])
                     }

                    if (edges.length >= 2) {
                        ctx.moveTo(edges[0][0], edges[0][1])
                        ctx.lineTo(edges[1][0], edges[1][1])
                    }
                }
            }
            ctx.stroke()
            ctx.setLineDash([])
        })
    }

    return canvas.toDataURL('image/png')
}

// ─── Disaster type icons & colors ────────────────────────────────────────────
const DISASTER_TYPE_META: Record<string, { icon: any; color: string; bg: string }> = {
    earthquake: { icon: Mountain, color: 'text-amber-500', bg: 'bg-amber-500/10' },
    flood: { icon: Droplets, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    hurricane: { icon: Wind, color: 'text-cyan-500', bg: 'bg-cyan-500/10' },
    tornado: { icon: Wind, color: 'text-purple-500', bg: 'bg-purple-500/10' },
    wildfire: { icon: Flame, color: 'text-red-500', bg: 'bg-red-500/10' },
    tsunami: { icon: Waves, color: 'text-teal-500', bg: 'bg-teal-500/10' },
    drought: { icon: TreePine, color: 'text-yellow-600', bg: 'bg-yellow-500/10' },
    landslide: { icon: Mountain, color: 'text-stone-500', bg: 'bg-stone-500/10' },
    volcano: { icon: Flame, color: 'text-orange-600', bg: 'bg-orange-500/10' },
    other: { icon: CloudLightning, color: 'text-slate-500', bg: 'bg-slate-500/10' },
}

// ─── Types ──────────────────────────────────────────────────────────────────
interface ActiveDisaster {
    id: string
    title: string
    type: string
    severity: string
    locations?: { latitude: number; longitude: number; name: string }
    latitude?: number
    longitude?: number
    location_name?: string
    status?: string
    affected_population?: number
}

interface PINNHeatmapProps {
    latitude?: number
    longitude?: number
    disasterId?: string
}

// ─── Main Component ─────────────────────────────────────────────────────────
export function PINNHeatmap({ latitude, longitude, disasterId }: PINNHeatmapProps) {
    // State
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(6)
    const [isExpanded, setIsExpanded] = useState(false)
    const [showContours, setShowContours] = useState(true)
    const [selectedDisasterId, setSelectedDisasterId] = useState<string | null>(disasterId || null)
    const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number; val: number; lat: number; lon: number } | null>(null)
    const [showDisasterPicker, setShowDisasterPicker] = useState(false)
    const [showMarkers, setShowMarkers] = useState(true)
    const [filterType, setFilterType] = useState<string | null>(null)
    const animFrameRef = useRef<number>(0)
    const lastTimeRef = useRef<number>(0)

    // Fetch active disasters
    const { data: disastersRaw } = useQuery({
        queryKey: ['disasters-for-spread'],
        queryFn: async () => {
            const data = await api.getDisasters({ status: 'active,monitoring', limit: 50 })
            return (Array.isArray(data) ? data : data?.disasters ?? []) as ActiveDisaster[]
        },
        staleTime: 60000,
    })

    const disasters = disastersRaw || []

    // Group disasters by type for the picker
    const disastersByType = useMemo(() => {
        const groups: Record<string, ActiveDisaster[]> = {}
        const filteredDisasters = filterType
            ? disasters.filter(d => d.type === filterType)
            : disasters
        for (const d of filteredDisasters) {
            const type = d.type || 'other'
            if (!groups[type]) groups[type] = []
            groups[type].push(d)
        }
        return groups
    }, [disasters, filterType])

    // Unique disaster types for filter tabs
    // Ensure all standard types are available for filtering even if not present in the current data
    const ALL_TYPES = ['earthquake', 'flood', 'hurricane', 'wildfire', 'other']

    const disasterTypes = useMemo(() => {
        const types = new Set<string>(ALL_TYPES)
        disasters.forEach(d => { if (d.type) types.add(d.type.toLowerCase()) })
        return Array.from(types).sort()
    }, [disasters])

    // Auto-select most critical active disaster if none provided on MOUNT
    const activeDisaster = useMemo(() => {
        if (!selectedDisasterId && status === 'success' && disasters.length > 0 && !disasterId) {
             // We don't auto-set here to keep selectedDisasterId null if user wants "All Disasters"
             // But we need a way to distinguish initial mount from explicit null choice.
             // For now, let's just say: if no ID, show ALL.
             return null
        }
        return disasters.find(d => d.id === selectedDisasterId) || null
    }, [disasters, selectedDisasterId, disasterId])

    // Resolve lat/lon from disaster or prop
    const resolvedLat = useMemo(() => {
        if (latitude) return latitude
        if (activeDisaster?.locations?.latitude) return activeDisaster.locations.latitude
        if (activeDisaster?.latitude) return activeDisaster.latitude
        // Use New Delhi as absolute fallback, but backend now auto-centers correctly
        return 28.6
    }, [latitude, activeDisaster])

    const resolvedLon = useMemo(() => {
        if (longitude) return longitude
        if (activeDisaster?.locations?.longitude) return activeDisaster.locations.longitude
        if (activeDisaster?.longitude) return activeDisaster.longitude
        return 77.2
    }, [longitude, activeDisaster])

    const horizonValues = [6, 12, 24]

    // Fetch heatmap data
    const { data, isLoading } = useQuery({
        queryKey: ['pinn-heatmap', resolvedLat, resolvedLon, selectedDisasterId],
        queryFn: () => getSpreadHeatmap({
            latitude: resolvedLat,
            longitude: resolvedLon,
            horizons: horizonValues,
            resolution: 40,
            disaster_id: selectedDisasterId || undefined,
        }),
        staleTime: 60000,
        refetchInterval: 120000,
    })

    // Derived risk score [0-100]
    const riskScore = useMemo(() => {
        const statsObj = (data as any)?.metadata || {}
        const total = statsObj.cluster_requests || 0
        if (total === 0) return 0
        const base = Math.min(100, total * 12)
        const densityFactor = (data as any)?.max_intensity || 0.8
        return Math.round(base * densityFactor)
    }, [data])

    // Victim markers from data
    const victimMarkers = useMemo(() => {
        return (data?.victim_markers || []) as VictimMarker[]
    }, [data])

    const victimStats = useMemo(() => {
        const markers = victimMarkers
        const meta = (data as any)?.metadata || {}
        
        let food = 0, water = 0, medical = 0, cloth = 0, other = 0, critical = 0
        markers.forEach(m => {
            const type = m.resource_type?.toLowerCase() || ''
            if (type.includes('food')) food++
            else if (type.includes('water')) water++
            else if (type.includes('medic') || type.includes('blood')) medical++
            else if (type.includes('cloth')) cloth++
            else other++

            if (m.priority === 'critical' || m.priority === 'urgent') critical++
        })

        return {
            total: markers.length,
            globalTotal: meta.global_requests || markers.length,
            totalPeople: meta.cluster_people || markers.reduce((acc: number, m: any) => acc + (m.head_count || 0), 0),
            globalPeople: meta.global_people || 0,
            food, water, medical, cloth, other, critical,
            isGlobal: meta.is_global_view ?? !selectedDisasterId
        }
    }, [victimMarkers, data, selectedDisasterId])

    // Victim stats summary
    // (Note: victimStats is now defined above using enriched metadata)

    // Extract grids for each horizon
    const grids = useMemo(() => {
        const result: Record<number, number[][]> = {}
        if (data?.horizons) {
            for (const key of Object.keys(data.horizons)) {
                const match = key.match(/T\+(\d+)h/)
                if (match) {
                    result[parseInt(match[1])] = data.horizons[key].grid || []
                }
            }
        }
        return result
    }, [data])

    // Compute current interpolated grid
    const currentGrid = useMemo(() => {
        const hours = [6, 12, 24]
        if (currentTime <= 6) return grids[6] || []
        if (currentTime >= 24) return grids[24] || []

        for (let i = 0; i < hours.length - 1; i++) {
            if (currentTime >= hours[i] && currentTime <= hours[i + 1]) {
                const gridA = grids[hours[i]]
                const gridB = grids[hours[i + 1]]
                if (!gridA || !gridB) return gridA || gridB || []
                const t = (currentTime - hours[i]) / (hours[i + 1] - hours[i])
                return lerpGrids(gridA, gridB, t)
            }
        }
        return grids[6] || []
    }, [grids, currentTime])

    // Current horizon physics (closest)
    const currentPhysics = useMemo(() => {
        if (!data?.horizons) return null
        const closest = currentTime <= 9 ? 'T+6h' : currentTime <= 18 ? 'T+12h' : 'T+24h'
        return data.horizons[closest]?.learned_physics || null
    }, [data, currentTime])

    // Compute bounds for the viewport
    const viewportBounds = useMemo(() => {
        if (data?.horizons) {
            const firstKey = Object.keys(data.horizons)[0]
            const h = data.horizons[firstKey]
            if (h.grid?.length > 0) {
                return {
                    xRange: h.x_range as [number, number],
                    yRange: h.y_range as [number, number],
                }
            }
        }
        const offset = ((data?.dynamic_reach_km || 50) / 111) * 1.5
        return {
            xRange: [resolvedLon - offset, resolvedLon + offset] as [number, number],
            yRange: [resolvedLat - offset, resolvedLat + offset] as [number, number],
        }
    }, [data, resolvedLat, resolvedLon])

    // Use center from server response if available (centroid of victim requests)
    const mapCenter = useMemo<[number, number]>(() => {
        if (data?.center) {
            return [data.center.latitude, data.center.longitude]
        }
        return [resolvedLat, resolvedLon]
    }, [data, resolvedLat, resolvedLon])

    // Animation loop
    useEffect(() => {
        if (!isPlaying) return

        let rafId: number
        const animate = (timestamp: number) => {
            if (!lastTimeRef.current) lastTimeRef.current = timestamp
            const delta = timestamp - lastTimeRef.current

            if (delta > 80) {
                lastTimeRef.current = timestamp
                setCurrentTime(prev => {
                    const next = prev + 0.3
                    if (next > 24) {
                        setIsPlaying(false)
                        return 6
                    }
                    return next
                })
            }
            rafId = requestAnimationFrame(animate)
        }

        rafId = requestAnimationFrame(animate)
        return () => {
            cancelAnimationFrame(rafId)
            lastTimeRef.current = 0
        }
    }, [isPlaying])

    // Compute heatmap canvas URL
    const canvasDataUrl = useMemo(() => {
        if (!currentGrid.length) return ''
        return gridToCanvasDataUrl(currentGrid, 512, 512, showContours)
    }, [currentGrid, showContours])

    // Compute x/y range from data
    const bounds = useMemo(() => {
        if (!data?.horizons) return null
        const firstKey = Object.keys(data.horizons)[0]
        if (!firstKey) return null
        const h = data.horizons[firstKey]
        return {
            xRange: h.x_range as [number, number],
            yRange: h.y_range as [number, number],
        }
    }, [data])

    // Compute stats
    const stats = useMemo(() => {
        if (!currentGrid.length) return { maxIntensity: 0, avgIntensity: 0, affectedCells: 0, totalCells: 0 }
        let max = 0, sum = 0, affected = 0, total = 0
        for (const row of currentGrid) {
            for (const val of row) {
                total++
                if (val > max) max = val
                sum += val
                if (val > 0.2) affected++
            }
        }
        return {
            maxIntensity: max,
            avgIntensity: total ? sum / total : 0,
            affectedCells: affected,
            totalCells: total,
            affectedPct: total ? Math.round((affected / total) * 100) : 0,
        }
    }, [currentGrid])

    const getCardinalDirection = useCallback((angle: number) => {
        const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        return directions[Math.round(angle / 45) % 8]
    }, [])

    // Human-readable physics
    const physicsDisplay = useMemo(() => {
        if (!currentPhysics) return null
        const diffusion = currentPhysics.diffusion ?? 0
        const velocity = currentPhysics.velocity || [0, 0]
        const speedKmH = (diffusion * 111 / 6).toFixed(1)
        const windAngle = Math.atan2(velocity[1], velocity[0]) * (180 / Math.PI)
        const windSpeed = Math.sqrt(velocity[0] ** 2 + velocity[1] ** 2)
        const direction = getCardinalDirection(windAngle)

        return {
            speedKmH,
            windAngle,
            windSpeed: (windSpeed * 111).toFixed(2),
            direction,
            rawDiffusion: diffusion.toFixed(3),
            rawVelocity: velocity.map((v: number) => v.toFixed(4)),
        }
    }, [currentPhysics, getCardinalDirection])

    const handleCellHover = useCallback((row: number, col: number, val: number) => {
        if (!bounds || !currentGrid.length) return
        const rows = currentGrid.length
        const cols = currentGrid[0].length
        const lat = bounds.yRange[0] + (bounds.yRange[1] - bounds.yRange[0]) * (1 - row / (rows - 1))
        const lon = bounds.xRange[0] + (bounds.xRange[1] - bounds.xRange[0]) * (col / (cols - 1))
        setHoveredCell({ row, col, val, lat, lon })
    }, [bounds, currentGrid])

    return (
        <div className={cn(
            "rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 overflow-hidden transition-all duration-300",
            isExpanded && "fixed inset-4 z-50 shadow-2xl"
        )}>
            {/* Expanded backdrop */}
            {isExpanded && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[-1]" onClick={() => setIsExpanded(false)} />
            )}

            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-100 dark:border-white/5 bg-gradient-to-r from-orange-50/50 to-red-50/50 dark:from-orange-500/5 dark:to-red-500/5">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/20">
                            <Flame className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h3 className="font-bold text-slate-900 dark:text-white text-sm">
                                PINN Spread Prediction
                            </h3>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                Physics-informed neural network — disaster spread over time
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* Disaster selector */}
                        <div className="relative">
                            <button
                                onClick={() => setShowDisasterPicker(!showDisasterPicker)}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-orange-300 dark:hover:border-orange-500/30 transition-colors"
                            >
                                {activeDisaster ? (
                                    <>
                                        {(() => {
                                            const meta = DISASTER_TYPE_META[activeDisaster.type] || DISASTER_TYPE_META.other
                                            const TypeIcon = meta.icon
                                            return <TypeIcon className={cn("w-3.5 h-3.5", meta.color)} />
                                        })()}
                                        <span className="max-w-[120px] truncate">{activeDisaster.title || activeDisaster.type}</span>
                                    </>
                                ) : (
                                    <>
                                        <AlertTriangle className="w-3 h-3 text-orange-500" />
                                        <span>Select Disaster</span>
                                    </>
                                )}
                                <ChevronDown className={cn("w-3 h-3 transition-transform", showDisasterPicker && "rotate-180")} />
                            </button>
                            {showDisasterPicker && (
                                <>
                                    <div className="fixed inset-0 z-10" onClick={() => setShowDisasterPicker(false)} />
                                    <div className="absolute right-0 top-full mt-1 w-80 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-2xl z-20 overflow-hidden">
                                        {/* Type filter tabs */}
                                        {disasterTypes.length > 1 && (
                                            <div className="p-2 border-b border-slate-100 dark:border-white/5 flex flex-wrap gap-1">
                                                <button
                                                    onClick={() => setFilterType(null)}
                                                    className={cn(
                                                        "px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-colors",
                                                        !filterType
                                                            ? "bg-orange-500 text-white"
                                                            : "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600"
                                                    )}
                                                >
                                                    All ({disasters.length})
                                                </button>
                                                {disasterTypes.map(type => {
                                                    const meta = DISASTER_TYPE_META[type] || DISASTER_TYPE_META.other
                                                    const TypeIcon = meta.icon
                                                    const count = disasters.filter(d => d.type === type).length
                                                    return (
                                                        <button
                                                            key={type}
                                                            onClick={() => setFilterType(filterType === type ? null : type)}
                                                            className={cn(
                                                                "px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-colors flex items-center gap-1",
                                                                filterType === type
                                                                    ? "bg-orange-500 text-white"
                                                                    : cn("text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600", meta.bg)
                                                            )}
                                                        >
                                                            <TypeIcon className="w-3 h-3" />
                                                            {type} ({count})
                                                        </button>
                                                    )
                                                })}
                                            </div>
                                        )}

                                        {/* "All Disasters" option */}
                                        <button
                                            onClick={() => {
                                                setSelectedDisasterId(null)
                                                setShowDisasterPicker(false)
                                            }}
                                            className={cn(
                                                "w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-white/5 border-b border-slate-100 dark:border-white/5",
                                                !selectedDisasterId && "bg-gradient-to-r from-orange-50 to-red-50 dark:from-orange-500/10 dark:to-red-500/10"
                                            )}
                                        >
                                            <div className="flex items-center gap-2">
                                                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
                                                    <Zap className="w-3 h-3 text-white" />
                                                </div>
                                                <span className="font-bold text-slate-900 dark:text-white">All Disasters</span>
                                                <span className="text-[10px] text-slate-400 ml-auto">Global view</span>
                                            </div>
                                            <p className="text-[11px] text-slate-500 mt-0.5 ml-8">
                                                Show all victim requests across all disasters
                                            </p>
                                        </button>

                                        {/* Disaster list grouped by type */}
                                        <div className="max-h-64 overflow-y-auto py-1">
                                            {Object.keys(disastersByType).length === 0 ? (
                                                <div className="px-4 py-8 text-center bg-slate-50/50 dark:bg-white/[0.01]">
                                                    <div className="w-12 h-12 rounded-full border-2 border-slate-200 dark:border-white/10 flex items-center justify-center mx-auto mb-3">
                                                        <Activity className="w-6 h-6 text-slate-300 dark:text-slate-600" />
                                                    </div>
                                                    <p className="text-sm font-bold text-slate-600 dark:text-slate-400">No Active Disaster Found</p>
                                                    <p className="text-[11px] text-slate-400 mt-1 max-w-[200px] mx-auto">
                                                        Currently showing global monitoring view of all victim requests.
                                                    </p>
                                                    <div className="mt-4 flex flex-wrap justify-center gap-1.5 opacity-60">
                                                        {ALL_TYPES.map(t => {
                                                            const meta = DISASTER_TYPE_META[t] || DISASTER_TYPE_META.other
                                                            const Icon = meta.icon
                                                            return (
                                                                <div key={t} className={cn("flex items-center gap-1 px-2 py-1 rounded-md border", meta.bg, meta.color)}>
                                                                    <Icon className="w-3 h-3" />
                                                                    <span className="text-[9px] font-bold uppercase">{t}</span>
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                </div>
                                            ) : (
                                                Object.entries(disastersByType).map(([type, typeDisasters]) => {
                                                    const meta = DISASTER_TYPE_META[type] || DISASTER_TYPE_META.other
                                                    const TypeIcon = meta.icon
                                                    return (
                                                        <div key={type}>
                                                            {!filterType && Object.keys(disastersByType).length > 1 && (
                                                                <div className="px-4 py-1.5 flex items-center gap-1.5 bg-slate-50 dark:bg-white/[0.02]">
                                                                    <TypeIcon className={cn("w-3 h-3", meta.color)} />
                                                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                                                        {type} ({typeDisasters.length})
                                                                    </span>
                                                                </div>
                                                            )}
                                                            {typeDisasters.map(d => {
                                                                const sevColor = d.severity === 'critical' ? 'bg-red-500' :
                                                                    d.severity === 'high' ? 'bg-orange-500' :
                                                                        d.severity === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                                                                const sevTextColor = d.severity === 'critical' ? 'text-red-600 dark:text-red-400' :
                                                                    d.severity === 'high' ? 'text-orange-600 dark:text-orange-400' :
                                                                        d.severity === 'medium' ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400'
                                                                return (
                                                                    <button
                                                                        key={d.id}
                                                                        onClick={() => {
                                                                            setSelectedDisasterId(d.id)
                                                                            setShowDisasterPicker(false)
                                                                        }}
                                                                        className={cn(
                                                                            "w-full text-left px-4 py-2.5 text-sm transition-all hover:bg-slate-50 dark:hover:bg-white/5",
                                                                            selectedDisasterId === d.id && "bg-orange-50 dark:bg-orange-500/10 border-l-2 border-orange-500"
                                                                        )}
                                                                    >
                                                                        <div className="flex items-center gap-2">
                                                                            <span className={cn("w-2 h-2 rounded-full shrink-0", sevColor)} />
                                                                            <span className="font-medium text-slate-900 dark:text-white truncate flex-1">
                                                                                {d.title || d.type}
                                                                            </span>
                                                                            <span className={cn("text-[10px] font-bold uppercase", sevTextColor)}>{d.severity}</span>
                                                                        </div>
                                                                    </button>
                                                                )
                                                            })}
                                                        </div>
                                                    )
                                                })
                                            )}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Show/hide victim markers toggle */}
                        <button
                            onClick={() => setShowMarkers(!showMarkers)}
                            className={cn(
                                "p-2 rounded-lg text-xs font-medium transition-all relative",
                                showMarkers
                                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400"
                                    : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                            )}
                            title={showMarkers ? "Hide victim markers" : "Show victim markers"}
                        >
                            {showMarkers ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                            {victimStats.total > 0 && showMarkers && (
                                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-orange-500 text-white text-[8px] font-bold flex items-center justify-center">
                                    {victimStats.total > 99 ? '99+' : victimStats.total}
                                </span>
                            )}
                        </button>

                        {/* Contour toggle */}
                        <button
                            onClick={() => setShowContours(!showContours)}
                            className={cn(
                                "p-2 rounded-lg text-xs font-medium transition-colors",
                                showContours
                                    ? "bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400"
                                    : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                            )}
                            title="Toggle contour lines"
                        >
                            <Layers className="w-4 h-4" />
                        </button>

                        {/* Expand */}
                        <button
                            onClick={() => setIsExpanded(!isExpanded)}
                            className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                            title={isExpanded ? "Minimize" : "Maximize"}
                        >
                            {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                        </button>
                    </div>
                </div>

                {/* Active disaster info bar */}
                {activeDisaster && (
                    <div className="mt-3 flex items-center gap-4 text-[11px]">
                        <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
                            <MapPin className="w-3 h-3" />
                            {activeDisaster.locations?.name || activeDisaster.location_name || `${resolvedLat.toFixed(2)}°, ${resolvedLon.toFixed(2)}°`}
                        </span>
                        <span className={cn(
                            "px-2 py-0.5 rounded-full font-bold uppercase",
                            activeDisaster.severity === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                activeDisaster.severity === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                    'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                        )}>
                            {activeDisaster.severity || 'medium'}
                        </span>
                        <span className="text-slate-400 capitalize">
                            {(() => {
                                const type = activeDisaster?.type || 'other'
                                const meta = DISASTER_TYPE_META[type] || DISASTER_TYPE_META.other
                                const TypeIcon = meta.icon
                                return <TypeIcon className={cn("w-3 h-3 inline mr-1", meta.color)} />
                            })()}
                            {activeDisaster?.type || 'Searching...'}
                        </span>
                        {victimStats.total > 0 && (
                            <span className="flex items-center gap-1 text-orange-500 dark:text-orange-400 font-semibold ml-auto">
                                <Users className="w-3 h-3" />
                                {victimStats.total} requests • {victimStats.totalPeople} people
                                {victimStats.critical > 0 && (
                                    <span className="text-red-500 dark:text-red-400 ml-1">
                                        ({victimStats.critical} critical)
                                    </span>
                                )}
                            </span>
                        )}
                    </div>
                )}

                {/* No disaster but showing all */}
                {!activeDisaster && !selectedDisasterId && (
                    <div className="mt-3 flex items-center gap-2 text-[11px]">
                        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-gradient-to-r from-orange-500/10 to-red-500/10 border border-orange-500/20 shadow-sm shadow-orange-500/5">
                            <Zap className="w-3 h-3 text-orange-500" />
                            <span className="font-bold text-orange-600 dark:text-orange-400">GLOBAL VIEW</span>
                        </div>
                        <Activity className="w-3.5 h-3.5 text-orange-500 animate-pulse" />
                        <span className="text-slate-400 text-[10px]">
                            {victimStats.isGlobal 
                                ? `Situational Awareness: Analyzing ${victimStats.total} / ${victimStats.globalTotal} system requests`
                                : `Targeted Analysis: Focusing on the primary disaster cluster`
                            }
                        </span>
                    </div>
                )}
            </div>

            {/* Stats row */}
            {currentGrid.length > 0 && (
                <div className="grid grid-cols-4 gap-px bg-slate-100 dark:bg-white/5">
                    {[
                        { label: 'Max Intensity', value: `${(stats.maxIntensity * 100).toFixed(0)}%`, icon: Gauge, color: 'text-red-600 dark:text-red-400' },
                        { label: 'Area Affected', value: `${stats.affectedPct}%`, icon: Activity, color: 'text-orange-600 dark:text-orange-400' },
                        { label: 'Time Horizon', value: `T+${currentTime.toFixed(1)}h`, icon: Clock, color: 'text-blue-600 dark:text-blue-400' },
                        { label: 'Victim Requests', value: `${victimStats.total}`, icon: Users, color: 'text-purple-600 dark:text-purple-400' },
                    ].map((s, i) => (
                        <div key={i} className="bg-white dark:bg-slate-900 px-4 py-3">
                            <div className="flex items-center gap-1.5 mb-1">
                                <s.icon className={cn("w-3 h-3", s.color)} />
                                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{s.label}</span>
                            </div>
                            <p className={cn("text-lg font-black tabular-nums", s.color)}>{s.value}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* Map + Heatmap */}
            <div className="relative">
                <SpreadMapView
                    center={mapCenter}
                    bounds={viewportBounds}
                    canvasDataUrl={canvasDataUrl}
                    grid={currentGrid}
                    height={isExpanded ? 'calc(100vh - 340px)' : '500px'}
                    onCellHover={handleCellHover}
                    onCellLeave={() => setHoveredCell(null)}
                    epicenters={(data as any)?.epicenters || []}
                    victimMarkers={victimMarkers as VictimMarkerData[]}
                    showMarkers={showMarkers}
                />

                {/* Loading / Scanning overlay when switching disasters */}
                {isLoading && (
                    <div className="absolute inset-0 z-[1001] bg-slate-900/20 backdrop-blur-[1px] flex flex-col items-center justify-center pointer-events-none">
                        <div className="relative">
                            <div className="w-24 h-24 rounded-full border-4 border-orange-500/20 border-t-orange-500 animate-spin" />
                            <div className="absolute inset-0 flex items-center justify-center">
                                <Activity className="w-8 h-8 text-orange-500 animate-pulse" />
                            </div>
                        </div>
                        <div className="mt-4 px-4 py-2 rounded-lg bg-slate-900/80 border border-white/10 text-white text-[10px] font-bold uppercase tracking-widest animate-pulse">
                            Scanning Area for Victim Clusters...
                        </div>
                    </div>
                )}

                {/* No Data Fallback */}
                {!isLoading && currentGrid.length === 0 && (
                    <div className="absolute inset-0 z-[1002] flex flex-col items-center justify-center bg-slate-50/50 dark:bg-slate-900/50 backdrop-blur-sm gap-2">
                        <Flame className="w-8 h-8 text-slate-300 dark:text-slate-600" />
                        <p className="text-sm text-slate-400">No heatmap data available</p>
                        <p className="text-xs text-slate-400">Select an active disaster above</p>
                    </div>
                )}

                {/* Floating tooltip */}
                {hoveredCell && (
                    <div className="absolute top-4 right-4 z-[1005] bg-slate-900/90 backdrop-blur-sm text-white rounded-xl p-3 shadow-2xl border border-white/10 min-w-[180px] pointer-events-none">
                        <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/10">
                            <div
                                className="w-4 h-4 rounded-md border border-white/20"
                                style={{ backgroundColor: infernoColor(hoveredCell.val) }}
                            />
                            <span className="font-bold text-sm">Intensity: {(hoveredCell.val * 100).toFixed(0)}%</span>
                        </div>
                        <div className="space-y-1 text-[11px] text-slate-300">
                            <p className="flex justify-between">
                                <span className="text-slate-400">Lat:</span>
                                <span className="font-mono">{hoveredCell.lat.toFixed(4)}°</span>
                            </p>
                            <p className="flex justify-between">
                                <span className="text-slate-400">Lon:</span>
                                <span className="font-mono">{hoveredCell.lon.toFixed(4)}°</span>
                            </p>
                            <p className="flex justify-between">
                                <span className="text-slate-400">Risk Level:</span>
                                <span className={cn("font-bold",
                                    hoveredCell.val >= 0.75 ? "text-red-400" :
                                        hoveredCell.val >= 0.5 ? "text-orange-400" :
                                            hoveredCell.val >= 0.25 ? "text-yellow-400" :
                                                "text-green-400"
                                )}>
                                    {hoveredCell.val >= 0.75 ? 'CRITICAL' :
                                        hoveredCell.val >= 0.5 ? 'HIGH' :
                                            hoveredCell.val >= 0.25 ? 'MODERATE' :
                                                'LOW'}
                                </span>
                            </p>
                        </div>
                    </div>
                )}

                        {/* Floating color legend */}
                        <div className="absolute bottom-4 left-4 z-[1000] bg-white/90 dark:bg-slate-900/90 backdrop-blur-sm rounded-xl p-3 shadow-xl border border-slate-200 dark:border-white/10">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Spread Intensity</p>
                            <div className="flex items-end gap-0.5 h-16">
                                {Array.from({ length: 30 }, (_, i) => {
                                    const t = i / 29
                                    return (
                                        <div
                                            key={i}
                                            className="w-2 rounded-t-sm"
                                            style={{
                                                height: `${20 + t * 80}%`,
                                                backgroundColor: infernoColor(t),
                                            }}
                                        />
                                    )
                                })}
                            </div>
                            <div className="flex justify-between mt-1">
                                <span className="text-[9px] text-slate-400">0%</span>
                                <span className="text-[9px] text-slate-400">25%</span>
                                <span className="text-[9px] text-slate-400">50%</span>
                                <span className="text-[9px] text-slate-400">75%</span>
                                <span className="text-[9px] text-slate-400">100%</span>
                            </div>
                            {showContours && (
                                <div className="mt-2 pt-2 border-t border-slate-200 dark:border-white/10 space-y-1">
                                    {[
                                        { label: '25% contour', dash: '4 3', opacity: 0.3 },
                                        { label: '50% contour', dash: '4 3', opacity: 0.5 },
                                        { label: '75% contour', dash: '4 3', opacity: 0.7 },
                                    ].map((c, i) => (
                                        <div key={i} className="flex items-center gap-2">
                                            <svg width="20" height="2" className="shrink-0">
                                                <line x1="0" y1="1" x2="20" y2="1" stroke="white" strokeWidth="1.5" strokeDasharray={c.dash} strokeOpacity={c.opacity} />
                                            </svg>
                                            <span className="text-[9px] text-slate-500">{c.label}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
            </div>

            {/* Playback Controls */}
            {currentGrid.length > 0 && (
                <div className="px-6 py-4 border-t border-slate-100 dark:border-white/5 bg-slate-50/50 dark:bg-white/[0.02]">
                    <div className="flex items-center gap-4">
                        {/* Play/Pause */}
                        <button
                            onClick={() => {
                                if (!isPlaying && currentTime >= 24) setCurrentTime(6)
                                setIsPlaying(!isPlaying)
                            }}
                            className={cn(
                                "w-10 h-10 rounded-xl flex items-center justify-center transition-all shadow-lg",
                                isPlaying
                                    ? "bg-orange-500 text-white shadow-orange-500/30 hover:bg-orange-600"
                                    : "bg-gradient-to-br from-orange-500 to-red-600 text-white shadow-orange-500/30 hover:shadow-orange-500/50"
                            )}
                        >
                            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                        </button>

                        {/* Time slider */}
                        <div className="flex-1">
                            <div className="relative">
                                <input
                                    type="range"
                                    min={6}
                                    max={24}
                                    step={0.1}
                                    value={currentTime}
                                    onChange={(e) => {
                                        setCurrentTime(parseFloat(e.target.value))
                                        setIsPlaying(false)
                                    }}
                                    className="w-full h-2 rounded-full appearance-none cursor-pointer
                                        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
                                        [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-orange-500
                                        [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-orange-500/30
                                        [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white
                                        [&::-webkit-slider-thumb]:cursor-pointer
                                        [&::-moz-range-thumb]:w-5 [&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:rounded-full
                                        [&::-moz-range-thumb]:bg-orange-500 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white"
                                    style={{
                                        background: `linear-gradient(to right, #f97316 0%, #f97316 ${((currentTime - 6) / 18) * 100}%, #e2e8f0 ${((currentTime - 6) / 18) * 100}%, #e2e8f0 100%)`,
                                    }}
                                />
                                {/* Tick marks */}
                                <div className="flex justify-between mt-1.5 px-0.5">
                                    {[6, 12, 18, 24].map(h => (
                                        <button
                                            key={h}
                                            onClick={() => { setCurrentTime(h); setIsPlaying(false) }}
                                            className={cn(
                                                "text-[10px] font-bold tabular-nums transition-colors cursor-pointer",
                                                Math.abs(currentTime - h) < 0.5
                                                    ? "text-orange-600 dark:text-orange-400"
                                                    : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                                            )}
                                        >
                                            T+{h}h
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Skip to end */}
                        <button
                            onClick={() => { setCurrentTime(24); setIsPlaying(false) }}
                            className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                            title="Skip to T+24h"
                        >
                            <SkipForward className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            )}

            {/* Physics & Model Info */}
            {(physicsDisplay || data) && (
                <div className="px-6 py-4 border-t border-slate-100 dark:border-white/5">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {/* Learned Physics */}
                        {physicsDisplay && (
                            <div className="rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-500/5 dark:to-indigo-500/5 border border-blue-100 dark:border-blue-500/10 p-4">
                                <div className="flex items-center gap-2 mb-3">
                                    <Wind className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                    <span className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider">Learned Physics</span>
                                </div>
                                <div className="flex items-center gap-4">
                                    {/* Directional arrow */}
                                    <div className="w-14 h-14 rounded-full bg-white dark:bg-slate-800 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center shadow-sm">
                                        <ArrowRight
                                            className="w-6 h-6 text-blue-600 dark:text-blue-400 transition-transform"
                                            style={{ transform: `rotate(${physicsDisplay?.windAngle || 0}deg)` }}
                                        />
                                    </div>
                                    <div className="flex-1 space-y-1.5">
                                        <p className="text-sm font-bold text-slate-900 dark:text-white">
                                            Spreading at ~{physicsDisplay?.speedKmH || 0} km/h
                                        </p>
                                        <p className="text-xs text-slate-500">
                                            Direction: {physicsDisplay?.direction || 'N/A'} • Drift: {physicsDisplay?.windSpeed || 0} km
                                        </p>
                                        <p className="text-[10px] font-mono text-slate-400">
                                            D={physicsDisplay?.rawDiffusion || 0} V=[{physicsDisplay?.rawVelocity?.join(', ') || '0, 0'}]
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Model info */}
                        <div className="rounded-xl bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-500/5 dark:to-pink-500/5 border border-purple-100 dark:border-purple-500/10 p-4">
                            <div className="flex items-center gap-2 mb-3">
                                <Info className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                <span className="text-xs font-bold text-purple-700 dark:text-purple-400 uppercase tracking-wider">Model Details</span>
                            </div>
                            <div className="space-y-2 text-xs">
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Model</span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300 uppercase">
                                        {data?.model || 'PINN'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Dynamic Reach</span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {data?.dynamic_reach_km ? Math.round(data.dynamic_reach_km) : 50} km
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Grid Resolution</span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {currentGrid.length}×{currentGrid[0]?.length || 0}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Center</span>
                                    <span className="font-mono font-medium text-slate-700 dark:text-slate-300">
                                        {mapCenter[0].toFixed(2)}°, {mapCenter[1].toFixed(2)}°
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Victim Markers</span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {victimStats.total} requests ({victimStats.totalPeople} people)
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

// ─── Helpers ────────────────────────────────────────────────────────────────
function getCardinalDirection(angle: number): string {
    const normalized = ((angle % 360) + 360) % 360
    const dirs = ['E', 'ENE', 'NE', 'NNE', 'N', 'NNW', 'NW', 'WNW', 'W', 'WSW', 'SW', 'SSW', 'S', 'SSE', 'SE', 'ESE']
    const index = Math.round(normalized / 22.5) % 16
    return dirs[index]
}
