'use client'

import { useQuery } from '@tanstack/react-query'
import { getMultiHorizonForecast, type ForecastHorizon } from '@/lib/api/workflow'
import { Activity, TrendingUp, Loader2, AlertTriangle } from 'lucide-react'

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

export function TFTForecastWidget() {
    const { data, isLoading, error } = useQuery({
        queryKey: ['tft-forecast'],
        queryFn: () => getMultiHorizonForecast(),
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
            <div className="rounded-xl border border-red-200 dark:border-red-800 bg-white dark:bg-slate-800 p-6">
                <div className="flex items-center gap-2 mb-4">
                    <AlertTriangle className="w-5 h-5 text-red-500" />
                    <h3 className="font-semibold text-slate-900 dark:text-white">Severity Forecast</h3>
                </div>
                <p className="text-sm text-red-600 dark:text-red-400">
                    {(error as Error).message || 'Failed to load forecast data'}
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
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[data?.current_severity || 'medium']}`}>
                        Current: {data?.current_severity || 'medium'}
                    </span>
                    <span className="text-xs text-slate-400">
                        {Math.round(confidence * 100)}% conf
                    </span>
                </div>
            </div>

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
