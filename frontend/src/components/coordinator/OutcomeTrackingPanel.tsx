'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import {
  Target, TrendingUp, CheckCircle2, AlertTriangle,
  XCircle, RefreshCw, Loader2, BarChart3, ArrowRight,
  ServerCrash, Info, ThumbsUp, ThumbsDown, Minus,
  RotateCcw, Zap, ClipboardList
} from 'lucide-react'

// ─── Plain-English helpers ────────────────────────────────────────────────────

/**
 * Converts a raw accuracy (0-1) into a traffic-light colour + label.
 */
function accuracyHealth(acc: number | null | undefined): {
  color: string; label: string; textColor: string; bg: string
} {
  if (acc == null) return { color: 'bg-slate-300', label: 'No data', textColor: 'text-slate-500', bg: 'bg-slate-50 dark:bg-white/5' }
  if (acc >= 0.85)  return { color: 'bg-green-500',  label: 'Excellent',   textColor: 'text-green-600 dark:text-green-400',  bg: 'bg-green-50 dark:bg-green-500/5' }
  if (acc >= 0.70)  return { color: 'bg-amber-500',  label: 'Good',        textColor: 'text-amber-600 dark:text-amber-400',  bg: 'bg-amber-50 dark:bg-amber-500/5' }
  if (acc >= 0.50)  return { color: 'bg-orange-500', label: 'Needs work',  textColor: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-50 dark:bg-orange-500/5' }
  return              { color: 'bg-red-500',    label: 'Poor',        textColor: 'text-red-600 dark:text-red-400',    bg: 'bg-red-50 dark:bg-red-500/5' }
}

/**
 * Converts MAPE to a plain English interpretation.
 */
function mapeToEnglish(mape: number | null | undefined): string {
  if (mape == null) return 'No data available yet.'
  if (mape <= 5)  return `The model's estimates are very close to reality — off by only ${mape.toFixed(1)}% on average.`
  if (mape <= 15) return `Estimates are reasonably accurate — off by ${mape.toFixed(1)}% on average.`
  if (mape <= 30) return `Estimates are somewhat off — ${mape.toFixed(1)}% average error. Model may need retraining.`
  return `Estimates are frequently wrong — ${mape.toFixed(1)}% average error. Retraining recommended soon.`
}

/**
 * Friendly model-type labels for the admin.
 */
const MODEL_LABELS: Record<string, { title: string; desc: string; icon: React.ReactNode }> = {
  severity: {
    title: 'Disaster Severity Prediction',
    desc:  'How well the AI predicts whether a disaster is Low / Medium / High / Critical',
    icon:  <AlertTriangle className="w-4 h-4 text-red-500" />,
  },
  spread: {
    title: 'Spread Area Estimation',
    desc:  'How accurately the AI estimates how far a disaster will spread (in km²)',
    icon:  <TrendingUp className="w-4 h-4 text-blue-500" />,
  },
  impact: {
    title: 'Human Impact Estimation',
    desc:  'How close the AI\'s casualty & damage estimates are to actual reported figures',
    icon:  <Target className="w-4 h-4 text-purple-500" />,
  },
}

/**
 * Plain-English explanation of what "MAE" actually means per model type.
 */
function maeContext(type: string, mae: number | null | undefined): string {
  if (mae == null) return ''
  const n = Number(mae)
  if (type === 'severity') return `(the model's confidence score is off by ${n.toFixed(1)} points on average)`
  if (type === 'spread')   return `(area estimates are off by ~${n.toFixed(0)} km² on average)`
  if (type === 'impact')   return `(casualty estimates differ by ~${n.toFixed(0)} from actual reports)`
  return ''
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AccuracyBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100))
  const color =
    pct >= 85 ? 'bg-green-500'
      : pct >= 70 ? 'bg-amber-500'
        : pct >= 50 ? 'bg-orange-500'
          : 'bg-red-500'
  return (
    <div className="w-full h-2 bg-slate-100 dark:bg-white/10 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function HealthBadge({ acc }: { acc: number | null | undefined }) {
  const h = accuracyHealth(acc)
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold ${h.bg} ${h.textColor}`}>
      {h.label}
    </span>
  )
}

function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-6 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
          <ServerCrash className="w-5 h-5 text-red-500" />
        </div>
        <div>
          <p className="text-sm font-semibold text-red-700 dark:text-red-400">Service Unavailable</p>
          <p className="text-xs text-red-500/80 dark:text-red-400/70 mt-1">
            {message || 'Could not load outcome data. Ensure the ML backend is running.'}
          </p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 text-xs font-medium hover:bg-red-200 dark:hover:bg-red-500/20 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function OutcomeTrackingPanel({
  selectedDisasterId,
}: {
  selectedDisasterId?: string | null
}) {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'accuracy' | 'outcomes' | 'evaluations'>('accuracy')

  const {
    data: accuracyData,
    isLoading: accuracyLoading,
    error: accuracyError,
    refetch: refetchAccuracy,
  } = useQuery({
    queryKey: ['accuracy-summary', selectedDisasterId],
    queryFn: () => api.getAccuracySummary(),
    refetchInterval: 120_000,
    retry: 1,
  })

  const {
    data: outcomesData,
    isLoading: outcomesLoading,
    error: outcomesError,
  } = useQuery({
    queryKey: ['outcomes', selectedDisasterId],
    queryFn: () =>
      selectedDisasterId
        ? api.getDisasterOutcomes(selectedDisasterId, { limit: 50 })
        : api.getOutcomes({ limit: 50 }),
    enabled: activeTab === 'outcomes',
    refetchInterval: 60_000,
    retry: 1,
  })

  const {
    data: evaluationsData,
    isLoading: evaluationsLoading,
    error: evaluationsError,
  } = useQuery({
    queryKey: ['evaluation-reports', selectedDisasterId],
    queryFn: () => api.getEvaluationReports({ limit: 10 }),
    enabled: activeTab === 'evaluations',
    retry: 1,
  })

  const autoCaptureMutation = useMutation({
    mutationFn: () => api.autoCaptureOutcomes(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outcomes'] })
      queryClient.invalidateQueries({ queryKey: ['accuracy-summary'] })
    },
  })

  const evaluateMutation = useMutation({
    mutationFn: () => api.generateEvaluationReport({ period_days: 30 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation-reports'] })
      queryClient.invalidateQueries({ queryKey: ['accuracy-summary'] })
    },
  })

  const tabs = [
    { id: 'accuracy'    as const, label: 'Model Health',  icon: Target },
    { id: 'outcomes'    as const, label: 'Past Outcomes', icon: ClipboardList },
    { id: 'evaluations' as const, label: 'Evaluations',   icon: BarChart3 },
  ]

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Target className="w-5 h-5 text-emerald-500" />
            AI Prediction Accuracy
            {selectedDisasterId && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-medium">
                Filtered
              </span>
            )}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            How accurate are our AI predictions? Compares what was predicted vs. what actually happened.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => autoCaptureMutation.mutate()}
            disabled={autoCaptureMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 text-xs font-medium hover:bg-emerald-200 dark:hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
          >
            {autoCaptureMutation.isPending
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <RefreshCw className="w-3.5 h-3.5" />}
            Sync Outcomes
          </button>
          <button
            onClick={() => evaluateMutation.mutate()}
            disabled={evaluateMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 text-xs font-medium hover:bg-blue-200 dark:hover:bg-blue-500/20 disabled:opacity-50 transition-colors"
          >
            {evaluateMutation.isPending
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Zap className="w-3.5 h-3.5" />}
            Recalculate
          </button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/5">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-white/10 text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* ══════════════ TAB: Model Health (Accuracy) ══════════════ */}
      {activeTab === 'accuracy' && (
        <div className="space-y-4">
          {accuracyLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : accuracyError ? (
            <ErrorState
              message={(accuracyError as Error)?.message}
              onRetry={() => refetchAccuracy()}
            />
          ) : accuracyData ? (
            <div className="space-y-3">
              {(['severity', 'spread', 'impact'] as const).map(ptype => {
                const d = accuracyData[ptype]
                const hasData = d && d.status !== 'no_data'
                const meta = MODEL_LABELS[ptype]
                const health = accuracyHealth(hasData ? d.accuracy : null)

                return (
                  <div
                    key={ptype}
                    className={`rounded-xl border p-4 space-y-3 ${
                      d?.retrain_triggered
                        ? 'border-amber-200 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-500/5'
                        : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]'
                    }`}
                  >
                    {/* Title row */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2">
                        <span className="mt-0.5">{meta.icon}</span>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                              {meta.title}
                            </h3>
                            <HealthBadge acc={hasData ? d.accuracy : null} />
                          </div>
                          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                            {meta.desc}
                          </p>
                        </div>
                      </div>

                      {d?.retrain_triggered && (
                        <span className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 font-semibold shrink-0">
                          <RotateCcw className="w-3 h-3" />
                          Auto-retraining
                        </span>
                      )}
                    </div>

                    {hasData ? (
                      <div className="space-y-3">
                        {/* Accuracy bar */}
                        {d.accuracy != null && (
                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-slate-500 dark:text-slate-400">Correct predictions</span>
                              <span className={`text-sm font-bold ${health.textColor}`}>
                                {(d.accuracy * 100).toFixed(1)}%
                              </span>
                            </div>
                            <AccuracyBar value={d.accuracy} />
                            <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                              {d.accuracy >= 0.85
                                ? `✅ The model is highly reliable — ${(d.accuracy * 100).toFixed(0)} out of every 100 predictions are correct.`
                                : d.accuracy >= 0.70
                                ? `⚠️ Reasonably accurate — ${(d.accuracy * 100).toFixed(0)} out of 100 correct. There is room for improvement.`
                                : `❌ Too many wrong predictions (${((1 - d.accuracy) * 100).toFixed(0)} out of 100). Retraining is recommended.`}
                            </p>
                          </div>
                        )}

                        {/* MAPE in plain English */}
                        {d.mape != null && (
                          <div className="rounded-lg bg-slate-50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5 p-3">
                            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 flex items-center gap-1">
                              <Info className="w-3 h-3" /> Average error in estimates
                            </p>
                            <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
                              {mapeToEnglish(d.mape)}
                            </p>
                            {d.mae != null && (
                              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                                {maeContext(ptype, d.mae)}
                              </p>
                            )}
                          </div>
                        )}

                        {/* Stats row */}
                        <div className="grid grid-cols-3 gap-2 text-center">
                          {[
                            {
                              label: 'Avg. Error (MAE)',
                              val: d.mae != null ? d.mae.toFixed(2) : '—',
                              tip: 'Mean Absolute Error — lower is better. Shown as "—" for classification models like Severity (no numeric error).',
                            },
                            {
                              label: 'Error Spread (RMSE)',
                              val: d.rmse != null ? d.rmse.toFixed(2) : '—',
                              tip: 'Root Mean Squared Error — lower is better. Shown as "—" for classification models.',
                            },
                            {
                              label: '% Error (MAPE)',
                              val: d.mape != null ? `${d.mape.toFixed(1)}%` : '—',
                              tip: 'Mean Absolute Percentage Error — lower is better. Shown as "—" for classification models.',
                            },
                          ].map(s => (
                            <div
                              key={s.label}
                              className="rounded-lg bg-slate-50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5 p-2"
                              title={s.tip}
                            >
                              <p className="text-xs text-slate-400 dark:text-slate-500 leading-tight">{s.label}</p>
                              <p className="text-sm font-bold text-slate-700 dark:text-slate-300 mt-0.5">{s.val}</p>
                              {s.val === '—' && (
                                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                                  (Classification model)
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                        
                        {/* Business Impact KPIs */}
                        {d.business_impact && (d.business_impact.estimated_resources_saved > 0 || d.business_impact.over_allocation_prevented_pct > 0) && (
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded-lg bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-100 dark:border-emerald-500/10 p-2.5 flex items-center gap-2">
                              <div className="p-1.5 rounded-md bg-emerald-100 dark:bg-emerald-500/10">
                                <Zap className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                              </div>
                              <div>
                                <p className="text-[10px] text-emerald-600/70 dark:text-emerald-400/60 font-semibold uppercase tracking-wider">Efficiency Gain</p>
                                <p className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
                                  {d.business_impact.over_allocation_prevented_pct}% <span className="text-[10px] font-normal opacity-70">less waste</span>
                                </p>
                              </div>
                            </div>
                            <div className="rounded-lg bg-blue-50/50 dark:bg-blue-500/5 border border-blue-100 dark:border-blue-500/10 p-2.5 flex items-center gap-2">
                              <div className="p-1.5 rounded-md bg-blue-100 dark:bg-blue-500/10">
                                <TrendingUp className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                              </div>
                              <div>
                                <p className="text-[10px] text-blue-600/70 dark:text-blue-400/60 font-semibold uppercase tracking-wider">Estimated ROI</p>
                                <p className="text-sm font-bold text-blue-700 dark:text-blue-300">
                                  {d.business_impact.estimated_resources_saved.toLocaleString()} <span className="text-[10px] font-normal opacity-70">units saved</span>
                                </p>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Classification vs. Regression explanation */}
                        {(['severity', 'spread', 'impact'] as const).includes(ptype) && (
                          (() => {
                            const isClassification = ptype === 'severity'
                            return (
                              <div className={`rounded-lg border p-3 ${
                                isClassification
                                  ? 'bg-blue-50 dark:bg-blue-500/5 border-blue-100 dark:border-blue-500/10'
                                  : 'bg-purple-50 dark:bg-purple-500/5 border-purple-100 dark:border-purple-500/10'
                              }`}>
                                <p className={`text-xs font-semibold mb-1 flex items-center gap-1 ${
                                  isClassification
                                    ? 'text-blue-700 dark:text-blue-400'
                                    : 'text-purple-700 dark:text-purple-400'
                                }`}>
                                  <Info className="w-3 h-3" />
                                  {isClassification ? 'Classification Model' : 'Regression Model'}
                                </p>
                                <p className={`text-xs leading-relaxed ${
                                  isClassification
                                    ? 'text-blue-900 dark:text-blue-200'
                                    : 'text-purple-900 dark:text-purple-200'
                                }`}>
                                  {isClassification
                                    ? 'This model predicts categories (Low / Medium / High / Critical) instead of numbers. That\'s why MAE/RMSE show as "—" — those metrics only work for numeric predictions. Accuracy % is the right metric here.'
                                    : 'This model predicts numeric values (area in km², casualties, etc.). MAE/RMSE/MAPE measure how far the predictions are from actual values.'}
                                </p>
                              </div>
                            )
                          })()
                        )}

                        {/* Retrain explanation */}
                        {d.retrain_triggered && (
                          <div className="rounded-lg bg-amber-50 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10 p-3 flex gap-2">
                            <RotateCcw className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                            <div>
                              <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                                Why is it retraining?
                              </p>
                              <p className="text-xs text-amber-600 dark:text-amber-300 mt-0.5 leading-relaxed">
                                The model's error exceeded acceptable limits. The system has automatically
                                started learning from the latest real-world data to improve future predictions.
                                No action needed — this happens automatically.
                              </p>
                            </div>
                          </div>
                        )}

                        <p className="text-[11px] text-slate-400 dark:text-slate-500 text-right">
                          Based on {d.total_predictions || 0} predictions
                        </p>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 text-center py-4">
                        No predictions recorded yet for this model.
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/[0.01] p-6 text-center space-y-2">
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No evaluation data yet</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Click <span className="font-semibold text-emerald-500">Sync Outcomes</span> to pull real outcomes from the database,
                then <span className="font-semibold text-blue-500">Recalculate</span> to compute accuracy scores.
              </p>
            </div>
          )}

          {/* ── How the feedback loop works ── */}
          <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/[0.01] p-4">
            <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
              How the self-improving loop works
            </h3>
            <div className="flex items-start gap-2 flex-wrap">
              {[
                { icon: '📊', label: 'Real victim data', sub: 'From your database' },
                { icon: '🤖', label: 'AI makes prediction', sub: 'Severity, spread, impact' },
                { icon: '📦', label: 'Resources allocated', sub: 'Based on prediction' },
                { icon: '📋', label: 'Actual outcome recorded', sub: 'After event resolves' },
                { icon: '📈', label: 'Model evaluated', sub: 'Predicted vs. actual' },
                { icon: '🔄', label: 'Model retrains', sub: 'Learns from mistakes' },
              ].map((step, i, arr) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex flex-col items-center px-3 py-2 rounded-lg bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 min-w-[90px]">
                    <span className="text-base">{step.icon}</span>
                    <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 text-center leading-tight mt-0.5">
                      {step.label}
                    </span>
                    <span className="text-[10px] text-slate-400 dark:text-slate-500 text-center leading-tight">
                      {step.sub}
                    </span>
                  </div>
                  {i < arr.length - 1 && (
                    <ArrowRight className="w-3 h-3 text-slate-300 dark:text-white/20 shrink-0" />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════ TAB: Past Outcomes ══════════════ */}
      {activeTab === 'outcomes' && (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
          {outcomesLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : outcomesError ? (
            <div className="p-6">
              <ErrorState message={(outcomesError as Error)?.message} />
            </div>
          ) : (outcomesData?.outcomes || []).length > 0 ? (
            <div>
              <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Showing the most recent {(outcomesData?.outcomes || []).length} prediction comparisons from real disaster data in your database.
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-white/5">
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        Model
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        Predicted
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        What actually happened
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        How close?
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        Correct?
                      </th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 min-w-[200px]">
                        AI Response Post-Mortem
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                    {(outcomesData?.outcomes || []).map((o: any) => {
                      const errPct = o.casualty_error_pct ?? o.area_error_pct ?? null
                      const isClose = errPct != null && Math.abs(errPct) <= 15
                      const label = MODEL_LABELS[o.prediction_type] || { title: o.prediction_type, icon: null }
                      return (
                        <tr key={o.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02]">
                          <td className="px-4 py-2.5 text-xs text-slate-700 dark:text-slate-300 font-medium">
                            {(label as any).title || o.prediction_type}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-slate-600 dark:text-slate-400">
                            {o.predicted_severity || o.predicted_casualties || o.predicted_area_km2?.toFixed(1) || '—'}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-slate-700 dark:text-slate-300 font-medium">
                            {o.actual_severity || o.actual_casualties || o.actual_area_km2?.toFixed(1) || '—'}
                          </td>
                          <td className="px-4 py-2.5 text-xs">
                            {errPct != null ? (
                              <span className={`font-semibold ${Math.abs(errPct) <= 10 ? 'text-green-600 dark:text-green-400' : Math.abs(errPct) <= 25 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
                                {errPct > 0 ? 'Over by ' : 'Under by '}
                                {Math.abs(errPct).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                          <td className="px-4 py-2.5">
                            {o.severity_match === true ? (
                              <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                                <ThumbsUp className="w-3.5 h-3.5" />
                                <span className="text-xs">Yes</span>
                              </div>
                            ) : o.severity_match === false ? (
                              <div className="flex items-center gap-1 text-red-500 dark:text-red-400">
                                <ThumbsDown className="w-3.5 h-3.5" />
                                <span className="text-xs">No</span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1 text-slate-400">
                                <Minus className="w-3.5 h-3.5" />
                                <span className="text-xs">N/A</span>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-2.5">
                            {o.notes ? (
                              <p className="text-[11px] text-slate-600 dark:text-slate-400 italic leading-relaxed border-l-2 border-slate-200 dark:border-white/10 pl-2">
                                "{o.notes}"
                              </p>
                            ) : (
                              <span className="text-[10px] text-slate-400 dark:text-slate-500">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center">
              <ClipboardList className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
                No outcome comparisons yet
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Click <span className="font-semibold text-emerald-500">Sync Outcomes</span> to pull real outcomes from all disasters in your database.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ══════════════ TAB: Evaluations ══════════════ */}
      {activeTab === 'evaluations' && (
        <div className="space-y-3">
          {evaluationsLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : evaluationsError ? (
            <ErrorState message={(evaluationsError as Error)?.message} />
          ) : (evaluationsData?.reports || []).length > 0 ? (
            (evaluationsData?.reports || []).map((report: any) => {
              const health = accuracyHealth(report.accuracy)
              const meta = MODEL_LABELS[report.model_type]
              return (
                <div
                  key={report.id}
                  className={`rounded-xl border p-4 ${
                    report.retrain_triggered
                      ? 'border-amber-200 dark:border-amber-500/20 bg-amber-50/30 dark:bg-amber-500/5'
                      : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]'
                  }`}
                >
                  {/* Header */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      {meta?.icon}
                      <div>
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                          {meta?.title || report.model_type} Evaluation
                        </h3>
                        <p className="text-[11px] text-slate-400 dark:text-slate-500">
                          Period ending {report.report_date}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <HealthBadge acc={report.accuracy} />
                      {report.retrain_triggered && (
                        <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 font-semibold">
                          <RotateCcw className="w-3 h-3" />
                          Retraining triggered
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Accuracy bar */}
                  {report.accuracy != null && (
                    <div className="mb-3">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs text-slate-500">Overall accuracy</span>
                        <span className={`text-sm font-bold ${health.textColor}`}>
                          {(report.accuracy * 100).toFixed(1)}%
                        </span>
                      </div>
                      <AccuracyBar value={report.accuracy} />
                    </div>
                  )}

                  {/* Stats grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                    {[
                      { label: 'Avg. Error', val: report.mae != null ? report.mae.toFixed(2) : '—', tip: 'Mean Absolute Error' },
                      { label: 'Error Spread', val: report.rmse != null ? report.rmse.toFixed(2) : '—', tip: 'Root Mean Squared Error' },
                      { label: '% Error', val: report.mape != null ? `${report.mape.toFixed(1)}%` : '—', tip: 'Mean Absolute % Error' },
                      { label: 'Predictions', val: String(report.total_predictions || 0), tip: 'Total predictions evaluated' },
                    ].map(s => (
                      <div
                        key={s.label}
                        title={s.tip}
                        className="rounded-lg bg-slate-50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5 p-2"
                      >
                        <p className="text-[10px] text-slate-400 dark:text-slate-500">{s.label}</p>
                        <p className="text-sm font-bold text-slate-700 dark:text-slate-300 mt-0.5">{s.val}</p>
                      </div>
                    ))}
                  </div>

                  {/* Plain summary */}
                  {report.mape != null && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-3 leading-relaxed">
                      {mapeToEnglish(report.mape)}
                    </p>
                  )}
                </div>
              )
            })
          ) : (
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-8 text-center">
              <BarChart3 className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
                No evaluation reports yet
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                First click <span className="font-semibold text-emerald-500">Sync Outcomes</span>,
                then <span className="font-semibold text-blue-500">Recalculate</span> to generate a report.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}