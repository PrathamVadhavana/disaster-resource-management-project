'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useState } from 'react'
import {
  FileText, RefreshCw, Clock, AlertTriangle, BarChart3,
  ChevronRight, Loader2, Calendar, Zap
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

export default function SituationReportPanel() {
  const queryClient = useQueryClient()
  const [selectedReport, setSelectedReport] = useState<any>(null)

  const { data: reportsData, isLoading } = useQuery({
    queryKey: ['sitreps'],
    queryFn: () => api.getSitreps({ limit: 10 }),
    refetchInterval: 60_000,
  })

  const { data: latestReport } = useQuery({
    queryKey: ['sitrep-latest'],
    queryFn: () => api.getLatestSitrep().catch(() => null),
    retry: false,
  })

  const generateMutation = useMutation({
    mutationFn: () => api.generateSitrep('on_demand', 'user'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sitreps'] })
      queryClient.invalidateQueries({ queryKey: ['sitrep-latest'] })
    },
  })

  const reports = reportsData?.reports || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            Situation Reports
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            AI-generated daily briefings on disaster status, resources, and recommendations
          </p>
        </div>
        <button
          onClick={() => generateMutation.mutate()}
          disabled={generateMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500 text-white text-sm font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
        >
          {generateMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
          Generate Report
        </button>
      </div>

      {/* Latest report preview */}
      {latestReport && !selectedReport && (
        <div className="rounded-2xl border border-blue-200 dark:border-blue-500/20 bg-blue-50/50 dark:bg-blue-500/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-900 dark:text-white text-sm">
              {latestReport.title}
            </h3>
            <span className="text-xs text-slate-500">
              {latestReport.created_at &&
                formatDistanceToNow(new Date(latestReport.created_at), { addSuffix: true })}
            </span>
          </div>
          {latestReport.summary && (
            <p className="text-sm text-slate-600 dark:text-slate-300 mb-3">
              {latestReport.summary}
            </p>
          )}
          {/* Key metrics */}
          {latestReport.key_metrics && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
              {Object.entries(latestReport.key_metrics as Record<string, number>).slice(0, 4).map(([key, value]) => (
                <div key={key} className="text-center p-2 rounded-lg bg-white/60 dark:bg-white/5">
                  <p className="text-lg font-bold text-slate-900 dark:text-white">{value}</p>
                  <p className="text-[10px] text-slate-500 capitalize">{key.replace(/_/g, ' ')}</p>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => setSelectedReport(latestReport)}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
          >
            Read Full Report <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Full report view */}
      {selectedReport && (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-900 dark:text-white">
              {selectedReport.title}
            </h3>
            <button
              onClick={() => setSelectedReport(null)}
              className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            >
              ← Back to list
            </button>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-500 mb-4">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              {selectedReport.report_date}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {selectedReport.generation_time_ms}ms
            </span>
            <span className="capitalize px-2 py-0.5 rounded-full bg-slate-100 dark:bg-white/10">
              {selectedReport.report_type}
            </span>
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
            {selectedReport.markdown_body}
          </div>
        </div>
      )}

      {/* Report list */}
      {!selectedReport && (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-white/5">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Report History</h3>
          </div>
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          ) : reports.length > 0 ? (
            <div className="divide-y divide-slate-100 dark:divide-white/5">
              {reports.map((report: any) => (
                <button
                  key={report.id}
                  onClick={async () => {
                    const full = await api.getSitrep(report.id)
                    setSelectedReport(full)
                  }}
                  className="w-full flex items-center gap-4 px-5 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors text-left"
                >
                  <FileText className="w-4 h-4 text-blue-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                      {report.title}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {report.report_date} · {report.report_type}
                    </p>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    report.status === 'generated' ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' :
                    report.status === 'emailed' ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400' :
                    'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                  }`}>
                    {report.status}
                  </span>
                  <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                </button>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center text-slate-400 text-sm">
              No reports generated yet. Click "Generate Report" to create one.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
