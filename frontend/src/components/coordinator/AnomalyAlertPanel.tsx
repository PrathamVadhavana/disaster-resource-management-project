'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import {
  AlertTriangle, Shield, ShieldAlert, ShieldCheck,
  CheckCircle2, XCircle, Eye, Loader2, Zap, ChevronDown,
  RefreshCw, ServerCrash
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  low: 'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-400',
}

const SEVERITY_ICON: Record<string, typeof AlertTriangle> = {
  critical: ShieldAlert,
  high: AlertTriangle,
  medium: Shield,
  low: ShieldCheck,
}

const TYPE_LABELS: Record<string, string> = {
  resource_consumption: '📦 Resource Consumption',
  request_volume: '📈 Request Volume',
  severity_escalation: '🔴 Severity Escalation',
  prediction_drift: '📊 Prediction Drift',
}

export default function AnomalyAlertPanel({ selectedDisasterId }: { selectedDisasterId?: string | null }) {
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [severityFilter, setSeverityFilter] = useState<string>('')

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['anomaly-alerts', statusFilter, selectedDisasterId],
    queryFn: async () => {
      if (selectedDisasterId) {
        try {
          return await api.getDisasterAnomalies(selectedDisasterId)
        } catch {
          // Fallback to general alerts when disaster-specific endpoint fails
          return api.getAnomalyAlerts({ status: statusFilter || undefined, limit: 50 })
        }
      }
      return api.getAnomalyAlerts({ status: statusFilter || undefined, limit: 30 })
    },
    refetchInterval: 30_000,
    retry: 1,
  })

  const detectMutation = useMutation({
    mutationFn: () => api.runAnomalyDetection(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const acknowledgeMutation = useMutation({
    mutationFn: (alertId: string) => api.acknowledgeAnomaly(alertId, 'current-user'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const resolveMutation = useMutation({
    mutationFn: ({ alertId, status }: { alertId: string; status: string }) =>
      api.resolveAnomaly(alertId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const allAlerts = data?.alerts || (Array.isArray(data) ? data : [])
  const alerts = allAlerts.filter((a: any) => {
    if (statusFilter && a.status !== statusFilter) return false
    if (severityFilter && a.severity !== severityFilter) return false
    return true
  })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            Anomaly Alerts
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            ML-detected anomalies in resource consumption, requests, and severity
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400 text-xs font-medium hover:bg-slate-200 dark:hover:bg-white/10 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => detectMutation.mutate()}
            disabled={detectMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 text-xs font-medium hover:bg-amber-200 dark:hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
          >
            {detectMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Run Detection
          </button>
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">Status:</span>
          {['active', 'acknowledged', 'resolved', ''].map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors ${
                statusFilter === s
                  ? 'bg-amber-500 text-white'
                  : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">Severity:</span>
          {['', 'critical', 'high', 'medium', 'low'].map(sev => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors ${
                severityFilter === sev
                  ? sev === 'critical' ? 'bg-red-500 text-white'
                    : sev === 'high' ? 'bg-orange-500 text-white'
                    : sev === 'medium' ? 'bg-amber-500 text-white'
                    : sev === 'low' ? 'bg-slate-500 text-white'
                    : 'bg-purple-500 text-white'
                  : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10'
              }`}
            >
              {sev || 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Alert count summary */}
      {allAlerts.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500 dark:text-slate-400">{alerts.length} of {allAlerts.length} shown</span>
          <span className="mx-1 text-slate-300 dark:text-white/10">|</span>
          {['critical', 'high', 'medium', 'low'].map(sev => {
            const count = allAlerts.filter((a: any) => a.severity === sev).length
            if (count === 0) return null
            return (
              <button
                key={sev}
                onClick={() => setSeverityFilter(severityFilter === sev ? '' : sev)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${SEVERITY_STYLES[sev]} ${severityFilter === sev ? 'ring-2 ring-offset-1 ring-amber-400' : 'hover:opacity-80'}`}
              >
                {count} {sev}
              </button>
            )
          })}
        </div>
      )}

      {/* Content */}
      <div className="space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-8 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                <ServerCrash className="w-6 h-6 text-red-500" />
              </div>
              <div>
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                  ML Anomaly Service Unavailable
                </p>
                <p className="text-xs text-red-500/80 dark:text-red-400/70 mt-1 max-w-xs mx-auto">
                  {(error as Error)?.message || 'Could not connect to the anomaly detection service. Ensure the backend is running.'}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => refetch()}
                  disabled={isFetching}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 text-xs font-medium hover:bg-red-200 dark:hover:bg-red-500/20 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
                  Retry Connection
                </button>
                <button
                  onClick={() => detectMutation.mutate()}
                  disabled={detectMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs font-medium hover:bg-amber-200 dark:hover:bg-amber-500/20 transition-colors disabled:opacity-50"
                >
                  {detectMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                  Run Detection
                </button>
              </div>
            </div>
          </div>
        ) : alerts.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-8 text-center">
            <ShieldCheck className="w-10 h-10 text-green-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              No {statusFilter || ''} anomaly alerts
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              {allAlerts.length > 0
                ? `${allAlerts.length} total alerts — adjust filters to see them`
                : 'Click "Run Detection" to scan for anomalies'}
            </p>
          </div>
        ) : (
          alerts.map((alert: any) => {
            const SevIcon = SEVERITY_ICON[alert.severity] || Shield
            const isExpanded = expandedId === alert.id

            return (
              <div
                key={alert.id}
                className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden"
              >
                <button
                  onClick={() => setExpandedId(isExpanded ? null : alert.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors"
                >
                  <SevIcon className={`w-5 h-5 shrink-0 ${
                    alert.severity === 'critical' ? 'text-red-500' :
                    alert.severity === 'high' ? 'text-orange-500' :
                    alert.severity === 'medium' ? 'text-amber-500' :
                    'text-slate-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-900 dark:text-white truncate">
                        {alert.title}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEVERITY_STYLES[alert.severity]}`}>
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {TYPE_LABELS[alert.anomaly_type] || alert.anomaly_type} ·{' '}
                      {alert.detected_at ? formatDistanceToNow(new Date(alert.detected_at), { addSuffix: true }) : 'unknown'}
                    </p>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                </button>

                {isExpanded && (
                  <div className="px-4 pb-4 space-y-3 border-t border-slate-100 dark:border-white/5 pt-3">
                    {alert.description && (
                      <p className="text-sm text-slate-600 dark:text-slate-300">{alert.description}</p>
                    )}
                    {alert.ai_explanation && (
                      <div className="rounded-lg bg-purple-50 dark:bg-purple-500/5 border border-purple-100 dark:border-purple-500/10 p-3">
                        <p className="text-xs font-medium text-purple-700 dark:text-purple-400 mb-1 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> AI Explanation
                        </p>
                        <p className="text-sm text-purple-900 dark:text-purple-200">{alert.ai_explanation}</p>
                      </div>
                    )}
                    <div className="flex gap-4 text-xs text-slate-500">
                      <span>Metric: <strong className="text-slate-700 dark:text-slate-300">{alert.metric_name}</strong></span>
                      <span>Value: <strong className="text-slate-700 dark:text-slate-300">{alert.metric_value?.toFixed(2)}</strong></span>
                      {alert.anomaly_score && (
                        <span>Score: <strong className="text-slate-700 dark:text-slate-300">{alert.anomaly_score?.toFixed(3)}</strong></span>
                      )}
                    </div>
                    {alert.status === 'active' && (
                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => acknowledgeMutation.mutate(alert.id)}
                          disabled={acknowledgeMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/20 transition-colors"
                        >
                          <CheckCircle2 className="w-3 h-3" /> Acknowledge
                        </button>
                        <button
                          onClick={() => resolveMutation.mutate({ alertId: alert.id, status: 'resolved' })}
                          disabled={resolveMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-500/20 transition-colors"
                        >
                          <ShieldCheck className="w-3 h-3" /> Resolve
                        </button>
                        <button
                          onClick={() => resolveMutation.mutate({ alertId: alert.id, status: 'false_positive' })}
                          disabled={resolveMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/15 transition-colors"
                        >
                          <XCircle className="w-3 h-3" /> False Positive
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}