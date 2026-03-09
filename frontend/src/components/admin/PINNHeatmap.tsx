'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSpreadHeatmap, type HeatmapData } from '@/lib/api/workflow'
import { Flame, Loader2, Clock, MapPin } from 'lucide-react'

const INTENSITY_COLORS = [
    'rgba(0, 128, 255, 0.0)',   // 0.0 - transparent
    'rgba(0, 128, 255, 0.2)',   // 0.1
    'rgba(0, 200, 200, 0.3)',   // 0.2
    'rgba(0, 255, 128, 0.4)',   // 0.3
    'rgba(128, 255, 0, 0.5)',   // 0.4
    'rgba(255, 255, 0, 0.6)',   // 0.5
    'rgba(255, 200, 0, 0.7)',   // 0.6
    'rgba(255, 128, 0, 0.8)',   // 0.7
    'rgba(255, 64, 0, 0.85)',   // 0.8
    'rgba(255, 0, 0, 0.9)',     // 0.9
    'rgba(200, 0, 0, 1.0)',     // 1.0
]

function getColor(intensity: number): string {
    const idx = Math.min(Math.floor(intensity * 10), 10)
    return INTENSITY_COLORS[idx]
}

interface PINNHeatmapProps {
    latitude?: number
    longitude?: number
    radiusKm?: number
}

export function PINNHeatmap({ latitude = 28.6, longitude = 77.2, radiusKm = 50 }: PINNHeatmapProps) {
    const [selectedHorizon, setSelectedHorizon] = useState('T+6h')
    const horizonValues = [6, 12, 24]

    const { data, isLoading } = useQuery({
        queryKey: ['pinn-heatmap', latitude, longitude, radiusKm],
        queryFn: () => getSpreadHeatmap({
            latitude,
            longitude,
            radius_km: radiusKm,
            horizons: horizonValues,
            resolution: 20,
        }),
        refetchInterval: 120000,
    })

    const horizonKeys = Object.keys(data?.horizons || {})
    const currentHorizon = data?.horizons?.[selectedHorizon]
    const grid = currentHorizon?.grid || []

    return (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Flame className="w-5 h-5 text-orange-500" />
                    <h3 className="font-semibold text-slate-900 dark:text-white">PINN Spread Prediction</h3>
                </div>
                <span className="text-xs text-slate-400 flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    {latitude.toFixed(2)}, {longitude.toFixed(2)}
                </span>
            </div>

            <p className="text-sm text-slate-500">
                Physics-informed neural network predicting disaster spread over time
            </p>

            {/* Time Slider */}
            <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-slate-400" />
                <div className="flex gap-2">
                    {horizonKeys.map((key) => (
                        <button
                            key={key}
                            onClick={() => setSelectedHorizon(key)}
                            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                                selectedHorizon === key
                                    ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-400'
                            }`}
                        >
                            {key}
                        </button>
                    ))}
                </div>
            </div>

            {/* Heatmap Grid */}
            {isLoading ? (
                <div className="flex justify-center py-12">
                    <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
                </div>
            ) : grid.length > 0 ? (
                <div className="relative">
                    <div
                        className="grid gap-0 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600"
                        style={{
                            gridTemplateColumns: `repeat(${grid[0]?.length || 20}, 1fr)`,
                            aspectRatio: '1',
                        }}
                    >
                        {grid.flatMap((row, i) =>
                            row.map((val, j) => (
                                <div
                                    key={`${i}-${j}`}
                                    style={{ backgroundColor: getColor(val) }}
                                    className="aspect-square"
                                    title={`Intensity: ${(val * 100).toFixed(0)}%`}
                                />
                            ))
                        )}
                    </div>

                    {/* Legend */}
                    <div className="flex items-center justify-between mt-3">
                        <span className="text-xs text-slate-400">Low risk</span>
                        <div className="flex h-3 rounded-full overflow-hidden flex-1 mx-3">
                            {INTENSITY_COLORS.map((color, i) => (
                                <div key={i} style={{ backgroundColor: color, flex: 1 }} />
                            ))}
                        </div>
                        <span className="text-xs text-slate-400">High risk</span>
                    </div>
                </div>
            ) : (
                <div className="text-center py-8 text-slate-400 text-sm">
                    No heatmap data available
                </div>
            )}

            {/* Learned Physics */}
            {currentHorizon?.learned_physics && (
                <div className="border-t border-slate-100 dark:border-slate-700 pt-3">
                    <div className="text-xs text-slate-500">
                        <span className="font-medium">Learned Physics: </span>
                        Diffusion={currentHorizon.learned_physics.diffusion?.toFixed(3) || 'N/A'},
                        Velocity=[{(currentHorizon.learned_physics.velocity || []).map((v: number) => v.toFixed(4)).join(', ')}]
                    </div>
                </div>
            )}

            <div className="text-xs text-slate-400">
                Model: {data?.model || 'PINN'} | Radius: {data?.radius_km || radiusKm}km
            </div>
        </div>
    )
}
