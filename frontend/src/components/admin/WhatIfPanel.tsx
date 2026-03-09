'use client'

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { runWhatIfAnalysis, getTopInterventions, type WhatIfQuery, type WhatIfResult } from '@/lib/api/workflow'
import { FlaskConical, ArrowRight, Loader2, TrendingDown, Lightbulb, BarChart3 } from 'lucide-react'

const INTERVENTION_VARIABLES = [
    { value: 'response_time_hours', label: 'Response Time (hours)', min: 0.5, max: 48 },
    { value: 'resource_availability', label: 'Resource Availability (%)', min: 0, max: 100 },
    { value: 'ngo_proximity_km', label: 'NGO Proximity (km)', min: 1, max: 200 },
    { value: 'resource_quality_score', label: 'Resource Quality Score', min: 0, max: 100 },
]

const OUTCOME_VARIABLES = [
    { value: 'casualties', label: 'Casualties' },
    { value: 'economic_damage_usd', label: 'Economic Damage ($)' },
]

export function WhatIfPanel() {
    const [variable, setVariable] = useState('response_time_hours')
    const [currentVal, setCurrentVal] = useState(6)
    const [proposedVal, setProposedVal] = useState(2)
    const [outcomeVar, setOutcomeVar] = useState('casualties')
    const [result, setResult] = useState<WhatIfResult | null>(null)

    const analysisMutation = useMutation({
        mutationFn: (query: WhatIfQuery) => runWhatIfAnalysis(query),
        onSuccess: (data) => setResult(data),
    })

    const { data: topInterventions, isLoading: loadingTop } = useQuery({
        queryKey: ['top-interventions', outcomeVar],
        queryFn: () => getTopInterventions(outcomeVar, 5),
    })

    const selectedVar = INTERVENTION_VARIABLES.find(v => v.value === variable)

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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Intervention Variable
                        </label>
                        <select
                            value={variable}
                            onChange={(e) => setVariable(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                        >
                            {INTERVENTION_VARIABLES.map(v => (
                                <option key={v.value} value={v.value}>{v.label}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Outcome to Measure
                        </label>
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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Current Value
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
                            Proposed Value
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
                        intervention_variable: variable,
                        current_value: currentVal,
                        proposed_value: proposedVal,
                        outcome_variable: outcomeVar,
                    })}
                    disabled={analysisMutation.isPending}
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

            {/* Result */}
            {result && (
                <div className="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/20 p-6 space-y-4">
                    <h3 className="font-semibold text-purple-700 dark:text-purple-400 flex items-center gap-2">
                        <BarChart3 className="w-5 h-5" />
                        Counterfactual Result
                    </h3>

                    <div className="flex items-center gap-4 text-lg">
                        <div className="text-center">
                            <div className="text-sm text-slate-500">Original</div>
                            <div className="font-bold text-slate-900 dark:text-white">
                                {typeof result.original_value === 'number' ? result.original_value.toFixed(1) : result.original_value}
                            </div>
                        </div>
                        <ArrowRight className="w-5 h-5 text-slate-400" />
                        <div className="text-center">
                            <div className="text-sm text-slate-500">Counterfactual</div>
                            <div className="font-bold text-green-600">
                                {typeof result.counterfactual_value === 'number' ? result.counterfactual_value.toFixed(1) : result.counterfactual_value}
                            </div>
                        </div>
                        <div className="text-center ml-4">
                            <div className="text-sm text-slate-500">Difference</div>
                            <div className={`font-bold ${result.difference < 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {result.difference > 0 ? '+' : ''}{typeof result.difference === 'number' ? result.difference.toFixed(1) : result.difference}
                            </div>
                        </div>
                    </div>

                    {result.confidence_interval && (
                        <p className="text-xs text-slate-500">
                            95% CI: [{result.confidence_interval[0]?.toFixed(1)}, {result.confidence_interval[1]?.toFixed(1)}]
                        </p>
                    )}

                    <p className="text-sm text-slate-600 dark:text-slate-400 bg-white/50 dark:bg-slate-800/50 rounded-lg p-3">
                        {result.explanation}
                    </p>
                </div>
            )}

            {/* Top Interventions */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
                <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-4">
                    <Lightbulb className="w-5 h-5 text-amber-500" />
                    Top Recommended Interventions
                </h3>
                {loadingTop ? (
                    <Loader2 className="w-5 h-5 text-slate-400 animate-spin mx-auto" />
                ) : (
                    <div className="space-y-3">
                        {((topInterventions as any)?.interventions || []).map((item: any, idx: number) => (
                            <div
                                key={idx}
                                className="flex items-center justify-between p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50"
                            >
                                <div className="flex items-center gap-3">
                                    <span className="w-6 h-6 rounded-full bg-purple-100 dark:bg-purple-900 text-purple-600 dark:text-purple-400 flex items-center justify-center text-xs font-bold">
                                        {idx + 1}
                                    </span>
                                    <div>
                                        <div className="font-medium text-sm text-slate-900 dark:text-white">
                                            {item.variable?.replace(/_/g, ' ')}
                                        </div>
                                        <div className="text-xs text-slate-500">
                                            {item.current_value} → {item.proposed_value}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1 text-green-600">
                                    <TrendingDown className="w-4 h-4" />
                                    <span className="font-medium text-sm">
                                        {typeof item.estimated_reduction === 'number' ? Math.abs(item.estimated_reduction).toFixed(1) : item.estimated_reduction ?? '?'} fewer
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
