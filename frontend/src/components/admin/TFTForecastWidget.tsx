'use client'

import { useQuery } from '@tanstack/react-query'
import { getMultiHorizonForecast, type ForecastHorizon } from '@/lib/api/workflow'
import { api } from '@/lib/api'
import { Activity, TrendingUp, Loader2, AlertTriangle, RefreshCw, ChevronDown, Globe, Filter } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

const SEVERITY_COLORS: Record<string, string> = {
    low: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
}

const SEVERITY_BAR: Record<string, string> = {
    low: 'bg-green-500',
    medium: 'bg-yellow-500',
    high: 'bg-orange-500',
    critical: 'bg-red-500',
}

const SEVERITY_ORDER = ['low', 'medium', 'high', 'critical']

export function TFTForecastWidget({ selectedDisasterId }: { selectedDisasterId?: string | null }) {
    const [showDisasterPicker, setShowDisasterPicker] = useState(false)
    const [localDisasterId, setLocalDisasterId] = useState<string | null>(selectedDisasterId || null)

    // Sync with parent
    const activeDId = selectedDisasterId !== undefined ? selectedDisasterId : localDisasterId

    const { data: disasterList } = useQuery({
        queryKey: ['disasters-for-forecast'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 50 }),
        retry: false,
        staleTime: 60000,
    })

    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ['tft-forecast', activeDId],
        queryFn: () => getMultiHorizonForecast(activeDId ? { disaster_id: activeDId } : undefined),
        refetchInterval: 60000, // refresh every minute
    })

    if (isLoading) {
        return (
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Activity className="w-5 h-5 text-blue-500" />
                    <h3 className="font-semibold text-slate-900 dark:text-white">Severity Forecast</h3>
                </div>
                <div className="flex justify-center py-8">
                    <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="rounded-xl border border-red-200 dark:border-red-500/20 bg-white dark:bg-slate-800 p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5 text-red-500" />
                        <h3 className="font-semibold text-slate-900 dark:text-white">Severity Forecast</h3>
                    </div>
                    <button
                        onClick={() => refetch()}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-xs font-medium hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                    >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Retry
                    </button>
                </div>
                <div className="rounded-lg bg-red-50 dark:bg-red-500/5 border border-red-100 dark:border-red-500/10 p-4 text-center">
                    <p className="text-sm font-medium text-red-700 dark:text-red-400 mb-1">
                        Forecast Service Unavailable
                    </p>
                    <p className="text-xs text-red-500/80 dark:text-red-400/70">
                        {(error as Error).message || 'Failed to load forecast data. Ensure the ML backend is running.'}
                    </p>
                </div>
                <p className="text-xs text-slate-400 mt-3 text-center">
                    The TFT model requires active disaster data and a running ML service.
                </p>
            </div>
        )
    }

    const horizons = data?.horizons || []
    const confidence = data?.confidence || 0
    const summary = data?.summary

    return (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Activity className="w-5 h-5 text-blue-500" />
                    <h3 className="font-semibold text-slate-900 dark:text-white">TFT Severity Forecast</h3>
                </div>
                <div className="flex items-center gap-2">
                    {data && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[data?.current_severity || 'medium']}`}>
                            Current: {data?.current_severity || 'medium'}
                        </span>
                    )}
                    {data && (
                        <span className="text-xs text-slate-400">
                            {Math.round(confidence * 100)}% conf
                        </span>
                    )}
                    <button
                        onClick={() => refetch()}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
                        title="Refresh forecast"
                    >
                        <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>

            {/* Disaster selector (standalone mode) */}
            {selectedDisasterId === undefined && (
                <div className="relative mb-3">
                    <button
                        onClick={() => setShowDisasterPicker(!showDisasterPicker)}
                        className={cn(
                            "flex items-center gap-2 w-full px-3 py-2 rounded-lg border text-xs font-medium transition-all",
                            localDisasterId
                                ? "bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20 text-blue-700 dark:text-blue-400"
                                : "bg-slate-50 dark:bg-white/5 border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400"
                        )}
                    >
                        {localDisasterId ? <Filter className="w-3.5 h-3.5" /> : <Globe className="w-3.5 h-3.5" />}
                        <span className="flex-1 text-left">
                            {localDisasterId
                                ? (() => {
                                    const d = Array.isArray(disasterList) ? disasterList.find((x: any) => x.id === localDisasterId) : null
                                    return d ? (d.title || d.type || 'Selected Disaster') : 'Filtered'
                                  })()
                                : 'All Active Disasters'}
                        </span>
                        <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", showDisasterPicker && "rotate-180")} />
                    </button>
                    {showDisasterPicker && (
                        <>
                            <div className="fixed inset-0 z-10" onClick={() => setShowDisasterPicker(false)} />
                            <div className="absolute left-0 right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-xl z-20 py-1 max-h-48 overflow-y-auto">
                                <button
                                    onClick={() => { setLocalDisasterId(null); setShowDisasterPicker(false) }}
                                    className={cn("flex items-center gap-2 w-full px-3 py-2 text-xs text-left transition-colors",
                                        !localDisasterId ? "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400" : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                                    )}
                                >
                                    <Globe className="w-3.5 h-3.5" /> All Active Disasters
                                </button>
                                {Array.isArray(disasterList) && disasterList.map((d: any) => (
                                    <button
                                        key={d.id}
                                        onClick={() => { setLocalDisasterId(d.id); setShowDisasterPicker(false) }}
                                        className={cn("flex items-center gap-2 w-full px-3 py-2 text-xs text-left transition-colors",
                                            localDisasterId === d.id ? "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400" : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                                        )}
                                    >
                                        <div className={cn("w-2 h-2 rounded-full",
                                            d.severity === 'critical' ? 'bg-red-500' : d.severity === 'high' ? 'bg-orange-500' : d.severity === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                                        )} />
                                        <span className="truncate">{d.title || d.type}</span>
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}

            {summary && (
                <div className="mb-4 rounded-lg border border-blue-100 dark:border-blue-900/30 bg-blue-50/60 dark:bg-blue-950/20 p-3 text-xs text-slate-600 dark:text-slate-300">
                    <p>
                        Based on {summary.active_request_count} active victim requests, {summary.victims_impacted} impacted victims, and {summary.availability_pct.toFixed(1)}% live resource availability.
                    </p>
                    {data?.derived_from && (
                        <p className="mt-1 text-slate-500 dark:text-slate-400">{data.derived_from}</p>
                    )}
                </div>
            )}

            {/* Horizons */}
            <div className="space-y-3">
                {horizons.map((h: ForecastHorizon) => {
                    const sevIdx = SEVERITY_ORDER.indexOf(h.predicted_severity)
                    const barWidth = ((sevIdx + 1) / 4) * 100

                    return (
                        <div key={h.horizon} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium text-slate-700 dark:text-slate-300">
                                    T+{h.horizon}
                                </span>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-slate-400">
                                        {h.lower_bound}
                                    </span>
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[h.predicted_severity]}`}>
                                        {h.predicted_severity}
                                    </span>
                                    <span className="text-xs text-slate-400">
                                        {h.upper_bound}
                                    </span>
                                </div>
                            </div>
                            <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ${SEVERITY_BAR[h.predicted_severity]}`}
                                    style={{ width: `${barWidth}%` }}
                                />
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* Model info */}
            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between text-xs text-slate-400">
                <span>Model: {data?.model_version || 'TFT'}</span>
                <span className="flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    Multi-horizon temporal fusion
                </span>
            </div>
        </div>
    )
}