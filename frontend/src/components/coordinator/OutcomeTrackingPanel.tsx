'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import {
  Target, TrendingUp, TrendingDown, CheckCircle2,
  XCircle, RefreshCw, Loader2, BarChart3, ArrowRight
} from 'lucide-react'

export default function OutcomeTrackingPanel() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'outcomes' | 'evaluations' | 'accuracy'>('accuracy')

  const { data: accuracyData, isLoading: accuracyLoading } = useQuery({
    queryKey: ['accuracy-summary'],
    queryFn: () => api.getAccuracySummary(),
    refetchInterval: 120_000,
  })

  const { data: outcomesData, isLoading: outcomesLoading } = useQuery({
    queryKey: ['outcomes'],
    queryFn: () => api.getOutcomes({ limit: 20 }),
    enabled: activeTab === 'outcomes',
  })

  const { data: evaluationsData, isLoading: evaluationsLoading } = useQuery({
    queryKey: ['evaluation-reports'],
    queryFn: () => api.getEvaluationReports(undefined, 10),
    enabled: activeTab === 'evaluations',
  })

  const autoCaptureMutation = useMutation({
    mutationFn: () => api.autoCaptureOutcomes(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outcomes'] })
      queryClient.invalidateQueries({ queryKey: ['accuracy-summary'] })
    },
  })

  const evaluateMutation = useMutation({
    mutationFn: () => api.generateEvaluationReport(undefined, 7),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation-reports'] })
      queryClient.invalidateQueries({ queryKey: ['accuracy-summary'] })
    },
  })

  const tabs = [
    { id: 'accuracy' as const, label: 'Accuracy Summary', icon: Target },
    { id: 'outcomes' as const, label: 'Outcomes', icon: BarChart3 },
    { id: 'evaluations' as const, label: 'Evaluations', icon: TrendingUp },
  ]

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Target className="w-5 h-5 text-emerald-500" />
            Outcome Tracking & Feedback Loop
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Actual vs. predicted outcomes drive self-improving model accuracy
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => autoCaptureMutation.mutate()}
            disabled={autoCaptureMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 text-xs font-medium hover:bg-emerald-200 dark:hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
          >
            {autoCaptureMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Auto-Capture
          </button>
          <button
            onClick={() => evaluateMutation.mutate()}
            disabled={evaluateMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 text-xs font-medium hover:bg-blue-200 dark:hover:bg-blue-500/20 disabled:opacity-50 transition-colors"
          >
            {evaluateMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BarChart3 className="w-3.5 h-3.5" />}
            Run Evaluation
          </button>
        </div>
      </div>

      {/* Tabs */}
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

      {/* Accuracy Summary */}
      {activeTab === 'accuracy' && (
        <div className="space-y-3">
          {accuracyLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : accuracyData ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {(['severity', 'spread', 'impact'] as const).map(ptype => {
                const data = accuracyData[ptype]
                const hasData = data && data.status !== 'no_data'

                return (
                  <div
                    key={ptype}
                    className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white capitalize">
                        {ptype}
                      </h3>
                      {hasData && data.retrain_triggered && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
                          Retrain triggered
                        </span>
                      )}
                    </div>

                    {hasData ? (
                      <div className="space-y-2">
                        {data.accuracy !== null && data.accuracy !== undefined && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-500">Accuracy</span>
                            <span className={`text-sm font-bold ${
                              data.accuracy >= 0.8 ? 'text-green-600' :
                              data.accuracy >= 0.6 ? 'text-amber-600' : 'text-red-600'
                            }`}>
                              {(data.accuracy * 100).toFixed(1)}%
                            </span>
                          </div>
                        )}
                        {data.mae !== null && data.mae !== undefined && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-500">MAE</span>
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                              {data.mae.toFixed(2)}
                            </span>
                          </div>
                        )}
                        {data.rmse !== null && data.rmse !== undefined && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-500">RMSE</span>
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                              {data.rmse.toFixed(2)}
                            </span>
                          </div>
                        )}
                        {data.mape !== null && data.mape !== undefined && (
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-500">MAPE</span>
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                              {data.mape.toFixed(1)}%
                            </span>
                          </div>
                        )}
                        <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-white/5">
                          <span className="text-xs text-slate-400">Predictions</span>
                          <span className="text-xs text-slate-500">{data.total_predictions || 0}</span>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 text-center py-4">No evaluation data yet</p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-sm text-slate-400">
              No accuracy data available. Run an evaluation to generate metrics.
            </div>
          )}

          {/* Feedback loop diagram */}
          <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/[0.01] p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Self-Improving Feedback Loop
            </h3>
            <div className="flex items-center justify-center gap-2 flex-wrap text-xs">
              {[
                { label: 'Real Data', icon: '📊' },
                { label: 'ML Predictions', icon: '🤖' },
                { label: 'Resource Allocation', icon: '📦' },
                { label: 'Actual Outcomes', icon: '📋' },
                { label: 'Model Evaluation', icon: '📈' },
                { label: 'Auto-Retrain', icon: '🔄' },
              ].map((step, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10">
                    <span>{step.icon}</span>
                    <span className="text-slate-700 dark:text-slate-300">{step.label}</span>
                  </div>
                  {i < 5 && <ArrowRight className="w-3 h-3 text-slate-400" />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Outcomes list */}
      {activeTab === 'outcomes' && (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
          {outcomesLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : (outcomesData?.outcomes || []).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-white/5">
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-500">Type</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-500">Predicted</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-500">Actual</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-500">Error</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-500">Match</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                  {(outcomesData?.outcomes || []).map((o: any) => (
                    <tr key={o.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02]">
                      <td className="px-4 py-2 capitalize text-slate-700 dark:text-slate-300">{o.prediction_type}</td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-400">
                        {o.predicted_severity || o.predicted_casualties || o.predicted_area_km2?.toFixed(1) || '—'}
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-400">
                        {o.actual_severity || o.actual_casualties || o.actual_area_km2?.toFixed(1) || '—'}
                      </td>
                      <td className="px-4 py-2">
                        {o.casualty_error_pct != null ? (
                          <span className={o.casualty_error_pct > 0 ? 'text-red-500' : 'text-green-500'}>
                            {o.casualty_error_pct > 0 ? '+' : ''}{o.casualty_error_pct.toFixed(1)}%
                          </span>
                        ) : o.area_error_pct != null ? (
                          <span className={o.area_error_pct > 0 ? 'text-red-500' : 'text-green-500'}>
                            {o.area_error_pct > 0 ? '+' : ''}{o.area_error_pct.toFixed(1)}%
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-2">
                        {o.severity_match === true ? (
                          <CheckCircle2 className="w-4 h-4 text-green-500" />
                        ) : o.severity_match === false ? (
                          <XCircle className="w-4 h-4 text-red-500" />
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-sm text-slate-400">
              No outcomes recorded yet. Use "Auto-Capture" to find resolved disasters.
            </div>
          )}
        </div>
      )}

      {/* Evaluations */}
      {activeTab === 'evaluations' && (
        <div className="space-y-3">
          {evaluationsLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : (evaluationsData?.reports || []).length > 0 ? (
            (evaluationsData?.reports || []).map((report: any) => (
              <div
                key={report.id}
                className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white capitalize">
                    {report.model_type} Model — {report.report_date}
                  </h3>
                  {report.retrain_triggered && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 font-medium">
                      Auto-retrain triggered
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  {report.accuracy !== null && (
                    <div>
                      <span className="text-slate-400">Accuracy</span>
                      <p className="font-bold text-slate-700 dark:text-slate-300">{(report.accuracy * 100).toFixed(1)}%</p>
                    </div>
                  )}
                  {report.mae !== null && (
                    <div>
                      <span className="text-slate-400">MAE</span>
                      <p className="font-bold text-slate-700 dark:text-slate-300">{report.mae?.toFixed(2)}</p>
                    </div>
                  )}
                  {report.rmse !== null && (
                    <div>
                      <span className="text-slate-400">RMSE</span>
                      <p className="font-bold text-slate-700 dark:text-slate-300">{report.rmse?.toFixed(2)}</p>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-400">Predictions</span>
                    <p className="font-bold text-slate-700 dark:text-slate-300">{report.total_predictions}</p>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-8 text-center text-sm text-slate-400">
              No evaluation reports yet. Click "Run Evaluation" to generate one.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
