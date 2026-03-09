'use client'

import { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
    ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
    ResponsiveContainer, Cell, BarChart, Bar, Legend,
} from 'recharts'
import {
    Scale, TrendingUp, Shield, AlertTriangle, CheckCircle2,
    Loader2, Info, ChevronDown, ChevronUp, Zap, Heart,
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface FairnessPlan {
    plan_index: number
    equity_weight: number
    efficiency_score: number
    equity_score: number
    gini: number
    allocation_count: number
    zone_allocations: Record<string, number>
    adjustments_applied: string[]
    allocations: Array<{
        resource_id: string
        type: string
        quantity: number
        location: string
        distance_km: number
        zone_id?: string
        rural_boost_applied?: boolean
        vulnerability_bump?: boolean
        underservice_bonus_applied?: boolean
    }>
}

interface FrontierResponse {
    disaster_id: string | null
    total_resources: number
    total_needs: number
    total_zones: number
    plans: FairnessPlan[]
}

// ── Component ────────────────────────────────────────────────────────────────

export function FairnessSlider({ disasterId }: { disasterId?: string }) {
    const queryClient = useQueryClient()
    const [sliderValue, setSliderValue] = useState(50) // 0–100
    const [expandedPlan, setExpandedPlan] = useState<number | null>(null)
    const [confirmApply, setConfirmApply] = useState(false)

    // Fetch Pareto frontier
    const { data: frontier, isLoading, error, refetch } = useQuery<FrontierResponse>({
        queryKey: ['fairness-frontier', disasterId],
        queryFn: () => api.getFairnessFrontier({ disaster_id: disasterId }),
        refetchInterval: 60_000,
        staleTime: 30_000,
    })

    // Apply mutation
    const applyMutation = useMutation({
        mutationFn: (planIndex: number) =>
            api.applyFairnessPlan({ plan_index: planIndex, disaster_id: disasterId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fairness-frontier'] })
            queryClient.invalidateQueries({ queryKey: ['admin-resources'] })
            setConfirmApply(false)
        },
    })

    // Map slider value (0–100) to plan index (0–9)
    const selectedPlanIndex = useMemo(() => {
        if (!frontier?.plans?.length) return 0
        return Math.min(
            Math.round((sliderValue / 100) * (frontier.plans.length - 1)),
            frontier.plans.length - 1
        )
    }, [sliderValue, frontier])

    const selectedPlan = frontier?.plans?.[selectedPlanIndex]

    // Pareto chart data
    const chartData = useMemo(() => {
        if (!frontier?.plans) return []
        return frontier.plans.map((p, i) => ({
            name: `Plan ${i}`,
            efficiency: +(p.efficiency_score * 100).toFixed(1),
            equity: +(p.equity_score * 100).toFixed(1),
            gini: +(p.gini * 100).toFixed(1),
            index: i,
            selected: i === selectedPlanIndex,
        }))
    }, [frontier, selectedPlanIndex])

    // Zone allocation bar chart
    const zoneChartData = useMemo(() => {
        if (!selectedPlan?.zone_allocations) return []
        return Object.entries(selectedPlan.zone_allocations)
            .map(([zone, qty]) => ({ zone: zone.slice(0, 8) + '…', quantity: qty, fullZone: zone }))
            .sort((a, b) => b.quantity - a.quantity)
            .slice(0, 15)
    }, [selectedPlan])

    const handleApply = useCallback(() => {
        if (confirmApply) {
            applyMutation.mutate(selectedPlanIndex)
        } else {
            setConfirmApply(true)
        }
    }, [confirmApply, selectedPlanIndex, applyMutation])

    // ── Render ───────────────────────────────────────────────────────────

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
                <span className="ml-3 text-sm text-slate-500">Computing fairness frontier…</span>
            </div>
        )
    }

    if (error) {
        return (
            <div className="p-6 bg-red-50 dark:bg-red-950/20 rounded-2xl border border-red-200 dark:border-red-900/30">
                <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                    <AlertTriangle className="w-5 h-5" />
                    <span className="font-medium">Failed to load fairness data</span>
                </div>
                <p className="mt-2 text-sm text-red-500">{(error as Error).message}</p>
                <button onClick={() => refetch()} className="mt-3 px-4 py-1.5 text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors">
                    Retry
                </button>
            </div>
        )
    }

    if (!frontier?.plans?.length) {
        return (
            <div className="p-6 bg-amber-50 dark:bg-amber-950/20 rounded-2xl border border-amber-200 dark:border-amber-900/30 text-center">
                <Info className="w-8 h-8 mx-auto text-amber-500 mb-2" />
                <p className="text-sm text-amber-700 dark:text-amber-400">
                    No allocation data available. Ensure resources and requests exist.
                </p>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard icon={<Scale className="w-4 h-4" />} label="Resources" value={frontier.total_resources} />
                <StatCard icon={<AlertTriangle className="w-4 h-4" />} label="Needs" value={frontier.total_needs} />
                <StatCard icon={<TrendingUp className="w-4 h-4" />} label="Zones" value={frontier.total_zones} />
                <StatCard icon={<Shield className="w-4 h-4" />} label="Plans" value={frontier.plans.length} />
            </div>

            {/* Slider */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5 p-6">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Efficiency ↔ Equity Trade-off</h3>
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400">
                        Plan {selectedPlanIndex} / {frontier.plans.length - 1}
                    </span>
                </div>

                <div className="relative mb-2">
                    <input
                        type="range"
                        min={0}
                        max={100}
                        value={sliderValue}
                        onChange={(e) => {
                            setSliderValue(Number(e.target.value))
                            setConfirmApply(false)
                        }}
                        className="w-full h-2 bg-gradient-to-r from-blue-500 via-purple-500 to-emerald-500 rounded-lg appearance-none cursor-pointer
                            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full
                            [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-slate-400 [&::-webkit-slider-thumb]:shadow-lg
                            [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing"
                    />
                </div>
                <div className="flex justify-between text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium">
                    <span className="flex items-center gap-1"><Zap className="w-3 h-3" /> Pure Efficiency</span>
                    <span className="flex items-center gap-1">Pure Equity <Heart className="w-3 h-3" /></span>
                </div>

                {/* Selected plan scores */}
                {selectedPlan && (
                    <div className="mt-5 grid grid-cols-3 gap-3">
                        <ScoreCard
                            label="Efficiency"
                            value={selectedPlan.efficiency_score}
                            color="text-blue-600 dark:text-blue-400"
                            bg="bg-blue-50 dark:bg-blue-950/20"
                        />
                        <ScoreCard
                            label="Equity"
                            value={selectedPlan.equity_score}
                            color="text-emerald-600 dark:text-emerald-400"
                            bg="bg-emerald-50 dark:bg-emerald-950/20"
                        />
                        <ScoreCard
                            label="Gini"
                            value={selectedPlan.gini}
                            color="text-purple-600 dark:text-purple-400"
                            bg="bg-purple-50 dark:bg-purple-950/20"
                            invert
                        />
                    </div>
                )}
            </div>

            {/* Pareto Frontier Chart */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5 p-6">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Pareto Frontier</h3>
                <ResponsiveContainer width="100%" height={280}>
                    <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-700" />
                        <XAxis dataKey="efficiency" name="Efficiency %" unit="%" tick={{ fontSize: 11 }} label={{ value: 'Efficiency %', position: 'bottom', offset: 0, style: { fontSize: 11 } }} />
                        <YAxis dataKey="equity" name="Equity %" unit="%" tick={{ fontSize: 11 }} label={{ value: 'Equity %', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }} />
                        <RTooltip
                            content={({ payload }: any) => {
                                if (!payload?.[0]) return null
                                const d = payload[0].payload
                                return (
                                    <div className="bg-white dark:bg-slate-800 p-3 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 text-xs">
                                        <p className="font-semibold mb-1">{d.name} {d.selected ? '(Selected)' : ''}</p>
                                        <p>Efficiency: {d.efficiency}%</p>
                                        <p>Equity: {d.equity}%</p>
                                        <p>Gini: {d.gini}%</p>
                                    </div>
                                )
                            }}
                        />
                        <Scatter data={chartData} fill="#6366f1">
                            {chartData.map((entry, i) => (
                                <Cell
                                    key={i}
                                    fill={entry.selected ? '#10b981' : '#6366f1'}
                                    r={entry.selected ? 8 : 5}
                                    stroke={entry.selected ? '#059669' : 'none'}
                                    strokeWidth={entry.selected ? 2 : 0}
                                />
                            ))}
                        </Scatter>
                    </ScatterChart>
                </ResponsiveContainer>
            </div>

            {/* Zone Allocation Distribution */}
            {zoneChartData.length > 0 && (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5 p-6">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Resource Distribution by Zone</h3>
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={zoneChartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-slate-200 dark:text-slate-700" />
                            <XAxis dataKey="zone" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 11 }} />
                            <RTooltip
                                content={({ payload }: any) => {
                                    if (!payload?.[0]) return null
                                    const d = payload[0].payload
                                    return (
                                        <div className="bg-white dark:bg-slate-800 p-2 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 text-xs">
                                            <p className="font-semibold">{d.fullZone}</p>
                                            <p>Quantity: {d.quantity}</p>
                                        </div>
                                    )
                                }}
                            />
                            <Bar dataKey="quantity" fill="#6366f1" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* Adjustments Applied */}
            {selectedPlan && selectedPlan.adjustments_applied.length > 0 && (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5 p-6">
                    <button
                        className="flex w-full items-center justify-between"
                        onClick={() => setExpandedPlan(expandedPlan === selectedPlanIndex ? null : selectedPlanIndex)}
                    >
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                            Fairness Adjustments ({selectedPlan.adjustments_applied.length})
                        </h3>
                        {expandedPlan === selectedPlanIndex
                            ? <ChevronUp className="w-4 h-4 text-slate-400" />
                            : <ChevronDown className="w-4 h-4 text-slate-400" />
                        }
                    </button>
                    {expandedPlan === selectedPlanIndex && (
                        <ul className="mt-3 space-y-1.5">
                            {selectedPlan.adjustments_applied.map((adj, i) => (
                                <li key={i} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-400">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                                    <span>{adj}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {/* Apply Button */}
            <div className="flex items-center justify-end gap-3">
                {confirmApply && (
                    <button
                        onClick={() => setConfirmApply(false)}
                        className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
                    >
                        Cancel
                    </button>
                )}
                <button
                    onClick={handleApply}
                    disabled={applyMutation.isPending}
                    className={cn(
                        'px-6 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm',
                        confirmApply
                            ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-500/20'
                            : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-500/20',
                        applyMutation.isPending && 'opacity-60 cursor-not-allowed',
                    )}
                >
                    {applyMutation.isPending ? (
                        <span className="flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin" /> Applying…
                        </span>
                    ) : confirmApply ? (
                        `Confirm: Apply Plan ${selectedPlanIndex}`
                    ) : (
                        `Apply Plan ${selectedPlanIndex}`
                    )}
                </button>
            </div>

            {/* Apply Result */}
            {applyMutation.isSuccess && (
                <div className="p-4 bg-emerald-50 dark:bg-emerald-950/20 rounded-xl border border-emerald-200 dark:border-emerald-900/30">
                    <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="w-5 h-5" />
                        <span className="font-medium text-sm">Allocation applied successfully</span>
                    </div>
                    <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-500">
                        {(applyMutation.data as any)?.resources_allocated ?? 0} resources allocated.
                        Efficiency: {((applyMutation.data as any)?.efficiency_score * 100).toFixed(1)}%,
                        Equity: {((applyMutation.data as any)?.equity_score * 100).toFixed(1)}%
                    </p>
                </div>
            )}

            {applyMutation.isError && (
                <div className="p-4 bg-red-50 dark:bg-red-950/20 rounded-xl border border-red-200 dark:border-red-900/30">
                    <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                        <AlertTriangle className="w-5 h-5" />
                        <span className="font-medium text-sm">Failed to apply allocation</span>
                    </div>
                    <p className="mt-1 text-xs text-red-500">{(applyMutation.error as Error).message}</p>
                </div>
            )}
        </div>
    )
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
    return (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-white/5 p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-100 dark:bg-white/5 text-slate-500 dark:text-slate-400">
                {icon}
            </div>
            <div>
                <p className="text-lg font-bold text-slate-900 dark:text-white">{value}</p>
                <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider">{label}</p>
            </div>
        </div>
    )
}

function ScoreCard({
    label, value, color, bg, invert = false,
}: {
    label: string; value: number; color: string; bg: string; invert?: boolean
}) {
    const pct = (value * 100).toFixed(1)
    const quality = invert
        ? value < 0.3 ? 'Good' : value < 0.5 ? 'Fair' : 'Poor'
        : value > 0.7 ? 'Good' : value > 0.4 ? 'Fair' : 'Poor'

    return (
        <div className={cn('rounded-xl p-3', bg)}>
            <p className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">{label}</p>
            <p className={cn('text-xl font-bold', color)}>{pct}%</p>
            <p className="text-[10px] text-slate-400">{quality}</p>
        </div>
    )
}
