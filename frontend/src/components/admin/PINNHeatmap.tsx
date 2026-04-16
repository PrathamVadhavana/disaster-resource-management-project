'use client'

import { useState, useEffect, useCallback, useMemo, useRef, useDeferredValue } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSpreadHeatmap } from '@/lib/api/workflow'
import type { VictimMarker } from '@/lib/api/workflow'
import { api } from '@/lib/api'
import {
    Flame, Loader2, Clock, MapPin, Play, Pause, SkipForward, SkipBack,
    Layers, Wind, Activity, ArrowRight, Maximize2, Minimize2,
    AlertTriangle, ChevronDown, Info, Gauge, Repeat, Download,
    Users, Eye, EyeOff, Zap, Droplets, Mountain, BarChart2,
    CloudLightning, Waves, TreePine, Shirt
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
            const yPos = (rows - 1 - i) * cellH // Correct: Row 0 is South (Bottom)
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

                    const edges: [number, number][] = []
                    const canvasY = (idx: number) => (rows - 1 - idx) * cellH // Map to bottom-up canvas

                    if ((tl < threshold) !== (tr < threshold)) {
                        const frac = (threshold - tl) / (tr - tl)
                        edges.push([(j + frac) * cellW, canvasY(i)])
                    }
                    if ((tl < threshold) !== (bl < threshold)) {
                        const frac = (threshold - bl) / (tl - bl)
                        edges.push([j * cellW, canvasY(i + frac)])
                    }
                    if ((bl < threshold) !== (br < threshold)) {
                        const frac = (threshold - bl) / (br - bl)
                        edges.push([(j + frac) * cellW, canvasY(i + 1)])
                    }
                    if ((tr < threshold) !== (br < threshold)) {
                        const frac = (threshold - br) / (tr - br)
                        edges.push([(j + 1) * cellW, canvasY(i + frac)])
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

// ─── Resource type icons & colors ────────────────────────────────────────────
const RESOURCE_TYPE_META: Record<string, { icon: any; color: string; bg: string }> = {
    food: { icon: Activity, color: 'text-amber-500', bg: 'bg-amber-500/10' },
    water: { icon: Droplets, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    medical: { icon: Activity, color: 'text-red-500', bg: 'bg-red-500/10' },
    shelter: { icon: Mountain, color: 'text-purple-500', bg: 'bg-purple-500/10' },
    personnel: { icon: Users, color: 'text-teal-500', bg: 'bg-teal-500/10' },
    equipment: { icon: Zap, color: 'text-orange-600', bg: 'bg-orange-500/10' },
    evacuation: { icon: Wind, color: 'text-cyan-500', bg: 'bg-cyan-500/10' },
    clothing: { icon: Shirt, color: 'text-pink-500', bg: 'bg-pink-500/10' },
    other: { icon: CloudLightning, color: 'text-slate-500', bg: 'bg-slate-500/10' },
}

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
    const [selectedDisasterId, setSelectedDisasterId] = useState<string | null>(() => {
        if (disasterId) return disasterId
        if (typeof window !== 'undefined') return localStorage.getItem('spreadmap_disaster') || null
        return null
    })
    const [hoveredCell, setHoveredCell] = useState<{
        row: number; col: number; val: number; lat: number; lon: number; tti?: number | null;
    } | null>(null)

    // Auto-calculate tactical data for the center if not hovering
    const [centerTacticalData, setCenterTacticalData] = useState<{
        val: number; lat: number; lon: number; tti?: number | null;
    } | null>(null)

    const [showDisasterPicker, setShowDisasterPicker] = useState(false)
    const [showMarkers, setShowMarkers] = useState(true)
    const [filterType, setFilterType] = useState<string | null>(null)
    const [playSpeed, setPlaySpeed] = useState(1)
    const [loop, setLoop] = useState(false)
    const [showBreakdown, setShowBreakdown] = useState(false)
    const [showShortcuts, setShowShortcuts] = useState(false)
    const animFrameRef = useRef<number>(0)
    const lastTimeRef = useRef<number>(0)

    // Deferred time — lets the slider stay smooth while lerpGrids runs off the critical path
    const deferredTime = useDeferredValue(currentTime)

    // Persist selected disaster in localStorage so it survives page refresh
    const handleSelectDisaster = useCallback((id: string | null) => {
        setSelectedDisasterId(id)
        if (typeof window !== 'undefined') {
            if (id) localStorage.setItem('spreadmap_disaster', id)
            else localStorage.removeItem('spreadmap_disaster')
        }
        setShowDisasterPicker(false)
    }, [])

    // Fetch active requests instead of disasters
    const { data: requestsRaw } = useQuery({
        queryKey: ['requests-for-spread'],
        queryFn: async () => {
            // Fetch more requests but filter locally for maximum reliability
            const data = await api.getAdminRequests({ page_size: 100 } as any)
            return (data?.requests || data || []) as VictimMarkerData[]
        },
        staleTime: 60000,
        refetchOnWindowFocus: false,
    })

    const requests = Array.isArray(requestsRaw) ? requestsRaw : []

    // Fetch disasters to map disaster types to requests
    const { data: disastersRaw } = useQuery({
        queryKey: ['disasters-for-spread-requests'],
        queryFn: async () => {
            const data = await api.getDisasters({ limit: 100 })
            return (Array.isArray(data) ? data : data?.disasters ?? []) as any[]
        },
        staleTime: 60000,
        refetchOnWindowFocus: false,
    })

    const disasters = Array.isArray(disastersRaw) ? disastersRaw : []

    // Map disaster_id -> disaster info
    const disasterInfoMap = useMemo(() => {
        const mapping: Record<string, { name: string; type: string }> = {}
        disasters.forEach(d => {
            if (d.id) mapping[d.id] = {
                name: d.locations?.name || d.location_name || d.name || 'Unknown Zone',
                type: (d.type || 'other').toLowerCase()
            }
        })
        return mapping
    }, [disasters])

    const activeRequests = useMemo(() => {
        return requests.filter(r =>
            (r.status === 'pending' || r.status === 'in_progress') &&
            r.latitude !== null && r.latitude !== undefined &&
            r.longitude !== null && r.longitude !== undefined
        )
    }, [requests])

    // Group requests by resource type for better categorization
    const requestsByResource = useMemo(() => {
        const groups: Record<string, VictimMarkerData[]> = {}
        for (const r of activeRequests) {
            // Filter by resource type if a filter is active
            if (filterType) {
                if (r.resource_type?.toLowerCase() !== filterType.toLowerCase()) continue
            }

            const groupKey = (r.resource_type || 'other').toLowerCase()
            if (!groups[groupKey]) groups[groupKey] = []
            groups[groupKey].push(r)
        }
        return groups
    }, [activeRequests, filterType])

    // Unique resource types for filter tabs
    const requestTypes = useMemo(() => {
        const types = new Set<string>()
        activeRequests.forEach(r => {
            if (r.resource_type) types.add(r.resource_type.toLowerCase())
        })
        return Array.from(types).sort()
    }, [activeRequests])

    // Auto-select active request
    const activeRequest = useMemo(() => {
        if (!selectedDisasterId && requests.length > 0 && !disasterId) return null
        return requests.find(r => r.id === selectedDisasterId) || null
    }, [requests, selectedDisasterId, disasterId])

    // Resolve lat/lon from request or prop
    const resolvedLat = useMemo(() => {
        if (latitude) return latitude
        if (activeRequest?.latitude) return activeRequest.latitude
        return 28.6
    }, [latitude, activeRequest])

    const resolvedLon = useMemo(() => {
        if (longitude) return longitude
        if (activeRequest?.longitude) return activeRequest.longitude
        return 77.2
    }, [longitude, activeRequest])

    const currentDisasterId = useMemo(() => activeRequest?.disaster_id || disasterId, [activeRequest, disasterId])

    const horizonValues = [6, 12, 24]

    // Fetch heatmap data
    const { data, isLoading } = useQuery({
        queryKey: ['pinn-heatmap', resolvedLat, resolvedLon, currentDisasterId, filterType],
        queryFn: () => getSpreadHeatmap({
            latitude: resolvedLat,
            longitude: resolvedLon,
            horizons: horizonValues,
            resolution: 60,
            disaster_id: currentDisasterId || undefined,
            // Bypass the missing property error safely:
            ...({ resource_type: filterType || undefined } as any)
        }),
        staleTime: 60000,
        refetchInterval: 120000,
        refetchOnWindowFocus: false,
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

    // Compute current interpolated grid (uses deferredTime so the slider stays responsive)
    const currentGrid = useMemo(() => {
        const hours = [6, 12, 24]
        if (deferredTime <= 6) return grids[6] || []
        if (deferredTime >= 24) return grids[24] || []

        for (let i = 0; i < hours.length - 1; i++) {
            if (deferredTime >= hours[i] && deferredTime <= hours[i + 1]) {
                const gridA = grids[hours[i]]
                const gridB = grids[hours[i + 1]]
                if (!gridA || !gridB) return gridA || gridB || []
                const t = (deferredTime - hours[i]) / (hours[i + 1] - hours[i])
                return lerpGrids(gridA, gridB, t)
            }
        }
        return grids[6] || []
    }, [grids, deferredTime])

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

    // Animation loop — supports variable speed and loop mode
    useEffect(() => {
        if (!isPlaying) return

        let rafId: number
        const animate = (timestamp: number) => {
            if (!lastTimeRef.current) lastTimeRef.current = timestamp
            const delta = timestamp - lastTimeRef.current

            if (delta > 80) {
                lastTimeRef.current = timestamp
                setCurrentTime(prev => {
                    const next = prev + 0.3 * playSpeed
                    if (next > 24) {
                        if (loop) return 6   // seamless loop
                        setIsPlaying(false)
                        return 24
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
    }, [isPlaying, playSpeed, loop])

    // Optimized: Only compute stats and physics at discrete time steps (every 0.5h) to save CPU
    const throttledTime = Math.round(currentTime * 2) / 2

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

    // Compute stats - throttled to discrete intervals
    const stats = useMemo(() => {
        if (!currentGrid.length || !bounds) return { maxIntensity: 0, avgIntensity: 0, residentsAtRisk: 0, areaSqKm: 0 }

        let max = 0, sum = 0, affectedCount = 0
        let residents = 0

        const rows = currentGrid.length
        const cols = currentGrid[0].length
        const impactThreshold = 0.3 // Only count area with >30% danger as 'Affected'

        const dLat = Math.abs(bounds.yRange[1] - bounds.yRange[0]) / rows
        const dLon = Math.abs(bounds.xRange[1] - bounds.xRange[0]) / cols
        const cellArea = (dLat * 111) * (dLon * 111 * Math.cos(bounds.yRange[0] * Math.PI / 180))

        for (let r = 0; r < rows; r++) {
            const lat = bounds.yRange[0] + (bounds.yRange[1] - bounds.yRange[0]) * (1 - r / (rows - 1))
            for (let c = 0; c < cols; c++) {
                const val = currentGrid[r][c]
                const lon = bounds.xRange[0] + (bounds.xRange[1] - bounds.xRange[0]) * (c / (cols - 1))

                if (val > max) max = val
                sum += val

                if (val > impactThreshold) {
                    affectedCount++
                    const density = getAreaDensity(lat, lon)
                    residents += density * cellArea * (val ** 1.5) // Non-linear risk weighting
                }
            }
        }

        return {
            maxIntensity: max,
            avgIntensity: sum / (rows * cols),
            residentsAtRisk: Math.round(residents),
            areaSqKm: +(affectedCount * cellArea).toFixed(1),
            affectedPct: Math.round((affectedCount / (rows * cols)) * 100),
        }
    }, [currentGrid, throttledTime, bounds])

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
    }, [currentPhysics, getCardinalDirection, throttledTime])

    const handleCellHover = useCallback((row: number, col: number, val: number) => {
        if (!bounds || !currentGrid.length) return
        const rows = currentGrid.length
        const cols = currentGrid[0].length
        // Correct Mapping: Row 0 = minLat (South)
        const lat = bounds.yRange[0] + (bounds.yRange[1] - bounds.yRange[0]) * (row / (rows - 1))
        const lon = bounds.xRange[0] + (bounds.xRange[1] - bounds.xRange[0]) * (col / (cols - 1))

        // TTI check
        const impactThreshold = 0.25
        const tti = val >= impactThreshold ? currentTime : calculateTTI(row, col, grids, impactThreshold)

        setHoveredCell({ row, col, val, lat, lon, tti })
    }, [bounds, currentGrid, grids, currentTime])

    // Update center tactical data periodically or when grid changes
    useEffect(() => {
        if (!currentGrid.length || !bounds) return
        const rows = currentGrid.length
        const cols = currentGrid[0].length

        // Find peak intensity cell for Sector Insight
        let maxVal = -1, peakR = Math.floor(rows / 2), peakC = Math.floor(cols / 2)
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                if (currentGrid[r][c] > maxVal) {
                    maxVal = currentGrid[r][c]
                    peakR = r
                    peakC = c
                }
            }
        }

        // Align with Row 0 = South
        const lat = minLat + peakR * ((maxLat - minLat) / (rows - 1))
        const lon = minLon + peakC * ((maxLon - minLon) / (cols - 1))
        const tti = maxVal >= 0.25 ? currentTime : calculateTTI(peakR, peakC, grids, 0.25)

        setCenterTacticalData({ val: maxVal, lat, lon, tti })
    }, [currentGrid, bounds, grids, currentTime])

    const minLat = bounds?.yRange[0] ?? 0
    const maxLat = bounds?.yRange[1] ?? 0
    const minLon = bounds?.xRange[0] ?? 0
    const maxLon = bounds?.xRange[1] ?? 0

    // Generate a high-quality smooth 2D heatmap image for the background
    const smoothHeatmapUrl = useMemo(() => {
        if (!currentGrid.length) return null
        return gridToCanvasDataUrl(currentGrid, 512, 512, false)
    }, [currentGrid])

    // Peak intensity time — find which horizon has the worst max
    const peakTime = useMemo(() => {
        let bestT = 6, bestVal = 0
        for (const [t, grid] of Object.entries(grids)) {
            const tNum = parseInt(t)
            if (!grid?.length) continue
            const mx = grid.flat().reduce((a, b) => Math.max(a, b), 0)
            if (mx > bestVal) { bestVal = mx; bestT = tNum }
        }
        return bestT
    }, [grids])

    // Risk trend sparkline across horizons
    const sparklineData = useMemo(() => [6, 12, 24].map(t => {
        const grid = grids[t]
        if (!grid?.length) return { t, max: 0 }
        const mx = grid.flat().reduce((a, b) => Math.max(a, b), 0)
        return { t, max: mx }
    }), [grids])

    // Snapshot export - Generates canvas ON DEMAND
    const handleExportSnapshot = useCallback(() => {
        if (!currentGrid.length) return
        const dataUrl = gridToCanvasDataUrl(currentGrid, 1024, 1024, showContours)
        const a = document.createElement('a')
        a.href = dataUrl
        a.download = `spread-map-T+${currentTime.toFixed(1)}h.png`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
    }, [currentGrid, showContours, currentTime])

    // Keyboard shortcuts
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            const tgt = e.target as HTMLElement
            if (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA' || tgt.tagName === 'SELECT') return
            switch (e.key) {
                case ' ':
                    e.preventDefault()
                    setIsPlaying(p => {
                        if (!p && currentTime >= 24) setCurrentTime(6)
                        return !p
                    })
                    break
                case 'ArrowLeft':
                    e.preventDefault()
                    setCurrentTime(t => Math.max(6, +(t - 1).toFixed(1)))
                    setIsPlaying(false)
                    break
                case 'ArrowRight':
                    e.preventDefault()
                    setCurrentTime(t => Math.min(24, +(t + 1).toFixed(1)))
                    setIsPlaying(false)
                    break
                case 'f': case 'F': setIsExpanded(p => !p); break
                case 'l': case 'L': setLoop(p => !p); break
                case 'c': case 'C': setShowContours(p => !p); break
                case '?': setShowShortcuts(p => !p); break
            }
        }
        window.addEventListener('keydown', handler)
        return () => window.removeEventListener('keydown', handler)
    }, [currentTime])

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
                        {/* Request selector */}
                        <div className="relative">
                            <button
                                onClick={() => setShowDisasterPicker(!showDisasterPicker)}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-orange-300 dark:hover:border-orange-500/30 transition-colors"
                            >
                                {activeRequest ? (
                                    <>
                                        {(() => {
                                            const meta = RESOURCE_TYPE_META[activeRequest.resource_type?.toLowerCase() || 'other'] || RESOURCE_TYPE_META.other
                                            const TypeIcon = meta.icon
                                            return <TypeIcon className={cn("w-3.5 h-3.5", meta.color)} />
                                        })()}
                                        <span className="max-w-[120px] truncate">{activeRequest.resource_type || 'Unknown'} - {activeRequest.head_count} Ppl</span>
                                    </>
                                ) : (
                                    <>
                                        <Users className="w-3 h-3 text-orange-500" />
                                        <span>Select Request</span>
                                    </>
                                )}
                                <ChevronDown className={cn("w-3 h-3 transition-transform", showDisasterPicker && "rotate-180")} />
                            </button>
                            {showDisasterPicker && (
                                <>
                                    <div className="fixed inset-0 z-10" onClick={() => setShowDisasterPicker(false)} />
                                    <div className="absolute right-0 top-full mt-1 w-80 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-2xl z-20 overflow-hidden">
                                        {/* Type filter tabs */}
                                        {requestTypes.length > 0 && (
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
                                                    All ({activeRequests.length})
                                                </button>
                                                {requestTypes.map(type => {
                                                    const meta = RESOURCE_TYPE_META[type] || RESOURCE_TYPE_META.other
                                                    const TypeIcon = meta.icon
                                                    const count = activeRequests.filter(r => r.resource_type?.toLowerCase() === type).length
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

                                        {/* "All Requests" option */}
                                        <button
                                            onClick={() => handleSelectDisaster(null)}
                                            className={cn(
                                                "w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-white/5 border-b border-slate-100 dark:border-white/5",
                                                !selectedDisasterId && "bg-gradient-to-r from-orange-50 to-red-50 dark:from-orange-500/10 dark:to-red-500/10"
                                            )}
                                        >
                                            <div className="flex items-center gap-2">
                                                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
                                                    <Users className="w-3 h-3 text-white" />
                                                </div>
                                                <span className="font-bold text-slate-900 dark:text-white">All Requests</span>
                                                <span className="text-[10px] text-slate-400 ml-auto">Global view</span>
                                            </div>
                                            <p className="text-[11px] text-slate-500 mt-0.5 ml-8">
                                                Show all victim requests across all areas
                                            </p>
                                        </button>

                                        {/* Request list grouped by Resource Type */}
                                        <div className="max-h-64 overflow-y-auto py-1">
                                            {Object.keys(requestsByResource).length === 0 ? (
                                                <div className="px-4 py-8 text-center bg-slate-50/50 dark:bg-white/[0.01]">
                                                    <div className="w-12 h-12 rounded-full border-2 border-slate-200 dark:border-white/10 flex items-center justify-center mx-auto mb-3">
                                                        <Activity className="w-6 h-6 text-slate-300 dark:text-slate-600" />
                                                    </div>
                                                    <p className="text-sm font-bold text-slate-600 dark:text-slate-400">No Pending Requests Found</p>
                                                </div>
                                            ) : (
                                                Object.entries(requestsByResource).map(([resourceKey, typeRequests]) => {
                                                    const meta = RESOURCE_TYPE_META[resourceKey] || RESOURCE_TYPE_META.other
                                                    const ResourceIcon = meta.icon
                                                    return (
                                                        <div key={resourceKey}>
                                                            <div className="px-4 py-1.5 flex items-center gap-1.5 bg-slate-50 dark:bg-white/[0.02]">
                                                                <ResourceIcon className={cn("w-3 h-3", meta.color)} />
                                                                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                                                    {resourceKey} ({typeRequests.length})
                                                                </span>
                                                            </div>
                                                            {typeRequests.map(r => {
                                                                const dInfo = r.disaster_id ? disasterInfoMap[r.disaster_id] : null
                                                                const sevTextColor = r.priority === 'critical' ? 'text-red-600 dark:text-red-400' :
                                                                    r.priority === 'high' ? 'text-orange-600 dark:text-orange-400' :
                                                                        r.priority === 'medium' ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400'

                                                                return (
                                                                    <button
                                                                        key={r.id}
                                                                        onClick={() => handleSelectDisaster(r.id)}
                                                                        className={cn(
                                                                            "w-full text-left px-4 py-2.5 text-sm transition-all hover:bg-slate-50 dark:hover:bg-white/5",
                                                                            selectedDisasterId === r.id && "bg-orange-50 dark:bg-orange-500/10 border-l-2 border-orange-500"
                                                                        )}
                                                                    >
                                                                        <div className="flex flex-col gap-1">
                                                                            <div className="flex items-center gap-2">
                                                                                <div className="min-w-[12px]">
                                                                                    <MapPin className="w-3 h-3 text-slate-400" />
                                                                                </div>
                                                                                <span className="font-medium text-slate-900 dark:text-white truncate flex-1">
                                                                                    {r.head_count} {r.head_count === 1 ? 'Person' : 'People'} - {dInfo?.name || r.address_text || `Coord: [${r.latitude.toFixed(3)}, ${r.longitude.toFixed(3)}]`}
                                                                                </span>
                                                                                <span className={cn("text-[10px] font-bold uppercase", sevTextColor)}>{r.priority}</span>
                                                                            </div>
                                                                            {r.description && (
                                                                                <span className="text-xs text-slate-500 truncate pl-5">{r.description}</span>
                                                                            )}
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

                        {/* Toggles */}
                        <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 rounded-lg p-1 border border-slate-200 dark:border-white/5">
                            <button
                                onClick={() => setShowMarkers(!showMarkers)}
                                className={cn(
                                    "p-1.5 rounded-md transition-all relative",
                                    showMarkers ? "bg-white dark:bg-slate-700 shadow-sm text-emerald-500" : "text-slate-400 hover:text-slate-600"
                                )}
                                title="Toggle markers"
                            >
                                {showMarkers ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                            </button>
                            <button
                                onClick={() => setShowContours(!showContours)}
                                className={cn(
                                    "p-1.5 rounded-md transition-all",
                                    showContours ? "bg-white dark:bg-slate-700 shadow-sm text-orange-500" : "text-slate-400 hover:text-slate-600"
                                )}
                                title="Toggle contours"
                            >
                                <Layers className="w-3.5 h-3.5" />
                            </button>
                            <div className="w-px h-4 bg-slate-200 dark:bg-white/10 mx-0.5" />
                            <button
                                onClick={() => setIsExpanded(!isExpanded)}
                                className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 transition-colors"
                            >
                                {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Sub-header / Status bar */}
                <div className="flex items-center gap-4 px-6 py-2 bg-slate-50/50 dark:bg-white/[0.01] text-[11px]">
                    {activeRequest ? (
                        <>
                            <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400 font-medium">
                                <MapPin className="w-3 h-3 text-slate-400" />
                                <span className="max-w-[400px] truncate">{activeRequest.description || 'Request Location'}</span>
                            </div>
                            <div className={cn(
                                "px-1.5 py-0.5 rounded font-black uppercase text-[9px] tracking-widest",
                                activeRequest.priority === 'critical' ? 'bg-red-500 text-white' :
                                    activeRequest.priority === 'high' ? 'bg-orange-500 text-white' : 'bg-yellow-500 text-white'
                            )}>
                                {activeRequest.priority}
                            </div>
                            <div className="text-slate-400 italic">
                                Learning Physics: Diffusion D={currentPhysics?.diffusion?.toFixed(3) || '0.000'}
                            </div>
                        </>
                    ) : (
                        <div className="flex items-center gap-2 text-slate-400">
                            <Activity className="w-3 h-3 text-orange-500 animate-pulse" />
                            <span>Global Situational Awareness: Aggregating all localized PINN projections</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Stats row */}
            {currentGrid.length > 0 && (
                <div className="grid grid-cols-4 gap-px bg-slate-100 dark:bg-white/5">
                    {[
                        { label: 'Time Horizon', value: `T+${currentTime.toFixed(1)}h`, icon: Clock, color: 'text-blue-600 dark:text-blue-400' },
                        { label: 'Residents at Risk', value: stats.residentsAtRisk.toLocaleString(), icon: Users, color: 'text-red-600 dark:text-red-400' },
                        { label: 'Affected Area', value: `${stats.areaSqKm} km²`, icon: Mountain, color: 'text-emerald-600 dark:text-emerald-400' },
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
                    grid={currentGrid}
                    height={isExpanded ? 'calc(100vh - 340px)' : '500px'}
                    onCellHover={handleCellHover}
                    onCellLeave={() => setHoveredCell(null)}
                    epicenters={(data as any)?.epicenters || []}
                    victimMarkers={victimMarkers as VictimMarkerData[]}
                    showMarkers={showMarkers}
                    smoothImage={smoothHeatmapUrl || undefined}
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

                {/* Tactical Intelligence — Interaction driven, appears only when targeting clusters */}
                {hoveredCell && hoveredCell.val > 0.05 && (
                    <div className="absolute top-4 right-4 z-[1005] bg-slate-900/90 backdrop-blur-md text-white rounded-xl p-4 shadow-2xl border border-white/10 min-w-[220px] pointer-events-none transition-all duration-300">
                        <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/10">
                            <div className="flex items-center gap-2">
                                <div className={cn("w-3 h-3 rounded-full", hoveredCell.val > 0.4 ? "animate-pulse bg-red-500" : "bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.4)]")} />
                                <span className="font-black text-[10px] uppercase tracking-widest text-slate-300">
                                    Target Intelligence
                                </span>
                            </div>
                            <span className="text-[10px] tabular-nums text-slate-500">
                                {hoveredCell.lat.toFixed(3)}°, {hoveredCell.lon.toFixed(3)}°
                            </span>
                        </div>

                        <div className="space-y-3.5">
                            <div className="flex items-center justify-between">
                                <span className="text-[9px] text-slate-400 uppercase font-black tracking-tight">Relative Intensity</span>
                                <div className="flex items-center gap-2">
                                    <div className="w-16 h-1.5 rounded-full bg-white/5 overflow-hidden">
                                        <div className="h-full bg-gradient-to-r from-orange-500 to-red-500 transition-all duration-500"
                                            style={{ width: `${hoveredCell.val * 100}%` }} />
                                    </div>
                                    <span className="text-xs font-black tabular-nums">
                                        {(hoveredCell.val * 100).toFixed(0)}%
                                    </span>
                                </div>
                            </div>

                            <div className="flex items-center justify-between">
                                <span className="text-[9px] text-slate-400 uppercase font-black tracking-tight">Population Density</span>
                                <span className="text-xs font-bold text-slate-200">
                                    ~{getAreaDensity(hoveredCell.lat, hoveredCell.lon).toLocaleString(undefined, { maximumFractionDigits: 0 })} / km²
                                </span>
                            </div>

                            <div className="pt-2 mt-2 border-t border-white/5 flex items-center justify-between">
                                <span className={cn(
                                    "text-[9px] uppercase font-black flex items-center gap-1",
                                    hoveredCell.tti != null && hoveredCell.tti! <= currentTime ? "text-red-400" : "text-orange-400"
                                )}>
                                    <Zap className="w-3 h-3" /> TTI ADVISORY
                                </span>
                                <span className={cn(
                                    "px-2 py-0.5 rounded font-black text-[10px] tracking-wider",
                                    hoveredCell.tti != null && hoveredCell.tti! <= currentTime
                                        ? "bg-red-600 text-white animate-pulse"
                                        : "bg-slate-800 text-slate-300"
                                )}>
                                    {hoveredCell.tti != null
                                        ? (hoveredCell.tti! <= currentTime ? 'IMPACTED' : `T+${hoveredCell.tti!.toFixed(1)}h`)
                                        : 'NOMINAL'}
                                </span>
                            </div>
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
                <div className="border-t border-slate-100 dark:border-white/5 bg-slate-50/50 dark:bg-white/[0.02]">

                    {/* Risk Trend Sparkline */}
                    {sparklineData.some(d => d.max > 0) && (
                        <div className="px-6 pt-4 pb-1">
                            <div className="flex items-center justify-between mb-1.5">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Risk Trend</span>
                                <div className="flex items-center gap-3">
                                    {sparklineData.map(d => (
                                        <button key={d.t}
                                            onClick={() => { setCurrentTime(d.t); setIsPlaying(false) }}
                                            className={cn(
                                                'text-[10px] font-bold tabular-nums transition-colors',
                                                Math.abs(currentTime - d.t) < 0.5
                                                    ? 'text-orange-600 dark:text-orange-400'
                                                    : 'text-slate-400 hover:text-orange-500'
                                            )}
                                        >
                                            T+{d.t}h {(d.max * 100).toFixed(0)}%
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="relative h-10">
                                <svg width="100%" height="40" viewBox="0 0 300 40" preserveAspectRatio="none" className="overflow-visible">
                                    <defs>
                                        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor="#f97316" stopOpacity="0.35" />
                                            <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
                                        </linearGradient>
                                    </defs>
                                    {(() => {
                                        const pts = sparklineData.map((d, i) => ({
                                            x: i === 0 ? 4 : i === 1 ? 150 : 296,
                                            y: 34 - Math.min(1, d.max) * 28
                                        }))
                                        const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
                                        const area = `${line} L296,40 L4,40 Z`
                                        return (
                                            <>
                                                <path d={area} fill="url(#sparkGrad)" />
                                                <path d={line} fill="none" stroke="#f97316" strokeWidth="2"
                                                    strokeLinecap="round" strokeLinejoin="round" />
                                                {pts.map((p, i) => (
                                                    <circle key={i} cx={p.x} cy={p.y} r={4}
                                                        fill={Math.abs(currentTime - sparklineData[i].t) < 0.5 ? '#f97316' : 'white'}
                                                        stroke="#f97316" strokeWidth="2"
                                                        className="cursor-pointer"
                                                        onClick={() => { setCurrentTime(sparklineData[i].t); setIsPlaying(false) }}
                                                    />
                                                ))}
                                            </>
                                        )
                                    })()}
                                </svg>
                            </div>
                        </div>
                    )}

                    <div className="px-6 pb-4 space-y-3">
                        {/* Transport + controls row */}
                        <div className="flex items-center gap-2 flex-wrap">
                            <button onClick={() => { setCurrentTime(6); setIsPlaying(false) }}
                                className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                                title="Reset to T+6h">
                                <SkipBack className="w-4 h-4" />
                            </button>

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

                            <button onClick={() => { setCurrentTime(24); setIsPlaying(false) }}
                                className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
                                title="Skip to T+24h">
                                <SkipForward className="w-4 h-4" />
                            </button>

                            {/* Speed */}
                            <div className="flex items-center gap-px bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5 ml-1">
                                {([0.5, 1, 2, 4] as const).map(s => (
                                    <button key={s} onClick={() => setPlaySpeed(s)}
                                        className={cn(
                                            'px-2 py-1 rounded-md text-[10px] font-bold transition-all',
                                            playSpeed === s
                                                ? 'bg-orange-500 text-white shadow-sm'
                                                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700'
                                        )}>
                                        {s}×
                                    </button>
                                ))}
                            </div>

                            {/* Loop */}
                            <button onClick={() => setLoop(l => !l)}
                                className={cn(
                                    'p-2 rounded-lg transition-colors',
                                    loop
                                        ? 'bg-orange-100 dark:bg-orange-500/20 text-orange-600 dark:text-orange-400'
                                        : 'bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700'
                                )}
                                title={loop ? 'Loop ON' : 'Loop OFF'}>
                                <Repeat className="w-4 h-4" />
                            </button>

                            <div className="ml-auto flex items-center gap-2">
                                {sparklineData.some(d => d.max > 0) && (
                                    <button
                                        onClick={() => { setCurrentTime(peakTime); setIsPlaying(false) }}
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-[11px] font-bold hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors border border-red-200 dark:border-red-500/20"
                                        title={`Jump to peak at T+${peakTime}h`}>
                                        <Zap className="w-3 h-3" />
                                        Peak T+{peakTime}h
                                    </button>
                                )}

                                {currentGrid.length > 0 && (
                                    <button onClick={handleExportSnapshot}
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[11px] font-bold hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                                        title="Export frame as PNG">
                                        <Download className="w-3 h-3" />
                                        Export
                                    </button>
                                )}

                                <button
                                    onClick={() => setShowShortcuts(s => !s)}
                                    className={cn(
                                        'px-2 py-1 rounded-lg text-[11px] font-bold border transition-colors',
                                        showShortcuts
                                            ? 'bg-slate-200 dark:bg-slate-700 border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300'
                                            : 'text-slate-400 hover:text-slate-600 border-slate-200 dark:border-slate-700'
                                    )}
                                    title="Keyboard shortcuts">?
                                </button>
                            </div>
                        </div>

                        {/* Shortcuts panel */}
                        {showShortcuts && (
                            <div className="p-3 rounded-xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-white/10 grid grid-cols-3 gap-x-4 gap-y-1.5">
                                {[
                                    ['Space', 'Play / Pause'], ['\u2190 \u2192', 'Step \u00b11h'],
                                    ['F', 'Fullscreen'], ['L', 'Loop'], ['C', 'Contours'], ['?', 'Help'],
                                ].map(([key, desc]) => (
                                    <div key={key} className="flex items-center gap-1.5">
                                        <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-700 border border-slate-200 dark:border-white/10 text-[9px] font-mono font-bold text-slate-600 dark:text-slate-300 shadow-sm whitespace-nowrap">{key}</kbd>
                                        <span className="text-[10px] text-slate-500">{desc}</span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Time slider */}
                        <div>
                            <input
                                type="range" min={6} max={24} step={0.1}
                                value={currentTime}
                                onChange={(e) => { setCurrentTime(parseFloat(e.target.value)); setIsPlaying(false) }}
                                className="w-full h-2 rounded-full appearance-none cursor-pointer
                                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
                                    [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-orange-500
                                    [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-orange-500/30
                                    [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:cursor-pointer
                                    [&::-moz-range-thumb]:w-5 [&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:rounded-full
                                    [&::-moz-range-thumb]:bg-orange-500 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white"
                                style={{
                                    background: `linear-gradient(to right,#f97316 0%,#f97316 ${((currentTime - 6) / 18) * 100}%,#e2e8f0 ${((currentTime - 6) / 18) * 100}%,#e2e8f0 100%)`,
                                }}
                            />
                            <div className="flex justify-between mt-1.5 px-0.5">
                                {[6, 12, 18, 24].map(h => (
                                    <button key={h} onClick={() => { setCurrentTime(h); setIsPlaying(false) }}
                                        className={cn(
                                            'text-[10px] font-bold tabular-nums transition-colors cursor-pointer',
                                            Math.abs(currentTime - h) < 0.5
                                                ? 'text-orange-600 dark:text-orange-400'
                                                : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                                        )}>
                                        T+{h}h
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Physics, Analytics & Model Info */}
            {(physicsDisplay || data) && (
                <div className="px-6 py-4 border-t border-slate-100 dark:border-white/5 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {/* Learned Physics */}
                        {physicsDisplay && (
                            <div className="rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-500/5 dark:to-indigo-500/5 border border-blue-100 dark:border-blue-500/10 p-4">
                                <div className="flex items-center gap-2 mb-3">
                                    <Wind className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                    <span className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider">Learned Physics</span>
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className="w-14 h-14 rounded-full bg-white dark:bg-slate-800 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center shadow-sm shrink-0">
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
                                {[
                                    ['Model', (data?.model || 'PINN').toUpperCase()],
                                    ['Dynamic Reach', `${data?.dynamic_reach_km ? Math.round(data.dynamic_reach_km) : 50} km`],
                                    ['Grid', `${currentGrid.length}×${currentGrid[0]?.length || 0}`],
                                    ['Center', `${mapCenter[0].toFixed(2)}°, ${mapCenter[1].toFixed(2)}°`],
                                    ['Victims', `${victimStats.total} req · ${victimStats.totalPeople} people`],
                                ].map(([label, val]) => (
                                    <div key={label} className="flex justify-between gap-2">
                                        <span className="text-slate-500 shrink-0">{label}</span>
                                        <span className="font-medium text-slate-700 dark:text-slate-300 text-right truncate">{val}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Victim Resource Breakdown */}
                    {victimStats.total > 0 && (
                        <div className="rounded-xl border border-slate-200 dark:border-white/10 overflow-hidden">
                            <button
                                onClick={() => setShowBreakdown(b => !b)}
                                className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
                            >
                                <div className="flex items-center gap-2">
                                    <BarChart2 className="w-4 h-4 text-orange-500" />
                                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Resource Breakdown</span>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400 font-bold">{victimStats.total} requests</span>
                                    {victimStats.critical > 0 && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 font-bold">{victimStats.critical} critical</span>
                                    )}
                                </div>
                                <span className="text-slate-400 text-xs">{showBreakdown ? '▲' : '▼'}</span>
                            </button>

                            {showBreakdown && (
                                <div className="px-4 py-3 space-y-2.5 bg-white dark:bg-white/[0.01]">
                                    {victimStats.totalPeople > 0 && (
                                        <p className="text-xs text-slate-500 pb-1">
                                            <span className="font-semibold text-slate-700 dark:text-slate-300">{victimStats.totalPeople.toLocaleString()}</span> people across {victimStats.total} requests
                                        </p>
                                    )}
                                    {([
                                        { label: 'Food', val: victimStats.food, color: 'bg-amber-500' },
                                        { label: 'Water', val: victimStats.water, color: 'bg-blue-500' },
                                        { label: 'Medical', val: victimStats.medical, color: 'bg-red-500' },
                                        { label: 'Shelter / Clothing', val: victimStats.cloth, color: 'bg-emerald-500' },
                                        { label: 'Other', val: victimStats.other, color: 'bg-slate-400' },
                                    ] as const).filter(r => r.val > 0).map(row => {
                                        const pct = Math.round((row.val / victimStats.total) * 100)
                                        return (
                                            <div key={row.label}>
                                                <div className="flex justify-between mb-1">
                                                    <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">{row.label}</span>
                                                    <span className="text-[11px] text-slate-500 tabular-nums">{row.val} ({pct}%)</span>
                                                </div>
                                                <div className="h-1.5 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
                                                    <div className={`h-full rounded-full transition-all duration-700 ${row.color}`}
                                                        style={{ width: `${pct}%` }} />
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

// ─── Tactical Analytics Helpers ─────────────────────────────────────────────
function getAreaDensity(lat: number, lon: number): number {
    // Strategic population centers for more accurate risk estimation
    const metros = [
        [28.61, 77.20, 11000], // Delhi
        [19.07, 72.87, 21000], // Mumbai
        [12.97, 77.59, 12000], // Bengaluru
        [22.57, 88.36, 15000], // Kolkata
        [13.08, 80.27, 10000], // Chennai
        [17.38, 78.48, 9000],  // Hyderabad
        [23.02, 72.57, 8000],  // Ahmedabad
        [18.52, 73.85, 7000],  // Pune
        [26.84, 80.94, 6000]   // Lucknow
    ]

    let density = 450 // National average fallback
    let maxFactor = 1

    for (const [mLat, mLon, mDens] of metros) {
        const dist = Math.sqrt((lat - mLat) ** 2 + (lon - mLon) ** 2)
        if (dist < 1.5) {
            const factor = Math.exp(-dist * 2.5)
            density = Math.max(density, mDens * factor)
            maxFactor = Math.max(maxFactor, factor * 2)
        }
    }

    // Add micro-variance based on coordinates for tactical realism
    const noise = (Math.sin(lat * 100) + Math.cos(lon * 100)) * 50
    return Math.max(100, density + noise)
}

function calculateTTI(row: number, col: number, grids: Record<string, number[][]>, threshold: number = 0.25): number | null {
    const horizons = [6, 12, 24]

    for (let i = 0; i < horizons.length; i++) {
        const t = horizons[i]
        const val = grids[t]?.[row]?.[col] ?? 0
        if (val >= threshold) return t
    }

    // Fallback: If it's growing but hasn't hit threshold, estimate based on growth rate
    const v6 = grids[6]?.[row]?.[col] ?? 0
    const v24 = grids[24]?.[row]?.[col] ?? 0
    if (v24 > v6 && v24 > 0.05) {
        const growthRate = (v24 - v6) / 18
        const remaining = threshold - v24
        const estimatedTTI = 24 + (remaining / Math.max(0.001, growthRate))
        return estimatedTTI < 72 ? Math.round(estimatedTTI) : null
    }

    return null
}
