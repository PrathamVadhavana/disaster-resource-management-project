'use client'

import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Cpu, Activity, Zap, Play, CheckCircle2, AlertCircle,
    Thermometer, Wind, Droplets, Map, Users, BarChart, Loader2, Sparkles, Database, Layers
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { MoEDashboard } from '@/components/admin/MoEDashboard'

export default function MLDashboard() {
    const [activeView, setActiveView] = useState<'sandbox' | 'moe'>('sandbox')
    const [selectedType, setSelectedType] = useState<'severity' | 'spread' | 'impact'>('severity')
    const [features, setFeatures] = useState<any>({
        temperature: 25,
        wind_speed: 15,
        humidity: 50,
        pressure: 1013,
        disaster_type: 'flood',
        current_area: 10,
        days_active: 1,
        affected_population: 5000,
        gdp_per_capita: 12000,
        infrastructure_density: 0.6
    })

    const { data: modelInfo, isLoading: infoLoading } = useQuery({
        queryKey: ['model-info'],
        queryFn: () => api.getModelInfo(),
    })

    const sandboxMutation = useMutation({
        mutationFn: () => api.predictSandbox({
            prediction_type: selectedType,
            features
        }),
    })

    const handleFeatureChange = (key: string, value: any) => {
        setFeatures((prev: any) => ({ ...prev, [key]: value }))
    }

    const DISASTER_TYPES = ['flood', 'wildfire', 'earthquake', 'hurricane', 'cyclone', 'other']

    return (
        <div className="space-y-6">
            {/* View Toggle */}
            <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/5 w-fit">
                <button
                    onClick={() => setActiveView('sandbox')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                        activeView === 'sandbox'
                            ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                    )}
                >
                    <Play className="w-4 h-4" />
                    ML Sandbox
                </button>
                <button
                    onClick={() => setActiveView('moe')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                        activeView === 'moe'
                            ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                    )}
                >
                    <Layers className="w-4 h-4" />
                    MoE Model
                </button>
            </div>

            {activeView === 'moe' ? (
                <MoEDashboard />
            ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Model Health Status */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                            <Cpu className="w-4 h-4 text-blue-500" />
                            Model Engine Health
                        </h3>

                        {infoLoading ? (
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                                <Activity className="w-3 h-3 animate-pulse" /> Loading model metadata...
                            </div>
                        ) : modelInfo ? (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5">
                                    <div className="text-xs font-medium text-slate-500">Global Version</div>
                                    <div className="text-xs font-bold text-slate-900 dark:text-white">{modelInfo.version}</div>
                                </div>
                                <div className="space-y-2">
                                    {[
                                        { label: 'Severity Model', status: modelInfo.severity_loaded },
                                        { label: 'Spread Model', status: modelInfo.spread_loaded },
                                        { label: 'Impact Model', status: modelInfo.impact_loaded },
                                    ].map((m, i) => (
                                        <div key={i} className="flex items-center justify-between text-xs">
                                            <span className="text-slate-500">{m.label}</span>
                                            {m.status ? (
                                                <span className="flex items-center gap-1 text-green-600 font-bold">
                                                    <CheckCircle2 className="w-3 h-3" /> LOADED
                                                </span>
                                            ) : (
                                                <span className="flex items-center gap-1 text-amber-500 font-bold">
                                                    <AlertCircle className="w-3 h-3" /> FALLBACK
                                                </span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div className="text-xs text-red-500">Failed to fetch model info</div>
                        )}
                    </div>

                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-gradient-to-br from-indigo-600 to-blue-700 p-6 text-white overflow-hidden relative">
                        <Sparkles className="absolute -bottom-4 -right-4 w-24 h-24 opacity-20 rotate-12" />
                        <h3 className="text-sm font-bold mb-2 flex items-center gap-2">
                            <Zap className="w-4 h-4" />
                            Active Inference
                        </h3>
                        <p className="text-xs text-blue-100 leading-relaxed mb-4">
                            Models are running on the edge using local compute. Inference latency is currently optimized for real-time SitRep generation.
                        </p>
                        <div className="flex items-center gap-2 text-[10px] uppercase font-heavy tracking-widest opacity-80">
                            <Database className="w-3 h-3" /> Training Set: 14.2k Events
                        </div>
                    </div>
                </div>

                {/* Sandbox Prediction */}
                <div className="lg:col-span-2 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <Play className="w-4 h-4 text-emerald-500" />
                            Model Sandbox & Simulation
                        </h3>
                        <div className="flex gap-1 p-1 rounded-lg bg-slate-100 dark:bg-white/5">
                            {(['severity', 'spread', 'impact'] as const).map(t => (
                                <button
                                    key={t}
                                    onClick={() => setSelectedType(t)}
                                    className={cn(
                                        "px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all",
                                        selectedType === t
                                            ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
                                            : "text-slate-500 hover:text-slate-700"
                                    )}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Inputs */}
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1.5">
                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Disaster Type</label>
                                    <select
                                        value={features.disaster_type}
                                        onChange={(e) => handleFeatureChange('disaster_type', e.target.value)}
                                        className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        {DISASTER_TYPES.map(dt => <option key={dt} value={dt}>{dt.charAt(0).toUpperCase() + dt.slice(1)}</option>)}
                                    </select>
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Temperature (°C)</label>
                                    <input
                                        type="number"
                                        value={features.temperature}
                                        onChange={(e) => handleFeatureChange('temperature', parseFloat(e.target.value))}
                                        className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Wind Speed (km/h)</label>
                                    <input
                                        type="number"
                                        value={features.wind_speed}
                                        onChange={(e) => handleFeatureChange('wind_speed', parseFloat(e.target.value))}
                                        className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Humidity (%)</label>
                                    <input
                                        type="number"
                                        value={features.humidity}
                                        onChange={(e) => handleFeatureChange('humidity', parseFloat(e.target.value))}
                                        className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                {selectedType === 'spread' && (
                                    <div className="space-y-1.5 col-span-2">
                                        <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Current Area (km²)</label>
                                        <input
                                            type="number"
                                            value={features.current_area}
                                            onChange={(e) => handleFeatureChange('current_area', parseFloat(e.target.value))}
                                            className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    </div>
                                )}
                                {selectedType === 'impact' && (
                                    <div className="space-y-1.5 col-span-2">
                                        <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Population at Risk</label>
                                        <input
                                            type="number"
                                            value={features.affected_population}
                                            onChange={(e) => handleFeatureChange('affected_population', parseFloat(e.target.value))}
                                            className="w-full h-9 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    </div>
                                )}
                            </div>
                            <button
                                onClick={() => sandboxMutation.mutate()}
                                disabled={sandboxMutation.isPending}
                                className="w-full h-11 flex items-center justify-center gap-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-sm font-bold hover:opacity-90 disabled:opacity-50 transition-all shadow-lg"
                            >
                                {sandboxMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                                Run Inference
                            </button>
                        </div>

                        {/* Result Output */}
                        <div className="relative min-h-[200px] rounded-2xl border border-dashed border-slate-200 dark:border-white/10 flex flex-col items-center justify-center p-6 bg-slate-50/50 dark:bg-white/[0.01]">
                            {sandboxMutation.data ? (
                                <div className="w-full space-y-4 animate-in fade-in slide-in-from-bottom-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">Prediction Result</span>
                                        <span className="text-[10px] font-bold text-emerald-500 uppercase flex items-center gap-1">
                                            <div className="w-1 h-1 rounded-full bg-emerald-500 animate-ping" /> Success
                                        </span>
                                    </div>

                                    <div className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-white/5 shadow-sm">
                                        {selectedType === 'severity' && (
                                            <div className="text-center">
                                                <div className={cn(
                                                    "text-3xl font-black uppercase mb-1",
                                                    sandboxMutation.data.result.predicted_severity === 'critical' ? 'text-red-600' :
                                                        sandboxMutation.data.result.predicted_severity === 'high' ? 'text-orange-600' : 'text-blue-600'
                                                )}>
                                                    {sandboxMutation.data.result.predicted_severity}
                                                </div>
                                                <p className="text-[10px] text-slate-400 font-bold uppercase">Predicted Severity</p>
                                            </div>
                                        )}
                                        {selectedType === 'spread' && (
                                            <div className="text-center">
                                                <div className="text-3xl font-black text-blue-600 mb-1">
                                                    {sandboxMutation.data.result.predicted_area_km2} <span className="text-sm">km²</span>
                                                </div>
                                                <p className="text-[10px] text-slate-400 font-bold uppercase">Estimated Spread</p>
                                            </div>
                                        )}
                                        {selectedType === 'impact' && (
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="text-center border-r border-slate-100 dark:border-white/5">
                                                    <div className="text-xl font-black text-red-600 leading-none mb-1">
                                                        {sandboxMutation.data.result.predicted_casualties}
                                                    </div>
                                                    <p className="text-[8px] text-slate-400 font-bold uppercase">Casualties</p>
                                                </div>
                                                <div className="text-center">
                                                    <div className="text-xl font-black text-emerald-600 leading-none mb-1">
                                                        ${(sandboxMutation.data.result.predicted_damage_usd / 1000000).toFixed(1)}M
                                                    </div>
                                                    <p className="text-[8px] text-slate-400 font-bold uppercase">Damage</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    <div className="flex items-center justify-between text-[10px] font-bold">
                                        <span className="text-slate-400">Model Confidence</span>
                                        <span className="text-slate-900 dark:text-white">{(sandboxMutation.data.result.confidence_score * 100).toFixed(1)}%</span>
                                    </div>
                                    <div className="w-full h-1 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-blue-600 transition-all duration-1000"
                                            style={{ width: `${sandboxMutation.data.result.confidence_score * 100}%` }}
                                        />
                                    </div>
                                </div>
                            ) : (
                                <>
                                    <Sparkles className="w-10 h-10 text-slate-200 dark:text-white/5 mb-4" />
                                    <p className="text-xs text-slate-400 font-medium text-center">Set features and run inference to see model predictions</p>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>
            )}
        </div>
    )
}
