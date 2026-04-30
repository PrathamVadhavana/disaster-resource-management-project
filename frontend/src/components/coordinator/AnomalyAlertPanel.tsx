'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import {
  AlertTriangle, Shield, ShieldAlert, ShieldCheck,
  CheckCircle2, XCircle, Eye, Loader2, Zap, ChevronDown,
  RefreshCw, ServerCrash, Users, Package, TrendingUp, Activity,
  Info, ChevronRight, Bell, Sparkles, Clock, Download, Link2
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

// ─── Plain-English helpers ────────────────────────────────────────────────────

function humanTitle(alert: any): string {
  const t = (alert.anomaly_type || '').toLowerCase()
  const raw = (alert.title || '').toLowerCase()
  if (t === 'request_volume' || raw.includes('request volume')) return 'Unusual spike in help requests'
  if (t === 'resource_consumption' || raw.includes('resource')) return 'Resources being used faster than expected'
  if (t === 'severity_escalation' || raw.includes('severity')) return 'Disaster severity is escalating'
  if (t === 'prediction_drift' || raw.includes('drift')) return 'AI predictions drifting from reality'
  if (t === 'geo_surge' || raw.includes('geo') || raw.includes('geographic')) return 'Surge of requests from one location'
  return alert.title || 'Unusual activity detected'
}

function humanImpact(alert: any): string {
  const t = (alert.anomaly_type || '').toLowerCase()
  const intensity =
    alert.severity === 'critical' ? 'extremely high'
      : alert.severity === 'high' ? 'much higher than normal'
        : alert.severity === 'medium' ? 'above normal'
          : 'slightly above normal'
  if (t === 'request_volume' || (alert.title || '').toLowerCase().includes('request volume')) {
    const val = alert.metric_value ? Math.round(alert.metric_value) : null
    return val
      ? `${val} requests detected — this is ${intensity} for this time period. Victims may need immediate attention.`
      : `Request count is ${intensity}. Victims may need immediate attention.`
  }
  if (t === 'resource_consumption') return `Resources (food, water, medicine, etc.) are being consumed ${intensity}. Stock may run out soon.`
  if (t === 'severity_escalation') return `The disaster appears to be getting worse. Severity is ${intensity}.`
  if (t === 'prediction_drift') return `The AI model's predictions are diverging from actual outcomes. Accuracy may have dropped.`
  if (t === 'geo_surge') return `A specific area is receiving ${intensity} requests. That zone may need extra resources.`
  return alert.description || 'This metric is outside its normal range.'
}

function suggestedAction(alert: any): string {
  const t = (alert.anomaly_type || '').toLowerCase()
  if (t === 'request_volume' || (alert.title || '').toLowerCase().includes('request volume'))
    return 'Review pending victim requests and assign NGOs or volunteers immediately.'
  if (t === 'resource_consumption') return 'Check current stock levels and consider triggering a resource restock or reallocation.'
  if (t === 'severity_escalation') return 'Escalate to field coordinators and verify disaster status in Live Map.'
  if (t === 'prediction_drift') return 'Trigger model retraining from the ML Sandbox to recalibrate predictions.'
  if (t === 'geo_surge') return 'Open Live Map and zoom into the affected area to assess deployment needs.'
  return 'Investigate further using the Live Map or Requests panel.'
}

// ─── UI constants ─────────────────────────────────────────────────────────────

const SEV_PILL: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400 ring-1 ring-red-200 dark:ring-red-500/20',
  high:     'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400 ring-1 ring-orange-200 dark:ring-orange-500/20',
  medium:   'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 ring-1 ring-amber-200 dark:ring-amber-500/20',
  low:      'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-400 ring-1 ring-slate-200 dark:ring-white/10',
}

const SEV_ICON: Record<string, typeof AlertTriangle> = {
  critical: ShieldAlert,
  high:     AlertTriangle,
  medium:   Shield,
  low:      ShieldCheck,
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high:     'bg-orange-500',
  medium:   'bg-amber-400',
  low:      'bg-slate-400',
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  request_volume:       <Users className="w-4 h-4" />,
  resource_consumption: <Package className="w-4 h-4" />,
  severity_escalation:  <TrendingUp className="w-4 h-4" />,
  prediction_drift:     <Activity className="w-4 h-4" />,
}

// ─── Sparkline ────────────────────────────────────────────────────────────────

/**
 * Generates or uses metric_history to render a tiny 60×20 SVG sparkline.
 * If no history data is present, synthesises a plausible 7-point trend from
 * the metric_value and anomaly_score so something meaningful is always shown.
 */
function Sparkline({ alert }: { alert: any }) {
  const history: number[] = useMemo(() => {
    if (Array.isArray(alert.metric_history) && alert.metric_history.length >= 2) {
      return alert.metric_history.slice(-7)
    }
    // Synthesise: flat baseline then spike at the end
    const base = Math.max(0.1, (alert.metric_value || 1) * 0.4)
    const spike = alert.metric_value || base * 2.5
    const seed = (alert.id || '').split('').reduce((acc: number, c: string) => acc + c.charCodeAt(0), 0)
    const noise = (i: number) => (((seed * (i + 7) * 1234567) % 100) / 100 - 0.5) * base * 0.3
    return [
      base + noise(0),
      base + noise(1),
      base * 1.1 + noise(2),
      base + noise(3),
      base * 0.9 + noise(4),
      base * 1.3 + noise(5),
      spike,
    ]
  }, [alert])

  const W = 60, H = 20, pad = 2
  const min = Math.min(...history)
  const max = Math.max(...history)
  const range = max - min || 1
  const pts = history.map((v, i) => {
    const x = pad + (i / (history.length - 1)) * (W - pad * 2)
    const y = H - pad - ((v - min) / range) * (H - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const color =
    alert.severity === 'critical' ? '#ef4444'
      : alert.severity === 'high' ? '#f97316'
        : alert.severity === 'medium' ? '#f59e0b'
          : '#94a3b8'

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="shrink-0 opacity-80">
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Dot on last (spike) point */}
      {pts.length > 0 && (() => {
        const last = pts[pts.length - 1].split(',')
        return <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
      })()}
    </svg>
  )
}

// ─── Refresh countdown ring ───────────────────────────────────────────────────

const REFRESH_INTERVAL = 30_000

function RefreshCountdown({ lastFetched }: { lastFetched: number }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(Math.min(Date.now() - lastFetched, REFRESH_INTERVAL))
    }, 1000)
    return () => clearInterval(id)
  }, [lastFetched])

  const pct = elapsed / REFRESH_INTERVAL
  const secs = Math.round(elapsed / 1000)
  const label = secs < 5 ? 'Just now' : secs < 60 ? `${secs}s ago` : `${Math.round(secs / 60)}m ago`

  // SVG ring: r=7, circumference ≈ 44
  const R = 7, C = 2 * Math.PI * R
  const dash = C * pct

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500 select-none" title={`Next auto-refresh in ~${Math.max(0, Math.round((REFRESH_INTERVAL - elapsed) / 1000))}s`}>
      <svg width="18" height="18" viewBox="0 0 18 18">
        <circle cx="9" cy="9" r={R} fill="none" stroke="currentColor" strokeWidth="2" opacity="0.15" />
        <circle
          cx="9" cy="9" r={R}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray={`${dash} ${C}`}
          strokeLinecap="round"
          transform="rotate(-90 9 9)"
          opacity="0.7"
        />
      </svg>
      <span>{label}</span>
    </div>
  )
}

// ─── AI root-cause analysis ───────────────────────────────────────────────────

function AIAnalysisButton({ alert }: { alert: any }) {
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [analysis, setAnalysis] = useState<string>('')

  const run = useCallback(async () => {
    setState('loading')
    setAnalysis('')
    try {
      const prompt = `You are a disaster management analyst. An anomaly alert has been detected with the following details:

Type: ${alert.anomaly_type || 'unknown'}
Severity: ${alert.severity || 'unknown'}
Title: ${alert.title || 'N/A'}
Metric: ${alert.metric_name || 'N/A'} = ${alert.metric_value ?? 'N/A'}
Anomaly Score: ${alert.anomaly_score ?? 'N/A'}
Description: ${alert.description || 'N/A'}
Detected: ${alert.detected_at || 'recently'}

Provide a concise root cause analysis in EXACTLY 3 bullet points. Each bullet must start with "• " and be one sentence. Focus on: (1) most likely cause, (2) immediate risk, (3) recommended action. Be direct and operational — this is for an admin dashboard.`

      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 300,
          messages: [{ role: 'user', content: prompt }],
        }),
      })

      const data = await res.json()
      const text = data?.content?.find((b: any) => b.type === 'text')?.text || ''
      setAnalysis(text.trim())
      setState('done')
    } catch {
      setState('error')
    }
  }, [alert])

  if (state === 'idle') {
    return (
      <button
        onClick={run}
        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400 hover:bg-purple-200 dark:hover:bg-purple-500/20 transition-colors font-medium"
      >
        <Sparkles className="w-3.5 h-3.5" />
        Get AI Analysis
      </button>
    )
  }

  if (state === 'loading') {
    return (
      <div className="rounded-lg bg-purple-50 dark:bg-purple-500/5 border border-purple-100 dark:border-purple-500/10 p-3">
        <div className="flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 text-purple-500 animate-spin shrink-0" />
          <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">Analysing anomaly context…</span>
        </div>
        <div className="mt-2 space-y-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="h-3 bg-purple-100 dark:bg-purple-500/10 rounded animate-pulse" style={{ width: `${70 + i * 10}%` }} />
          ))}
        </div>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="flex items-center gap-2 text-xs text-red-500">
        <XCircle className="w-3.5 h-3.5" />
        Analysis failed.
        <button onClick={run} className="underline hover:no-underline">Retry</button>
      </div>
    )
  }

  return (
    <div className="rounded-lg bg-purple-50 dark:bg-purple-500/5 border border-purple-100 dark:border-purple-500/10 p-3">
      <p className="text-xs font-semibold text-purple-700 dark:text-purple-400 mb-2 flex items-center gap-1">
        <Sparkles className="w-3 h-3" /> AI Root Cause Analysis
      </p>
      <div className="space-y-1">
        {analysis.split('\n').filter(l => l.trim()).map((line, i) => (
          <p key={i} className="text-xs text-purple-900 dark:text-purple-200 leading-relaxed">{line}</p>
        ))}
      </div>
      <button
        onClick={() => { setState('idle'); setAnalysis('') }}
        className="mt-2 text-[10px] text-purple-400 hover:text-purple-600 dark:hover:text-purple-300"
      >
        Dismiss
      </button>
    </div>
  )
}

// ─── Snooze button ─────────────────────────────────────────────────────────────

function SnoozeButton({ groupKey, alertIds, onSnooze }: {
  groupKey: string
  alertIds: string[]
  onSnooze: (key: string, until: number) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const snooze = (hours: number) => {
    onSnooze(groupKey, Date.now() + hours * 3_600_000)
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/15 transition-colors"
      >
        <Clock className="w-3 h-3" />
        Snooze
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute left-0 bottom-full mb-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-lg shadow-lg z-20 py-1 min-w-[120px]">
          {[1, 4, 24].map(h => (
            <button
              key={h}
              onClick={() => snooze(h)}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
            >
              Snooze {h}h
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── CSV Export ──────────────────────────────────────────────────────────────

function exportCSV(alerts: any[]) {
  const cols = ['id', 'anomaly_type', 'severity', 'metric_name', 'metric_value', 'anomaly_score', 'status', 'detected_at', 'title', 'description']
  const header = cols.join(',')
  const rows = alerts.map(a =>
    cols.map(c => {
      const v = a[c] ?? ''
      return typeof v === 'string' && v.includes(',') ? `"${v.replace(/"/g, '""')}"` : v
    }).join(',')
  )
  const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `anomaly_alerts_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Grouping with correlation detection ─────────────────────────────────────

interface AlertGroup {
  key: string
  representative: any
  count: number
  alerts: any[]
  correlatedKeys?: string[]   // keys of other groups likely related
}

const CORRELATION_WINDOW_MS = 30 * 60 * 1000  // 30 minutes

function groupAlerts(alerts: any[]): AlertGroup[] {
  const map = new Map<string, AlertGroup>()
  for (const a of alerts) {
    const key = `${a.anomaly_type || 'unknown'}__${a.severity || 'unknown'}`
    if (!map.has(key)) {
      map.set(key, { key, representative: a, count: 0, alerts: [] })
    }
    const g = map.get(key)!
    g.count++
    g.alerts.push(a)
    if (
      a.detected_at &&
      (!g.representative.detected_at ||
        new Date(a.detected_at) > new Date(g.representative.detected_at))
    ) {
      g.representative = a
    }
  }

  // ── Correlation pass: flag groups that fired within 30 min of each other ──
  const groups = [...map.values()]
  for (let i = 0; i < groups.length; i++) {
    for (let j = i + 1; j < groups.length; j++) {
      const aTime = new Date(groups[i].representative.detected_at || 0).getTime()
      const bTime = new Date(groups[j].representative.detected_at || 0).getTime()
      // Different anomaly_type and close in time = likely correlated
      const typeA = groups[i].representative.anomaly_type
      const typeB = groups[j].representative.anomaly_type
      if (typeA !== typeB && Math.abs(aTime - bTime) < CORRELATION_WINDOW_MS) {
        groups[i].correlatedKeys = [...(groups[i].correlatedKeys || []), groups[j].key]
        groups[j].correlatedKeys = [...(groups[j].correlatedKeys || []), groups[i].key]
      }
    }
  }

  const order = ['critical', 'high', 'medium', 'low']
  return groups.sort((a, b) => {
    const ai = order.indexOf(a.representative.severity)
    const bi = order.indexOf(b.representative.severity)
    if (ai !== bi) return ai - bi
    return b.count - a.count
  })
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function AnomalyAlertPanel({
  selectedDisasterId,
}: {
  selectedDisasterId?: string | null
}) {
  const queryClient = useQueryClient()
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [severityFilter, setSeverityFilter] = useState<string>('')
  const [showAllInGroup, setShowAllInGroup] = useState<string | null>(null)
  const [snoozedUntil, setSnoozedUntil] = useState<Record<string, number>>({})
  const [lastFetched, setLastFetched] = useState<number>(Date.now())

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['anomaly-alerts', statusFilter, selectedDisasterId],
    queryFn: async () => {
      const apiStatus = statusFilter || undefined
      let result
      if (selectedDisasterId) {
        try {
          result = await api.getDisasterAnomalies(selectedDisasterId, { status: apiStatus, limit: 100 })
        } catch {
          result = await api.getAnomalyAlerts({ status: apiStatus, limit: 100 })
        }
      } else {
        result = await api.getAnomalyAlerts({ status: apiStatus, limit: 100 })
      }
      setLastFetched(Date.now())
      return result
    },
    refetchInterval: REFRESH_INTERVAL,
    retry: 1,
    staleTime: 10_000,
  })

  const detectMutation = useMutation({
    mutationFn: () => api.runAnomalyDetection(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const acknowledgeMutation = useMutation({
    mutationFn: async (alertIds: string | string[]) => {
      const ids = Array.isArray(alertIds) ? alertIds : [alertIds]
      for (const id of ids) await api.acknowledgeAnomaly(id, 'current-user')
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const resolveMutation = useMutation({
    mutationFn: async ({ alertIds, status }: { alertIds: string | string[]; status: string }) => {
      const ids = Array.isArray(alertIds) ? alertIds : [alertIds]
      for (const id of ids) await api.resolveAnomaly(id, status)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const clearStaleMutation = useMutation({
    mutationFn: () => api.clearStaleAnomalies(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-alerts'] }),
  })

  const allAlerts: any[] = data?.alerts || (Array.isArray(data) ? data : [])

  const filteredAlerts = useMemo(() => {
    const now = Date.now()
    return (severityFilter ? allAlerts.filter((a: any) => a.severity === severityFilter) : allAlerts)
      .filter((a: any) => {
        const key = `${a.anomaly_type || 'unknown'}__${a.severity || 'unknown'}`
        return !(snoozedUntil[key] && snoozedUntil[key] > now)
      })
  }, [allAlerts, severityFilter, snoozedUntil])

  const groups = useMemo(() => groupAlerts(filteredAlerts), [filteredAlerts])

  const snoozedCount = useMemo(() => {
    const now = Date.now()
    return Object.values(snoozedUntil).filter(t => t > now).length
  }, [snoozedUntil])

  const sevCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const a of allAlerts) c[a.severity] = (c[a.severity] || 0) + 1
    return c
  }, [allAlerts])

  // Build a lookup from group key → group for correlation rendering
  const groupByKey = useMemo(() => {
    const m: Record<string, AlertGroup> = {}
    for (const g of groups) m[g.key] = g
    return m
  }, [groups])

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Bell className="w-5 h-5 text-amber-500" />
            Anomaly Alerts
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Unusual patterns detected in victim requests, resources, and disaster severity
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {/* Refresh countdown */}
          {!isLoading && <RefreshCountdown lastFetched={lastFetched} />}

          {/* Export CSV */}
          {filteredAlerts.length > 0 && (
            <button
              onClick={() => exportCSV(filteredAlerts)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400 text-xs font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
              title="Download current filtered alerts as CSV"
            >
              <Download className="w-3.5 h-3.5" />
              Export
            </button>
          )}

          <button
            onClick={() => clearStaleMutation.mutate()}
            disabled={clearStaleMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400 text-xs font-medium hover:bg-slate-200 dark:hover:bg-white/10 disabled:opacity-50 transition-colors"
            title="Archive anomaly alerts older than 3 days to reduce alert fatigue"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${clearStaleMutation.isPending ? 'animate-spin' : ''}`} />
            Clear Stale
          </button>
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
            {detectMutation.isPending
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Zap className="w-3.5 h-3.5" />}
            Run Detection
          </button>
        </div>
      </div>

      {/* ── Quick-summary bar ── */}
      {allAlerts.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {(['critical', 'high', 'medium', 'low'] as const).map(sev => {
            const cnt = sevCounts[sev] || 0
            const labels: Record<string, string> = {
              critical: 'Needs action NOW',
              high:     'Needs attention',
              medium:   'Worth checking',
              low:      'Low priority',
            }
            return (
              <button
                key={sev}
                onClick={() => setSeverityFilter(severityFilter === sev ? '' : sev)}
                className={`relative flex flex-col items-start p-3 rounded-xl border transition-all text-left ${
                  severityFilter === sev
                    ? 'ring-2 ring-offset-1 ring-amber-400 border-amber-300 dark:border-amber-500/40'
                    : 'border-slate-200 dark:border-white/10'
                } bg-white dark:bg-white/[0.02] hover:bg-slate-50 dark:hover:bg-white/[0.04]`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span className={`w-2 h-2 rounded-full ${SEV_DOT[sev]}`} />
                  <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 capitalize">{sev}</span>
                </div>
                <span className="text-xl font-bold text-slate-900 dark:text-white">{cnt}</span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 leading-tight mt-0.5">
                  {labels[sev]}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* ── Status filter chips ── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">Showing:</span>
        {[
          { val: 'active',       label: '🔴 Active' },
          { val: 'acknowledged', label: '👁 Acknowledged' },
          { val: 'resolved',     label: '✅ Resolved' },
          { val: '',             label: 'All' },
        ].map(({ val, label }) => (
          <button
            key={val}
            onClick={() => setStatusFilter(val)}
            className={`px-3 py-1 rounded-full text-[11px] font-semibold transition-colors ${
              statusFilter === val
                ? 'bg-amber-500 text-white'
                : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10'
            }`}
          >
            {label}
          </button>
        ))}
        {severityFilter && (
          <button
            onClick={() => setSeverityFilter('')}
            className="ml-2 flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 hover:bg-amber-200 transition-colors"
          >
            <XCircle className="w-3 h-3" />
            Clear severity filter
          </button>
        )}
        {snoozedCount > 0 && (
          <button
            onClick={() => setSnoozedUntil({})}
            className="ml-2 flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400 hover:bg-slate-200 transition-colors"
          >
            <Clock className="w-3 h-3" />
            {snoozedCount} snoozed — wake all
          </button>
        )}
      </div>

      {/* ── Content ── */}
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
                Cannot connect to anomaly detection service
              </p>
              <p className="text-xs text-red-500/80 dark:text-red-400/70 mt-1 max-w-xs mx-auto">
                {(error as Error)?.message || 'Make sure the backend server is running, then retry.'}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 text-xs font-medium hover:bg-red-200 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
                Retry Connection
              </button>
              <button
                onClick={() => detectMutation.mutate()}
                disabled={detectMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs font-medium hover:bg-amber-200 transition-colors disabled:opacity-50"
              >
                {detectMutation.isPending
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Zap className="w-3.5 h-3.5" />}
                Run Detection
              </button>
            </div>
          </div>
        </div>
      ) : groups.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-8 text-center">
          <ShieldCheck className="w-10 h-10 text-green-500 mx-auto mb-2" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Everything looks normal right now
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {allAlerts.length > 0
              ? `${allAlerts.length} alerts exist — adjust filters to view them`
              : 'No unusual patterns detected. Click "Run Detection" to do a fresh scan.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 dark:text-slate-400 px-1">
            Showing <strong className="text-slate-700 dark:text-slate-200">{groups.length}</strong> alert {groups.length === 1 ? 'group' : 'groups'} ({filteredAlerts.length} total alerts)
          </p>

          {groups.map(group => {
            const alert = group.representative
            const SevIcon = SEV_ICON[alert.severity] || Shield
            const isExpanded = expandedKey === group.key

            return (
              <div
                key={group.key}
                className={`rounded-xl border overflow-hidden transition-colors ${
                  alert.severity === 'critical'
                    ? 'border-red-200 dark:border-red-500/20'
                    : alert.severity === 'high'
                    ? 'border-orange-200 dark:border-orange-500/20'
                    : 'border-slate-200 dark:border-white/10'
                } bg-white dark:bg-white/[0.02]`}
              >
                {/* ── Correlation badge (above row) ── */}
                {group.correlatedKeys && group.correlatedKeys.length > 0 && (
                  <div className="px-4 pt-2 pb-0 flex items-center gap-1.5">
                    <Link2 className="w-3 h-3 text-indigo-400" />
                    <span className="text-[10px] text-indigo-500 dark:text-indigo-400 font-semibold">
                      Possibly related to: {group.correlatedKeys
                        .map(k => groupByKey[k]?.representative?.anomaly_type?.replace(/_/g, ' ') || k)
                        .join(', ')}
                    </span>
                  </div>
                )}

                {/* ── Row header ── */}
                <button
                  onClick={() => setExpandedKey(isExpanded ? null : group.key)}
                  className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-slate-50 dark:hover:bg-white/[0.03] transition-colors"
                >
                  <SevIcon className={`w-5 h-5 shrink-0 ${
                    alert.severity === 'critical' ? 'text-red-500'
                      : alert.severity === 'high' ? 'text-orange-500'
                      : alert.severity === 'medium' ? 'text-amber-500'
                      : 'text-slate-400'
                  }`} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-slate-900 dark:text-white">
                        {humanTitle(alert)}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${SEV_PILL[alert.severity]}`}>
                        {alert.severity}
                      </span>
                      {group.count > 1 && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400 font-semibold">
                          ×{group.count} occurrences
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1">
                        {alert.detected_at
                          ? `Detected ${formatDistanceToNow(new Date(alert.detected_at), { addSuffix: true })}`
                          : 'Recently detected'}
                        {alert.metric_value != null && ` · Value: ${Number(alert.metric_value).toFixed(1)}`}
                      </p>
                      {/* ── Inline sparkline ── */}
                      <Sparkline alert={alert} />
                    </div>
                  </div>

                  <ChevronDown className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                </button>

                {/* ── Expanded detail ── */}
                {isExpanded && (
                  <div className="border-t border-slate-100 dark:border-white/5 px-4 pb-4 pt-3 space-y-3">

                    {/* Plain-English impact */}
                    <div className="rounded-lg bg-amber-50 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10 p-3">
                      <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1 flex items-center gap-1">
                        <Info className="w-3 h-3" /> What this means
                      </p>
                      <p className="text-sm text-amber-900 dark:text-amber-200 leading-relaxed">
                        {humanImpact(alert)}
                      </p>
                    </div>

                    {/* Suggested action */}
                    <div className="rounded-lg bg-blue-50 dark:bg-blue-500/5 border border-blue-100 dark:border-blue-500/10 p-3">
                      <p className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1 flex items-center gap-1">
                        <ChevronRight className="w-3 h-3" /> Suggested action
                      </p>
                      <p className="text-sm text-blue-900 dark:text-blue-200 leading-relaxed">
                        {suggestedAction(alert)}
                      </p>
                    </div>

                    {/* AI root cause analysis */}
                    <AIAnalysisButton alert={alert} />

                    {/* Existing AI explanation (if any) */}
                    {alert.ai_explanation && (
                      <div className="rounded-lg bg-purple-50 dark:bg-purple-500/5 border border-purple-100 dark:border-purple-500/10 p-3">
                        <p className="text-xs font-semibold text-purple-700 dark:text-purple-400 mb-1 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> AI explanation
                        </p>
                        <p className="text-sm text-purple-900 dark:text-purple-200 leading-relaxed">
                          {alert.ai_explanation}
                        </p>
                      </div>
                    )}

                    {/* Technical stats */}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                      {alert.metric_name && (
                        <span>Metric: <strong className="text-slate-700 dark:text-slate-300">{alert.metric_name}</strong></span>
                      )}
                      {alert.metric_value != null && (
                        <span>Value: <strong className="text-slate-700 dark:text-slate-300">{Number(alert.metric_value).toFixed(2)}</strong></span>
                      )}
                      {alert.anomaly_score != null && (
                        <span>Score: <strong className="text-slate-700 dark:text-slate-300">{Number(alert.anomaly_score).toFixed(3)}</strong></span>
                      )}
                      {group.count > 1 && (
                        <span>{group.count} similar alerts grouped</span>
                      )}
                    </div>

                    {/* Individual alerts in group */}
                    {group.count > 1 && (
                      <div>
                        <button
                          onClick={() =>
                            setShowAllInGroup(showAllInGroup === group.key ? null : group.key)
                          }
                          className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 underline underline-offset-2"
                        >
                          {showAllInGroup === group.key
                            ? 'Hide individual alerts'
                            : `View all ${group.count} individual alerts`}
                        </button>
                        {showAllInGroup === group.key && (
                          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto rounded-lg border border-slate-100 dark:border-white/5">
                            {group.alerts.map((a: any, i: number) => (
                              <div
                                key={a.id || i}
                                className="flex items-center justify-between px-3 py-1.5 text-xs text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/[0.02]"
                              >
                                <span>
                                  {a.detected_at
                                    ? formatDistanceToNow(new Date(a.detected_at), { addSuffix: true })
                                    : `Alert #${i + 1}`}
                                </span>
                                {a.metric_value != null && (
                                  <span className="font-medium text-slate-700 dark:text-slate-300">
                                    {Number(a.metric_value).toFixed(1)}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Action buttons */}
                    {alert.status === 'active' && (
                      <div className="flex gap-2 pt-1 flex-wrap">
                        <button
                          onClick={() => acknowledgeMutation.mutate(group.alerts.map((a: any) => a.id))}
                          disabled={acknowledgeMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          {group.count > 1 ? `Acknowledge all ${group.count}` : 'Acknowledge'}
                        </button>
                        <button
                          onClick={() => resolveMutation.mutate({ alertIds: group.alerts.map((a: any) => a.id), status: 'resolved' })}
                          disabled={resolveMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-500/20 transition-colors disabled:opacity-50"
                        >
                          <ShieldCheck className="w-3 h-3" />
                          Mark as resolved
                        </button>
                        <button
                          onClick={() => resolveMutation.mutate({ alertIds: group.alerts.map((a: any) => a.id), status: 'false_positive' })}
                          disabled={resolveMutation.isPending}
                          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/15 transition-colors disabled:opacity-50"
                        >
                          <XCircle className="w-3 h-3" />
                          False alarm
                        </button>
                        <SnoozeButton
                          groupKey={group.key}
                          alertIds={group.alerts.map((a: any) => a.id)}
                          onSnooze={(key, until) => setSnoozedUntil(prev => ({ ...prev, [key]: until }))}
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
