'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
    getTopInterventions,
    getWhatIfContext,
    runWhatIfAnalysis,
    type WhatIfContextResponse,
    type WhatIfQuery,
    type WhatIfResult,
} from '@/lib/api/workflow'
import { api } from '@/lib/api'
import { FlaskConical, ArrowRight, Loader2, TrendingDown, Lightbulb, BarChart3, AlertTriangle, Info, Zap, Clock, MapPin, Target, CheckCircle2, ArrowDown, ArrowUp } from 'lucide-react'
import { cn } from '@/lib/utils'

const INTERVENTION_VARIABLES = [
    { value: 'response_time_hours', label: 'Response Time', unit: 'hours', min: 0.5, max: 48, desc: 'The factor you\'re changing (e.g. reducing response time from 6h to 2h)' },
    { value: 'resource_availability', label: 'Resource Availability', unit: '%', min: 0, max: 100, desc: 'Percentage of resources available for deployment' },
    { value: 'ngo_proximity_km', label: 'NGO Proximity', unit: 'km', min: 1, max: 200, desc: 'Distance to nearest NGO facility' },
    { value: 'resource_quality_score', label: 'Resource Quality Score', unit: 'score', min: 0, max: 100, desc: 'Quality rating of available resources (0-100)' },
]

const OUTCOME_VARIABLES = [
    { value: 'casualties', label: 'Casualties', desc: 'What you want to see improve (e.g. casualties, resource delivery rate)' },
    { value: 'economic_damage_usd', label: 'Economic Damage ($)', desc: 'Financial impact in USD' },
]

const PRESET_SCENARIOS = [
    { label: 'Double volunteer count', variable: 'resource_availability', current: 50, proposed: 100 },
    { label: 'Halve response time', variable: 'response_time_hours', current: 6, proposed: 3 },
    { label: 'Add 50 water units', variable: 'resource_quality_score', current: 60, proposed: 90 },
]

function clamp(value: number, min: number, max: number) {
    return Math.max(min, Math.min(max, value))
}

function getSuggestedValue(variable: string, currentValue: number, min: number, max: number) {
    const proposed = variable === 'response_time_hours' || variable === 'ngo_proximity_km'
        ? currentValue * 0.75
        : currentValue * 1.25
    return Number(clamp(proposed, min, max).toFixed(1))
}

function formatNumber(value: number | undefined) {
    if (typeof value !== 'number' || Number.isNaN(value)) return '0'
    return new Intl.NumberFormat().format(Math.round(value))
}

// Simple causal graph visualization
function CausalGraph({ result, variable, outcomeVar }: { result: WhatIfResult; variable: string; outcomeVar: string }) {
    const varLabel = INTERVENTION_VARIABLES.find(v => v.value === variable)?.label || variable
    const outcomeLabel = OUTCOME_VARIABLES.find(v => v.value === outcomeVar)?.label || outcomeVar
    const impact = result.difference
    const isPositive = impact < 0

    return (
        <div className="relative p-6 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
            <div className="flex items-center justify-between">
                {/* Intervention Node */}
                <div className="flex flex-col items-center">
                    <div className="w-20 h-20 rounded-xl bg-purple-100 dark:bg-purple-500/20 flex items-center justify-center mb-2">
                        <Zap className="w-8 h-8 text-purple-600 dark:text-purple-400" />
                    </div>
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-300 text-center">{varLabel}</span>
                </div>

                {/* Edge */}
                <div className="flex-1 mx-4 relative">
                    <div className="h-0.5 bg-gradient-to-r from-purple-500 to-emerald-500 w-full" />
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
                        <div className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center",
                            isPositive ? 'bg-green-100 dark:bg-green-500/20' : 'bg-red-100 dark:bg-red-500/20'
                        )}>
                            {isPositive ? <ArrowDown className="w-4 h-4 text-green-600" /> : <ArrowUp className="w-4 h-4 text-red-600" />}
                        </div>
                    </div>
                    <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1">
                        <span className={cn(
                            "text-xs font-bold px-2 py-0.5 rounded-full",
                            isPositive ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                        )}>
                            {isPositive ? 'Reduces' : 'Increases'} {Math.abs(impact).toFixed(1)}
                        </span>
                    </div>
                </div>

                {/* Outcome Node */}
                <div className="flex flex-col items-center">
                    <div className="w-20 h-20 rounded-xl bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center mb-2">
                        <Target className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-300 text-center">{outcomeLabel}</span>
                </div>
            </div>
        </div>
    )
}

export function WhatIfPanel() {
    const [variable, setVariable] = useState('response_time_hours')
    const [currentVal, setCurrentVal] = useState(6)
    const [proposedVal, setProposedVal] = useState(2)
    const [outcomeVar, setOutcomeVar] = useState('casualties')
    const [selectedDisaster, setSelectedDisaster] = useState('')
    const [result, setResult] = useState<WhatIfResult | null>(null)

    const { data: disasters } = useQuery({
        queryKey: ['disasters-for-whatif'],
        queryFn: () => api.getDisasters({ status: 'active' }),
        retry: false,
    })

    // Fetch disaster details when a disaster is selected
    const { data: selectedDisasterData } = useQuery({
        queryKey: ['disaster-details', selectedDisaster],
        queryFn: () => selectedDisaster ? api.getDisaster(selectedDisaster) : null,
        enabled: !!selectedDisaster,
        retry: false,
    })

    const { data: whatIfContext, isLoading: loadingContext, error: contextError } = useQuery<WhatIfContextResponse>({
        queryKey: ['what-if-context', selectedDisaster],
        queryFn: () => getWhatIfContext(selectedDisaster || undefined),
        retry: false,
    })

    useEffect(() => {
        const selectedVariable = INTERVENTION_VARIABLES.find((entry) => entry.value === variable)
        const observedValue = whatIfContext?.observation?.[variable]
        if (!selectedVariable || typeof observedValue !== 'number' || Number.isNaN(observedValue)) {
            return
        }

        const boundedCurrent = clamp(observedValue, selectedVariable.min, selectedVariable.max)
        setCurrentVal(Number(boundedCurrent.toFixed(1)))
        setProposedVal(getSuggestedValue(variable, boundedCurrent, selectedVariable.min, selectedVariable.max))
    }, [variable, whatIfContext])

    const analysisMutation = useMutation({
        mutationFn: (query: WhatIfQuery) => runWhatIfAnalysis(query),
        onSuccess: (data) => setResult(data),
    })

    const { data: topInterventions, isLoading: loadingTop, error: topInterventionsError } = useQuery({
        queryKey: ['top-interventions', outcomeVar, selectedDisaster],
        queryFn: () => getTopInterventions(outcomeVar, 5, selectedDisaster || undefined),
        retry: false,
    })

    const selectedVar = INTERVENTION_VARIABLES.find(v => v.value === variable)
    const selectedOutcome = OUTCOME_VARIABLES.find(v => v.value === outcomeVar)

    const applyPreset = (preset: typeof PRESET_SCENARIOS[0]) => {
        setVariable(preset.variable)
        setCurrentVal(preset.current)
        setProposedVal(preset.proposed)
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <FlaskConical className="w-6 h-6 text-purple-500" />
                    What-If Analysis
                </h2>
                <p className="text-sm text-slate-500 mt-1">
                    Explore counterfactual scenarios using causal AI to understand intervention impacts
                </p>
            </div>

            {/* Input Form */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 space-y-4">
                <h3 className="font-semibold text-slate-900 dark:text-white">Configure Scenario</h3>

                {whatIfContext && (
                    <div className="rounded-lg border border-purple-200 dark:border-purple-900/40 bg-purple-50/60 dark:bg-purple-950/20 p-4 text-sm text-slate-600 dark:text-slate-300">
                        <p className="font-medium text-slate-900 dark:text-white mb-1">Live context from Supabase</p>
                        <p>
                            {formatNumber(whatIfContext.summary.active_request_count)} active requests, {formatNumber(whatIfContext.summary.victims_impacted)} impacted victims, and {whatIfContext.summary.availability_pct.toFixed(1)}% current resource availability.
                        </p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{whatIfContext.derived_from}</p>
                    </div>
                )}

                {contextError && (
                    <div className="rounded-lg border border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-950/20 p-3 text-sm text-red-600 dark:text-red-400">
                        {(contextError as Error).message}
                    </div>
                )}

                {/* Preset Scenarios */}
                <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Preset Scenarios
                    </label>
                    <div className="flex flex-wrap gap-2">
                        {PRESET_SCENARIOS.map((preset, i) => (
                            <button
                                key={i}
                                onClick={() => applyPreset(preset)}
                                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-purple-50 dark:hover:bg-purple-500/10 hover:border-purple-300 dark:hover:border-purple-500/30 hover:text-purple-700 dark:hover:text-purple-400 transition-colors"
                            >
                                {preset.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <div className="flex items-center gap-1 mb-1">
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
                                Intervention Variable
                            </label>
                            <div className="group relative">
                                <Info className="w-3.5 h-3.5 text-slate-400 cursor-help" />
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-10 shadow-xl max-w-xs">
                                    {selectedVar?.desc}
                                    <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-700" />
                                </div>
                            </div>
                        </div>
                        <select
                            value={variable}
                            onChange={(e) => setVariable(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                        >
                            {INTERVENTION_VARIABLES.map(v => (
                                <option key={v.value} value={v.value}>{v.label} ({v.unit})</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <div className="flex items-center gap-1 mb-1">
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
                                Outcome to Measure
                            </label>
                            <div className="group relative">
                                <Info className="w-3.5 h-3.5 text-slate-400 cursor-help" />
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-10 shadow-xl max-w-xs">
                                    {selectedOutcome?.desc}
                                    <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-700" />
                                </div>
                            </div>
                        </div>
                        <select
                            value={outcomeVar}
                            onChange={(e) => setOutcomeVar(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                        >
                            {OUTCOME_VARIABLES.map(v => (
                                <option key={v.value} value={v.value}>{v.label}</option>
                            ))}
                        </select>
                    </div>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
                        Disaster Context (Optional)
                    </label>
                    <select
                        value={selectedDisaster}
                        onChange={(e) => setSelectedDisaster(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                    >
                        <option value="">All disasters (global)</option>
                        {(Array.isArray(disasters) ? disasters : []).map((d: any) => (
                            <option key={d.id} value={d.id}>{d.title || d.name} ({d.severity})</option>
                        ))}
                    </select>
                    {selectedDisasterData && (
                        <div className="mt-2 p-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg text-xs">
                            <div className="font-medium text-slate-700 dark:text-slate-300 mb-1">Disaster Details:</div>
                            <div className="text-slate-600 dark:text-slate-400">
                                Type: {selectedDisasterData.type || 'Unknown'} • 
                                Location: {selectedDisasterData.location_name || 'Unknown'} • 
                                Severity: {selectedDisasterData.severity || 'Unknown'}
                            </div>
                        </div>
                    )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Current Value {selectedVar && <span className="text-slate-400">({selectedVar.unit})</span>}
                        </label>
                        <input
                            type="number"
                            value={currentVal}
                            onChange={(e) => setCurrentVal(parseFloat(e.target.value))}
                            min={selectedVar?.min}
                            max={selectedVar?.max}
                            step="0.5"
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Proposed Value {selectedVar && <span className="text-slate-400">({selectedVar.unit})</span>}
                        </label>
                        <input
                            type="number"
                            value={proposedVal}
                            onChange={(e) => setProposedVal(parseFloat(e.target.value))}
                            min={selectedVar?.min}
                            max={selectedVar?.max}
                            step="0.5"
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                        />
                    </div>
                </div>

                <button
                    onClick={() => analysisMutation.mutate({
                        disaster_id: selectedDisaster || undefined,
                        intervention_variable: variable,
                        current_value: currentVal,
                        proposed_value: proposedVal,
                        outcome_variable: outcomeVar,
                    })}
                    disabled={analysisMutation.isPending || loadingContext || !!contextError}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium disabled:opacity-50"
                >
                    {analysisMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <FlaskConical className="w-4 h-4" />
                    )}
                    Run Analysis
                </button>
                {analysisMutation.isError && (
                    <p className="text-sm text-red-600 dark:text-red-400 mt-2">
                        {analysisMutation.error?.message || 'Analysis failed. Please try again.'}
                    </p>
                )}
            </div>

            {/* Result with Causal Graph and Comparison */}
            {result && (
                <div className="space-y-4">
                    {/* Causal Graph */}
                    <div className="rounded-xl border border-purple-200 dark:border-purple-800 bg-white dark:bg-slate-800 p-6">
                        <h3 className="font-semibold text-purple-700 dark:text-purple-400 flex items-center gap-2 mb-4">
                            <BarChart3 className="w-5 h-5" />
                            Causal Relationship
                        </h3>
                        <CausalGraph result={result} variable={variable} outcomeVar={outcomeVar} />
                    </div>

                    {/* Comparison Panel */}
                    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
                        <h3 className="font-semibold text-slate-900 dark:text-white mb-4">Scenario Comparison</h3>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600">
                                <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Current Scenario</p>
                                <p className="text-2xl font-bold text-slate-900 dark:text-white">
                                    {typeof result.original_value === 'number' ? result.original_value.toFixed(1) : result.original_value}
                                </p>
                                <p className="text-xs text-slate-500 mt-1">
                                    {selectedVar?.label}: {currentVal}{selectedVar?.unit}
                                </p>
                            </div>
                            <div className="p-4 rounded-xl bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20">
                                <p className="text-xs text-purple-600 dark:text-purple-400 uppercase tracking-wider mb-1">Proposed Scenario</p>
                                <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                                    {typeof result.counterfactual_value === 'number' ? result.counterfactual_value.toFixed(1) : result.counterfactual_value}
                                </p>
                                <p className="text-xs text-purple-500 mt-1">
                                    {selectedVar?.label}: {proposedVal}{selectedVar?.unit}
                                </p>
                            </div>
                        </div>
                        
                        <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50 flex items-center justify-between">
                            <div>
                                <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider">Delta</p>
                                <p className={cn(
                                    "text-xl font-bold",
                                    result.difference < 0 ? 'text-green-600' : 'text-red-600'
                                )}>
                                    {result.difference > 0 ? '+' : ''}{typeof result.difference === 'number' ? result.difference.toFixed(1) : result.difference}
                                </p>
                            </div>
                            {result.confidence_interval && (
                                <div className="text-right">
                                    <p className="text-xs text-slate-500 dark:text-slate-400">95% CI</p>
                                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                        [{result.confidence_interval[0]?.toFixed(1)}, {result.confidence_interval[1]?.toFixed(1)}]
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Plain-English Summary */}
                    <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20 p-6">
                        <h3 className="font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-2 mb-3">
                            <Lightbulb className="w-5 h-5" />
                            What this means
                        </h3>
                        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                            {result.explanation}
                        </p>
                    </div>

                    {/* Summary Stats */}
                    {result.summary && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                            <div className="rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3">
                                <p className="text-slate-500">Requests</p>
                                <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{formatNumber(result.summary.active_request_count)}</p>
                            </div>
                            <div className="rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3">
                                <p className="text-slate-500">Victims</p>
                                <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{formatNumber(result.summary.victims_impacted)}</p>
                            </div>
                            <div className="rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3">
                                <p className="text-slate-500">Urgent</p>
                                <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{formatNumber(result.summary.urgent_request_count)}</p>
                            </div>
                            <div className="rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-3">
                                <p className="text-slate-500">Availability</p>
                                <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{result.summary.availability_pct.toFixed(1)}%</p>
                            </div>
                        </div>
                    )}

                    {result.derived_from && (
                        <p className="text-xs text-slate-500 dark:text-slate-400">{result.derived_from}</p>
                    )}
                </div>
            )}

            {/* Top Interventions */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
                <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-4">
                    <Lightbulb className="w-5 h-5 text-amber-500" />
                    Top Recommended Interventions
                </h3>
                {(topInterventions as any)?.summary && (
                    <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
                        Based on {formatNumber((topInterventions as any).summary.active_request_count)} active requests and {formatNumber((topInterventions as any).summary.victims_impacted)} impacted victims.
                    </p>
                )}
                {loadingTop ? (
                    <div className="space-y-3">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="h-16 bg-slate-200 dark:bg-slate-700 rounded-lg animate-pulse" />
                        ))}
                    </div>
                ) : topInterventionsError ? (
                    <div className="text-center py-4 text-red-600 dark:text-red-400">
                        <p className="text-sm">Failed to load interventions: {(topInterventionsError as Error).message}</p>
                    </div>
                ) : !topInterventions || !(topInterventions as any)?.interventions || (topInterventions as any)?.interventions.length === 0 ? (
                    <div className="text-center py-4 text-slate-500">
                        <p className="text-sm">No interventions available for this outcome variable</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {((topInterventions as any)?.interventions || []).map((item: any, idx: number) => {
                            const impactPct = item.estimated_reduction ? Math.min(Math.abs(item.estimated_reduction) * 2, 100) : 50
                            const costLevel = idx === 0 ? 'Low' : idx === 1 ? 'Medium' : 'High'
                            const costColor = costLevel === 'Low' ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' :
                                costLevel === 'Medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400' :
                                'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                            
                            return (
                                <div
                                    key={idx}
                                    className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600"
                                >
                                    <div className="flex items-start justify-between mb-2">
                                        <div className="flex items-center gap-3">
                                            <span className="w-6 h-6 rounded-full bg-purple-100 dark:bg-purple-900 text-purple-600 dark:text-purple-400 flex items-center justify-center text-xs font-bold">
                                                {idx + 1}
                                            </span>
                                            <div>
                                                <div className="font-medium text-sm text-slate-900 dark:text-white">
                                                    {item.variable?.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
                                                </div>
                                                <div className="text-xs text-slate-500">
                                                    {item.current_value} → {item.proposed_value}
                                                </div>
                                            </div>
                                        </div>
                                        <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-bold", costColor)}>
                                            {costLevel} Cost
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="flex-1">
                                            <div className="h-2 bg-slate-200 dark:bg-slate-600 rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-gradient-to-r from-green-500 to-emerald-500 rounded-full transition-all duration-500"
                                                    style={{ width: `${impactPct}%` }}
                                                />
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1 text-green-600">
                                            <TrendingDown className="w-4 h-4" />
                                            <span className="font-medium text-sm">
                                                {typeof item.estimated_reduction === 'number' ? Math.abs(item.estimated_reduction).toFixed(1) : item.estimated_reduction ?? '?'} fewer
                                            </span>
                                        </div>
                                    </div>
                                    <button className="mt-3 w-full px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 hover:bg-purple-200 dark:hover:bg-purple-500/20 transition-colors">
                                        Apply This Intervention
                                    </button>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>
        </div>
    )
}