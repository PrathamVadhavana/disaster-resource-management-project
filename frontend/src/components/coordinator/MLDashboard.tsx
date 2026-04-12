'use client'

import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Cpu, Activity, Zap, Play, CheckCircle2, AlertCircle,
    Thermometer, Wind, Droplets, Map, Users, BarChart, Loader2, Sparkles, Database, Layers,
    Shield, Briefcase, Info, RefreshCcw, TrendingUp, Heart, Globe, Building2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { MoEDashboard } from '@/components/admin/MoEDashboard'
import { BarChart as ReBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const SCENARIOS = [
    {
        id: 'wildfire_supercell',
        name: 'The Omega Firestorm',
        description: 'Total ecosystem collapse event',
        icon: Thermometer,
        features: {
            temperature: 52,
            wind_speed: 110,
            humidity: 5,
            pressure: 1015,
            disaster_type: 'wildfire',
            current_area: 850,
            affected_population: 150000
        }
    },
    {
        id: 'catastrophic_hurricane',
        name: 'Category 6 Superstorm',
        description: 'Atmospheric pressure collapse',
        icon: Wind,
        features: {
            temperature: 28,
            wind_speed: 320,
            humidity: 95,
            pressure: 920,
            disaster_type: 'hurricane',
            current_area: 1200,
            affected_population: 850000
        }
    },
    {
        id: 'urban_tsunami',
        name: 'Mega-Tsunami Impact',
        description: 'Coastal infrastructure failure',
        icon: Droplets,
        features: {
            temperature: 18,
            wind_speed: 45,
            humidity: 90,
            pressure: 1005,
            disaster_type: 'tsunami',
            current_area: 50,
            affected_population: 2400000
        }
    }
]

export default function MLDashboard() {
    const [activeView, setActiveView] = useState<'sandbox' | 'moe'>('sandbox')
    const [selectedType, setSelectedType] = useState<'severity' | 'spread' | 'impact'>('severity')
    const [runEnsemble, setRunEnsemble] = useState(true)
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

    // FIXED: Direct mapping to API schema to ensure all keys reach the backend
    const sandboxMutation = useMutation({
        mutationFn: (payload: { prediction_type: string; features: any; run_ensemble: boolean }) => 
            api.predictSandbox(payload),
    })

    const handleFeatureChange = (key: string, value: any) => {
        setFeatures((prev: any) => {
            if (typeof value === 'number' && Number.isNaN(value)) {
                return prev
            }
            return { ...prev, [key]: value }
        })
    }

    const triggerInference = (typeOverride?: string, featuresOverride?: any) => {
        sandboxMutation.mutate({
            prediction_type: typeOverride || selectedType,
            features: featuresOverride || features,
            run_ensemble: runEnsemble
        })
    }

    const applyScenario = (scenarioFeatures: any) => {
        const merged = { ...features, ...scenarioFeatures }
        setFeatures(merged)
        // Immediate feedback upon scenario selection
        triggerInference(selectedType, merged)
    }

    // AUTO-REFLECT: Trigger inference when switching between target analysis types
    useEffect(() => {
        if (activeView === 'sandbox') {
            triggerInference()
        }
    }, [selectedType, activeView, runEnsemble])

    // DEBOUNCED AUTO-REFLECT: Trigger on feature changes (sliders/inputs)
    useEffect(() => {
        if (activeView !== 'sandbox') return
        
        const timeout = setTimeout(() => {
            triggerInference()
        }, 500)
        
        return () => clearTimeout(timeout)
    }, [features])

    const DISASTER_TYPES = ['flood', 'wildfire', 'earthquake', 'hurricane', 'cyclone', 'tornado', 'tsunami', 'other']

    const importanceData = useMemo(() => {
        return sandboxMutation.data?.result.feature_importance?.filter((f: any) => f.percentage > 1).slice(0, 5) || []
    }, [sandboxMutation.data])

    return (
        <div className="space-y-6">
            {/* View Toggle */}
            <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/5 w-fit">
                <button
                    onClick={() => setActiveView('sandbox')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all focus:outline-none",
                        activeView === 'sandbox'
                            ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                    )}
                >
                    <Play className="w-4 h-4" />
                    Strategic Sandbox
                </button>
                <button
                    onClick={() => setActiveView('moe')}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all focus:outline-none",
                        activeView === 'moe'
                            ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                    )}
                >
                    <Layers className="w-4 h-4" />
                    MoE Expert Pool
                </button>
            </div>

            {activeView === 'moe' ? (
                <MoEDashboard />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                    {/* Left Column Diagnostics */}
                    <div className="lg:col-span-3 space-y-6">
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900/50 p-5 shadow-sm">
                            <h3 className="text-xs font-heavy text-slate-400 mb-4 flex items-center gap-2 uppercase tracking-widest">
                                <Cpu className="w-3.5 h-3.5 text-blue-500" />
                                Model Orchestrator
                            </h3>

                            {infoLoading ? (
                                <div className="space-y-3">
                                    {[1, 2, 3].map(i => <div key={i} className="h-4 bg-slate-100 dark:bg-white/5 rounded-md animate-pulse" />)}
                                </div>
                            ) : modelInfo ? (
                                <div className="space-y-4">
                                    <div className="space-y-2">
                                        {[
                                            { label: 'SeverityForecaster', status: modelInfo.severity_loaded },
                                            { label: 'SpatialSpreadEngine', status: modelInfo.spread_loaded },
                                            { label: 'ImpactEstimator', status: modelInfo.impact_loaded },
                                        ].map((m, i) => (
                                            <div key={i} className="flex items-center justify-between">
                                                <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{m.label}</span>
                                                <div className={cn(
                                                    "w-2 h-2 rounded-full",
                                                    m.status ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-amber-500"
                                                )} />
                                            </div>
                                        ))}
                                    </div>
                                    <div className="pt-3 border-t border-slate-100 dark:border-white/5">
                                        <div className="flex items-center justify-between text-[10px] text-slate-400 font-bold uppercase">
                                            <span>Inference Latency</span>
                                            <span className="text-emerald-500">~12.4ms</span>
                                        </div>
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900/50 p-5 shadow-sm">
                            <h3 className="text-xs font-heavy text-slate-400 mb-4 flex items-center gap-2 uppercase tracking-widest">
                                <RefreshCcw className="w-3.5 h-3.5 text-indigo-500" />
                                Rapid Presets
                            </h3>
                            <div className="space-y-2">
                                {SCENARIOS.map(s => (
                                    <button
                                        key={s.id}
                                        onClick={() => applyScenario(s.features)}
                                        className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-white/2 hover:border-indigo-500/50 hover:bg-indigo-50/10 dark:hover:bg-indigo-500/5 transition-all text-left group"
                                    >
                                        <div className="w-8 h-8 flex items-center justify-center rounded-lg bg-white dark:bg-white/5 shadow-sm group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                                            <s.icon className="w-4 h-4" />
                                        </div>
                                        <div className="flex-1">
                                            <div className="text-[11px] font-black text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{s.name}</div>
                                            <div className="text-[8px] text-slate-400 uppercase font-bold tracking-tight mt-0.5">{s.description}</div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-2xl bg-linear-to-br from-indigo-600 to-blue-700 p-5 text-white shadow-xl relative overflow-hidden group">
                           <Shield className="absolute -bottom-2 -right-2 w-20 h-20 opacity-10 group-hover:scale-110 transition-transform duration-700" />
                           <p className="text-[11px] font-medium leading-relaxed mb-0 relative z-10">
                               <b>Chained Inference</b> is active. Predicting spread/impact now automatically accounts for atmospheric severity in real-time.
                           </p>
                        </div>
                    </div>

                    {/* Middle Column Controls */}
                    <div className="lg:col-span-6 space-y-6">
                        <div className="rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 p-8 shadow-sm">
                            <div className="flex items-center justify-between mb-8">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 rounded-full bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center">
                                        <Play className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                    </div>
                                    <div>
                                        <h2 className="text-xl font-black text-slate-900 dark:text-white leading-none">Intelligence Synthesis</h2>
                                        <p className="text-[10px] text-slate-500 mt-1 uppercase font-bold tracking-widest">Global Stressor Configuration</p>
                                    </div>
                                </div>
                                
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none mr-2">Ensemble</div>
                                    <input 
                                        type="checkbox" 
                                        checked={runEnsemble} 
                                        onChange={() => setRunEnsemble(!runEnsemble)}
                                        className="sr-only peer"
                                    />
                                    <div className="w-10 h-5 bg-slate-200 dark:bg-white/10 rounded-full peer-checked:bg-indigo-500 transition-all relative after:content-[''] after:absolute after:top-1 after:left-1 after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-5" />
                                </label>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-8">
                                <div className="space-y-4">
                                   <div className="space-y-1.5">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Disaster Type</label>
                                            <span className="text-[10px] font-bold text-blue-500 uppercase tracking-widest">{features.disaster_type}</span>
                                        </div>
                                        <select
                                            value={features.disaster_type}
                                            onChange={(e) => handleFeatureChange('disaster_type', e.target.value)}
                                            className="w-full h-11 px-4 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5 text-sm font-bold text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500 appearance-none transition-all"
                                        >
                                            {DISASTER_TYPES.map(dt => (
                                                <option key={dt} value={dt} className="text-slate-900 bg-white">
                                                    {dt === 'tsunami' ? 'Coastal Tsunami' : dt.charAt(0).toUpperCase() + dt.slice(1)}
                                                </option>
                                            ))}
                                        </select>
                                   </div>

                                   <div className="space-y-3">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Temperature Baseline</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{features.temperature}°C</span>
                                        </div>
                                        <input 
                                            type="range" min="0" max="100" step="1" 
                                            value={features.temperature} 
                                            onChange={(e) => handleFeatureChange('temperature', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-orange-500" 
                                        />
                                   </div>

                                   <div className="space-y-3">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Wind Intensity</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{features.wind_speed} km/h</span>
                                        </div>
                                        <input 
                                            type="range" min="0" max="300" step="5" 
                                            value={features.wind_speed} 
                                            onChange={(e) => handleFeatureChange('wind_speed', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-blue-500" 
                                        />
                                   </div>

                                   {selectedType === 'impact' && (
                                     <div className="space-y-3 animate-in fade-in slide-in-from-left-2 transition-all">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Infrastructure Density</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{(features.infrastructure_density * 100).toFixed(0)}%</span>
                                        </div>
                                        <input 
                                            type="range" min="0" max="1" step="0.05" 
                                            value={features.infrastructure_density} 
                                            onChange={(e) => handleFeatureChange('infrastructure_density', parseFloat(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-slate-500" 
                                        />
                                     </div>
                                   )}
                                </div>

                                <div className="space-y-4">
                                    <div className="space-y-3">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Humidity Level</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{features.humidity}%</span>
                                        </div>
                                        <input 
                                            type="range" min="0" max="100" step="1" 
                                            value={features.humidity} 
                                            onChange={(e) => handleFeatureChange('humidity', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-emerald-500" 
                                        />
                                    </div>

                                    <div className="space-y-3">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Barometric Pressure</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{features.pressure} mb</span>
                                        </div>
                                        <input 
                                            type="range" min="940" max="1050" step="1" 
                                            value={features.pressure} 
                                            onChange={(e) => handleFeatureChange('pressure', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-indigo-500" 
                                        />
                                    </div>

                                    <div className="space-y-1.5">
                                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Population at Risk</label>
                                        <input
                                            type="number"
                                            value={features.affected_population}
                                            onChange={(e) => handleFeatureChange('affected_population', parseInt(e.target.value))}
                                            className="w-full h-11 px-4 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5 text-sm font-bold text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500 transition-all font-mono"
                                        />
                                    </div>

                                    {selectedType === 'spread' && (
                                     <div className="space-y-3 animate-in fade-in slide-in-from-right-2 transition-all">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Initial Growth Area (km²)</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">{features.current_area}</span>
                                        </div>
                                        <input 
                                            type="range" min="1" max="1000" step="10" 
                                            value={features.current_area} 
                                            onChange={(e) => handleFeatureChange('current_area', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-purple-500" 
                                        />
                                     </div>
                                   )}

                                   {selectedType === 'impact' && (
                                     <div className="space-y-3 animate-in fade-in slide-in-from-right-2 transition-all">
                                        <div className="flex justify-between">
                                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Local GDP per Capita</label>
                                            <span className="text-sm font-black text-slate-900 dark:text-white">${features.gdp_per_capita.toLocaleString()}</span>
                                        </div>
                                        <input 
                                            type="range" min="1000" max="80000" step="1000" 
                                            value={features.gdp_per_capita} 
                                            onChange={(e) => handleFeatureChange('gdp_per_capita', parseInt(e.target.value))}
                                            className="w-full h-1.5 bg-slate-100 dark:bg-white/10 rounded-lg appearance-none cursor-pointer accent-emerald-600" 
                                        />
                                     </div>
                                   )}
                                </div>
                            </div>

                            <div className="mt-10 flex gap-4">
                                {(['severity', 'spread', 'impact'] as const).map(t => (
                                    <button
                                        key={t}
                                        onClick={() => setSelectedType(t)}
                                        className={cn(
                                            "flex-1 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all",
                                            selectedType === t
                                                ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-xl shadow-slate-200 dark:shadow-none scale-[1.02]"
                                                : "bg-slate-50 dark:bg-white/5 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300"
                                        )}
                                    >
                                        Target: {t}
                                    </button>
                                ))}
                            </div>

                            <button
                                onClick={triggerInference}
                                disabled={sandboxMutation.isPending}
                                className={cn(
                                    "w-full mt-6 h-16 rounded-2xl bg-linear-to-r from-blue-600 via-indigo-600 to-indigo-700 text-white font-black uppercase tracking-widest text-sm flex items-center justify-center gap-3 transition-all hover:opacity-90 active:scale-[0.98] shadow-2xl shadow-blue-500/20 disabled:opacity-50",
                                    sandboxMutation.isPending && "animate-pulse"
                                )}
                            >
                                {sandboxMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                                Initiate Machine Inference
                            </button>
                        </div>

                        {/* Recommendation Cards */}
                        {sandboxMutation.data?.result.recommendations && (
                            <div className="rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 p-8 shadow-sm">
                                <h3 className="text-sm font-black text-slate-900 dark:text-white mb-6 flex items-center gap-2">
                                    <Briefcase className="w-5 h-5 text-emerald-500" />
                                    Strategic Deployment Plan
                                </h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {sandboxMutation.data.result.recommendations.map((r: any, idx: number) => (
                                        <div key={idx} className="p-4 rounded-2xl border border-slate-100 dark:border-white/5 bg-slate-50/50 dark:bg-white/1 flex gap-4 animate-in zoom-in-95 transition-all">
                                            <div className={cn(
                                                "w-12 h-12 shrink-0 rounded-xl flex items-center justify-center shadow-sm",
                                                r.priority === 'Critical' ? "bg-red-500 text-white shadow-[0_0_15px_rgba(239,68,68,0.4)]" : 
                                                r.priority === 'High' ? "bg-orange-500 text-white" : "bg-blue-500 text-white"
                                            )}>
                                                {r.type === 'Water' ? <Droplets className="w-6 h-6" /> : 
                                                 r.type === 'Emergency Food' ? <Heart className="w-6 h-6" /> : 
                                                 r.type === 'Mobile Shelter' ? <Globe className="w-6 h-6" /> :
                                                 <Activity className="w-6 h-6" />}
                                            </div>
                                            <div>
                                                <div className="flex items-center gap-2 mb-0.5">
                                                    <span className="text-xs font-black text-slate-900 dark:text-white uppercase tracking-tighter">{r.type}</span>
                                                    <span className={cn(
                                                        "text-[8px] font-black uppercase px-2 py-0.5 rounded-full",
                                                        r.priority === 'Critical' ? "bg-red-500/10 text-red-600" :
                                                        r.priority === 'High' ? "bg-orange-500/10 text-orange-600" : "bg-blue-500/10 text-blue-600"
                                                    )}>
                                                        {r.priority}
                                                    </span>
                                                </div>
                                                <div className="text-lg font-black text-slate-700 dark:text-slate-300 lining-nums">
                                                    {(r.quantity || 0).toLocaleString()} <span className="text-[10px] text-slate-400 uppercase">{r.unit}</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Right Column Analysis */}
                    <div className="lg:col-span-3 space-y-6">
                        <div className="rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 p-6 shadow-sm overflow-hidden relative min-h-[400px]">
                            <div className="flex items-center justify-between mb-6">
                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">Inference Output</span>
                                {sandboxMutation.data ? (
                                    <span className="flex items-center gap-1.5 text-[8px] font-black text-emerald-500 uppercase">
                                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" /> Active
                                    </span>
                                ) : sandboxMutation.isError ? (
                                    <span className="text-[8px] font-black text-red-500 uppercase flex items-center gap-1">
                                        <AlertCircle className="w-2 h-2" /> Error
                                    </span>
                                ) : (
                                    <span className="text-[8px] font-black text-slate-300 dark:text-slate-600 uppercase">Idle</span>
                                )}
                            </div>

                            {sandboxMutation.isError && (
                                <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-500 mb-6 animate-in slide-in-from-top-2">
                                    <div className="flex items-start gap-3">
                                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                                        <div>
                                            <div className="text-[10px] font-black uppercase tracking-widest">Inference Failure</div>
                                            <div className="text-[11px] font-medium leading-relaxed mt-1">
                                                {(sandboxMutation.error as any)?.message || 'Agent failed to synthesize data. Check parameters and retry.'}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {sandboxMutation.data ? (
                                <div className="space-y-6">
                                    <div className="text-center py-8 rounded-3xl bg-slate-50 dark:bg-white/2 border border-slate-100 dark:border-white/5 animate-in slide-in-from-top-4 transition-all duration-500">
                                        {selectedType === 'severity' && (
                                            <>
                                                <div className={cn(
                                                    "text-4xl font-black uppercase mb-1 drop-shadow-[0_2px_10px_rgba(0,0,0,0.1)]",
                                                    sandboxMutation.data.result.predicted_severity === 'critical' ? 'text-red-500' :
                                                        sandboxMutation.data.result.predicted_severity === 'high' ? 'text-orange-500' : 'text-blue-500'
                                                )}>
                                                    {sandboxMutation.data.result.predicted_severity}
                                                </div>
                                                <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Severity Index</p>
                                            </>
                                        )}
                                        {selectedType === 'spread' && (
                                            <>
                                                <div className="text-4xl font-black text-indigo-500 mb-1 drop-shadow-sm lining-nums">
                                                    {(sandboxMutation.data.result.predicted_area_km2 || 0).toLocaleString()}
                                                </div>
                                                <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">km² Est. Growth</p>
                                            </>
                                        )}
                                        {selectedType === 'impact' && (
                                            <div className="space-y-4">
                                                <div>
                                                    <div className="text-4xl font-black text-red-500 mb-0.5 lining-nums">
                                                        {(sandboxMutation.data.result.predicted_casualties || 0).toLocaleString()}
                                                    </div>
                                                    <p className="text-[9px] text-slate-400 font-bold uppercase tracking-widest">Predicted Casualties</p>
                                                </div>
                                                <div className="pt-6 border-t border-slate-200/50 dark:border-white/5 mx-6">
                                                    <div className="text-3xl font-black text-emerald-500 mb-0.5 lining-nums">
                                                        ${((sandboxMutation.data.result.predicted_damage_usd || 0) / 1000000).toFixed(1)}M
                                                    </div>
                                                    <p className="text-[9px] text-slate-400 font-bold uppercase tracking-widest">Economic Damage</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest">
                                            <span className="text-slate-400">Confidence Score</span>
                                            <span className="text-slate-900 dark:text-white leading-none">{(sandboxMutation.data.result.confidence_score * 100).toFixed(1)}%</span>
                                        </div>
                                        <div className="h-2 w-full bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                            <div 
                                                className="h-full bg-linear-to-r from-blue-500 to-indigo-600 transition-all duration-1000 ease-out"
                                                style={{ width: `${sandboxMutation.data.result.confidence_score * 100}%` }}
                                            />
                                        </div>
                                    </div>

                                    {sandboxMutation.data.result.ensemble && (
                                        <div className="p-4 rounded-2xl bg-indigo-50/50 dark:bg-indigo-500/5 border border-indigo-100 dark:border-indigo-500/10 animate-in slide-in-from-bottom-2">
                                            <div className="flex items-center gap-2 mb-2">
                                                <TrendingUp className="w-3.5 h-3.5 text-indigo-500" />
                                                <span className="text-[10px] font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-widest">Model Consensus</span>
                                            </div>
                                            <div className="flex items-center justify-between">
                                                <span className="text-[11px] font-bold text-slate-500">Agreement</span>
                                                <span className={cn(
                                                    "text-[11px] font-black px-2 py-0.5 rounded-full",
                                                    sandboxMutation.data.result.ensemble.agreement === 'High' ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600"
                                                )}>{sandboxMutation.data.result.ensemble.agreement}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="h-64 flex flex-col items-center justify-center text-center">
                                    <Sparkles className="w-10 h-10 text-slate-200 dark:text-white/5 mb-4 animate-pulse" />
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-8 leading-relaxed">
                                        System ready for input. Configure environment parameters to begin.
                                    </p>
                                </div>
                            )}
                        </div>

                        {/* XAI Chart */}
                        {importanceData.length > 0 && (
                            <div className="rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 p-6 shadow-sm">
                                <h3 className="text-[10px] font-black text-slate-400 mb-4 flex items-center gap-2 uppercase tracking-widest">
                                    <BarChart className="w-3.5 h-3.5 text-blue-500" />
                                    Dynamic Attribution
                                </h3>
                                <div className="h-48 w-full -ml-8">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <ReBarChart
                                            layout="vertical"
                                            data={importanceData}
                                            margin={{ top: 0, right: 30, left: 10, bottom: 0 }}
                                            key={sandboxMutation.data?.timestamp}
                                        >
                                            <XAxis type="number" hide />
                                            <YAxis 
                                                dataKey="feature" 
                                                type="category" 
                                                axisLine={false} 
                                                tickLine={false} 
                                                tick={{ fill: '#94a3b8', fontSize: 8, fontWeight: 700 }}
                                                width={90}
                                            />
                                            <Tooltip 
                                                cursor={{ fill: 'transparent' }} 
                                                content={({ active, payload }) => {
                                                    if (active && payload?.[0]) {
                                                        return (
                                                            <div className="bg-slate-900 border border-white/10 text-white text-[10px] px-2 py-1 rounded-md font-bold shadow-xl">
                                                                {payload[0].value}% Impact Weight
                                                            </div>
                                                        )
                                                    }
                                                    return null
                                                }}
                                            />
                                            <Bar dataKey="percentage" radius={[0, 4, 4, 0]} barSize={10} animationDuration={1000}>
                                                {importanceData.map((entry: any, index: number) => (
                                                    <Cell key={`cell-${index}`} fill={index === 0 ? '#6366f1' : index === 1 ? '#818cf8' : '#cbd5e1'} className="dark:opacity-80" />
                                                ))}
                                            </Bar>
                                        </ReBarChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
