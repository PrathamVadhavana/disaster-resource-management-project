'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
    Brain, Loader2, RefreshCw, Play, Settings, BarChart3, Activity,
    AlertTriangle, CheckCircle2, Zap, Target, Layers, Cpu
} from 'lucide-react'

interface MoEStatus {
    model_loaded: boolean
    n_experts: number
    top_k: number
    expert_utilization: Record<string, number>
    cache_stats: {
        cache_hits: number
        cache_misses: number
        hit_rate: number
        cache_size: number
    }
    experts: string[]
    error?: string
}

interface MoEPrediction {
    severity?: {
        predicted_severity: string
        confidence: number
        probabilities: Record<string, number>
    }
    spread?: {
        predicted_area_km2: number
        ci_lower_km2: number
        ci_upper_km2: number
    }
    impact?: {
        predicted_casualties: number
        predicted_damage_usd: number
    }
    resource?: {
        resource_allocation: Record<string, number>
        primary_resource: string
    }
    anomaly?: {
        anomaly_score: number
        is_anomaly: boolean
        confidence: number
    }
    expert_routing: {
        gate_probs: number[][]
        expert_usage: number[]
        load_balance_loss: number
    }
    cached: boolean
}

const EXPERT_COLORS: Record<string, string> = {
    severity: 'bg-red-500',
    spread: 'bg-blue-500',
    impact: 'bg-orange-500',
    resource: 'bg-green-500',
    anomaly: 'bg-purple-500',
}

export function MoEDashboard() {
    const qc = useQueryClient()
    const [testFeatures, setTestFeatures] = useState({
        temperature: 30,
        humidity: 70,
        wind_speed: 25,
        pressure: 1000,
        precipitation: 50,
        population_density: 500,
        affected_population: 10000,
        current_area: 100,
    })
    const [disasterType, setDisasterType] = useState('flood')
    const [severity, setSeverity] = useState('high')
    const [latitude, setLatitude] = useState(19.076)
    const [longitude, setLongitude] = useState(72.877)

    const { data: moeStatus, isLoading: statusLoading } = useQuery<MoEStatus>({
        queryKey: ['moe-status'],
        queryFn: () => api.getMoEStatus(),
        refetchInterval: 30000,
    })

    const { data: cacheStats } = useQuery({
        queryKey: ['moe-cache-stats'],
        queryFn: () => api.getMoECacheStats(),
        refetchInterval: 10000,
    })

    const predictMutation = useMutation({
        mutationFn: () => api.moePredict({
            features: testFeatures,
            disaster_type: disasterType,
            severity: severity,
            latitude: latitude,
            longitude: longitude,
        }),
    })

    const trainMutation = useMutation({
        mutationFn: () => api.trainMoE({ epochs: 50, batch_size: 32 }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['moe-status'] })
        },
    })

    const clearCacheMutation = useMutation({
        mutationFn: () => api.clearMoECache(),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['moe-cache-stats'] })
        },
    })

    const resetStatsMutation = useMutation({
        mutationFn: () => api.resetMoEStats(),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['moe-status'] })
        },
    })

    if (statusLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
            </div>
        )
    }

    const prediction = predictMutation.data as MoEPrediction | undefined

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Layers className="w-5 h-5 text-purple-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Mixture of Experts (MoE)</h3>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => resetStatsMutation.mutate()}
                        disabled={resetStatsMutation.isPending}
                        className="px-3 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors disabled:opacity-50"
                    >
                        <RefreshCw className="w-3 h-3 mr-1 inline" />
                        Reset Stats
                    </button>
                    <button
                        onClick={() => trainMutation.mutate()}
                        disabled={trainMutation.isPending}
                        className="px-3 py-1.5 rounded-lg text-xs bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
                    >
                        {trainMutation.isPending ? <Loader2 className="w-3 h-3 mr-1 inline animate-spin" /> : <Play className="w-3 h-3 mr-1 inline" />}
                        Train MoE
                    </button>
                </div>
            </div>

            {/* Model Status */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Cpu className="w-4 h-4 text-purple-500" />
                        <span className="text-xs font-medium text-slate-500">Model Status</span>
                    </div>
                    <p className={cn(
                        "text-lg font-bold",
                        moeStatus?.model_loaded ? "text-emerald-600" : "text-red-600"
                    )}>
                        {moeStatus?.model_loaded ? "Loaded" : "Not Loaded"}
                    </p>
                </div>

                <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Brain className="w-4 h-4 text-purple-500" />
                        <span className="text-xs font-medium text-slate-500">Experts</span>
                    </div>
                    <p className="text-lg font-bold text-slate-900 dark:text-white">
                        {moeStatus?.n_experts || 0} / Top-{moeStatus?.top_k || 0}
                    </p>
                </div>

                <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Zap className="w-4 h-4 text-purple-500" />
                        <span className="text-xs font-medium text-slate-500">Cache Hit Rate</span>
                    </div>
                    <p className="text-lg font-bold text-slate-900 dark:text-white">
                        {((cacheStats?.hit_rate || 0) * 100).toFixed(1)}%
                    </p>
                </div>

                <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Target className="w-4 h-4 text-purple-500" />
                        <span className="text-xs font-medium text-slate-500">Cache Size</span>
                    </div>
                    <p className="text-lg font-bold text-slate-900 dark:text-white">
                        {cacheStats?.cache_size || 0}
                    </p>
                </div>
            </div>

            {/* Expert Utilization */}
            {moeStatus?.model_loaded && (
                <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Expert Utilization</h4>
                    <div className="space-y-3">
                        {moeStatus.experts?.map((expert, idx) => {
                            const utilization = moeStatus.expert_utilization?.[expert] || 0
                            return (
                                <div key={expert} className="flex items-center gap-3">
                                    <span className="text-xs font-medium text-slate-500 w-20 capitalize">{expert}</span>
                                    <div className="flex-1 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                        <div
                                            className={cn("h-full rounded-full transition-all", EXPERT_COLORS[expert] || 'bg-purple-500')}
                                            style={{ width: `${Math.min(utilization * 100, 100)}%` }}
                                        />
                                    </div>
                                    <span className="text-xs font-mono text-slate-400 w-16 text-right">
                                        {(utilization * 100).toFixed(1)}%
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* Test Prediction */}
            <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Test MoE Prediction</h4>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Disaster Type</label>
                        <select
                            value={disasterType}
                            onChange={(e) => setDisasterType(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                        >
                            {['earthquake', 'flood', 'hurricane', 'tornado', 'wildfire', 'tsunami', 'drought', 'landslide', 'volcano', 'other'].map(type => (
                                <option key={type} value={type}>{type}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Severity</label>
                        <select
                            value={severity}
                            onChange={(e) => setSeverity(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                        >
                            {['low', 'medium', 'high', 'critical'].map(sev => (
                                <option key={sev} value={sev}>{sev}</option>
                            ))}
                        </select>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="block text-xs font-medium text-slate-500 mb-1">Latitude</label>
                            <input
                                type="number"
                                value={latitude}
                                onChange={(e) => setLatitude(parseFloat(e.target.value))}
                                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-slate-500 mb-1">Longitude</label>
                            <input
                                type="number"
                                value={longitude}
                                onChange={(e) => setLongitude(parseFloat(e.target.value))}
                                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                            />
                        </div>
                    </div>
                </div>

                <button
                    onClick={() => predictMutation.mutate()}
                    disabled={predictMutation.isPending || !moeStatus?.model_loaded}
                    className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {predictMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                    Run MoE Prediction
                </button>

                {/* Prediction Results */}
                {prediction && (
                    <div className="mt-4 space-y-4">
                        <div className="flex items-center gap-2 mb-2">
                            {prediction.cached ? (
                                <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400">Cached</span>
                            ) : (
                                <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">Fresh</span>
                            )}
                        </div>

                        {/* Expert Routing Visualization */}
                        <div className="rounded-xl border border-slate-100 dark:border-white/5 p-4 bg-slate-50 dark:bg-white/[0.01]">
                            <h5 className="text-xs font-bold text-slate-500 mb-3">Expert Routing</h5>
                            <div className="grid grid-cols-5 gap-2">
                                {prediction.expert_routing.expert_usage.map((usage, idx) => (
                                    <div key={idx} className="text-center">
                                        <div className={cn(
                                            "w-full h-16 rounded-lg mb-1 flex items-center justify-center text-white font-bold",
                                            EXPERT_COLORS[moeStatus?.experts?.[idx] || ''] || 'bg-slate-400'
                                        )}>
                                            {(usage * 100).toFixed(0)}%
                                        </div>
                                        <span className="text-[10px] text-slate-400 capitalize">{moeStatus?.experts?.[idx]}</span>
                                    </div>
                                ))}
                            </div>
                            <p className="text-[10px] text-slate-400 mt-2">
                                Load Balance Loss: {prediction.expert_routing.load_balance_loss.toFixed(4)}
                            </p>
                        </div>

                        {/* Prediction Outputs */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {prediction.severity && (
                                <div className="rounded-xl border border-slate-100 dark:border-white/5 p-4">
                                    <h5 className="text-xs font-bold text-slate-500 mb-2">Severity</h5>
                                    <p className="text-lg font-bold text-red-600 capitalize">{prediction.severity.predicted_severity}</p>
                                    <p className="text-xs text-slate-400">Confidence: {(prediction.severity.confidence * 100).toFixed(1)}%</p>
                                </div>
                            )}
                            {prediction.spread && (
                                <div className="rounded-xl border border-slate-100 dark:border-white/5 p-4">
                                    <h5 className="text-xs font-bold text-slate-500 mb-2">Spread</h5>
                                    <p className="text-lg font-bold text-blue-600">{prediction.spread.predicted_area_km2.toFixed(1)} km²</p>
                                    <p className="text-xs text-slate-400">CI: [{prediction.spread.ci_lower_km2.toFixed(1)}, {prediction.spread.ci_upper_km2.toFixed(1)}]</p>
                                </div>
                            )}
                            {prediction.impact && (
                                <div className="rounded-xl border border-slate-100 dark:border-white/5 p-4">
                                    <h5 className="text-xs font-bold text-slate-500 mb-2">Impact</h5>
                                    <p className="text-lg font-bold text-orange-600">{prediction.impact.predicted_casualties} casualties</p>
                                    <p className="text-xs text-slate-400">${(prediction.impact.predicted_damage_usd / 1e6).toFixed(1)}M damage</p>
                                </div>
                            )}
                            {prediction.anomaly && (
                                <div className="rounded-xl border border-slate-100 dark:border-white/5 p-4">
                                    <h5 className="text-xs font-bold text-slate-500 mb-2">Anomaly</h5>
                                    <p className={cn(
                                        "text-lg font-bold",
                                        prediction.anomaly.is_anomaly ? "text-red-600" : "text-emerald-600"
                                    )}>
                                        {prediction.anomaly.is_anomaly ? "Detected" : "Normal"}
                                    </p>
                                    <p className="text-xs text-slate-400">Score: {prediction.anomaly.anomaly_score.toFixed(3)}</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Error Display */}
            {predictMutation.isError && (
                <div className="rounded-xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 p-4">
                    <p className="text-sm text-red-700 dark:text-red-400">
                        {(predictMutation.error as any)?.message || 'Prediction failed'}
                    </p>
                </div>
            )}
        </div>
    )
}