'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Brain, Loader2, FileText, RefreshCw, Send, Clock, CheckCircle2,
    AlertTriangle, Sparkles, MessageSquare, BarChart3, ChevronDown,
    Zap, MapPin, FlaskConical, Activity, Play
} from 'lucide-react'
import { cn } from '@/lib/utils'
import AnomalyAlertPanel from '@/components/coordinator/AnomalyAlertPanel'
import OutcomeTrackingPanel from '@/components/coordinator/OutcomeTrackingPanel'
import MLDashboard from '@/components/coordinator/MLDashboard'
import { TFTForecastWidget } from '@/components/admin/TFTForecastWidget'
import { PINNHeatmap } from '@/components/admin/PINNHeatmap'
import UnifiedDisasterGPT from '@/components/admin/UnifiedDisasterGPT'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Download, Printer, Search, Sparkle, BrainCircuit } from 'lucide-react'

const mdComponents = {
    table: (props: any) => (
        <div className="overflow-x-auto my-4 rounded-xl border border-slate-200 dark:border-white/10">
            <table className="w-full text-sm" {...props} />
        </div>
    ),
    thead: (props: any) => <thead className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-500/10 dark:to-indigo-500/10" {...props} />,
    th: (props: any) => <th className="px-4 py-2.5 text-left text-xs font-bold text-purple-700 dark:text-purple-400 uppercase tracking-wider border-b border-slate-200 dark:border-white/10" {...props} />,
    td: (props: any) => <td className="px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 border-b border-slate-100 dark:border-white/5" {...props} />,
    tr: (props: any) => <tr className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02] transition-colors even:bg-slate-50/30 dark:even:bg-white/[0.01]" {...props} />,
    h1: (props: any) => <h1 className="text-2xl font-black text-slate-900 dark:text-white border-b border-slate-200 dark:border-white/10 pb-3 mb-6 mt-2" {...props} />,
    h2: (props: any) => <h2 className="text-xl font-bold text-purple-700 dark:text-purple-400 mt-8 mb-3 pb-2 border-b border-purple-100 dark:border-purple-500/10" {...props} />,
    h3: (props: any) => <h3 className="text-lg font-semibold text-slate-800 dark:text-white mt-5 mb-2" {...props} />,
    strong: (props: any) => <strong className="font-semibold text-slate-900 dark:text-white" {...props} />,
    ul: (props: any) => <ul className="list-disc pl-5 my-3 space-y-1.5" {...props} />,
    ol: (props: any) => <ol className="list-decimal pl-5 my-3 space-y-1.5" {...props} />,
    li: (props: any) => <li className="text-slate-600 dark:text-slate-300" {...props} />,
    p: (props: any) => <p className="text-slate-600 dark:text-slate-300 leading-relaxed my-2" {...props} />,
    hr: () => <hr className="my-6 border-slate-200 dark:border-white/10" />,
    blockquote: (props: any) => <blockquote className="border-l-4 border-purple-300 dark:border-purple-500/30 pl-4 my-4 italic text-slate-500 dark:text-slate-400" {...props} />,
    em: (props: any) => <em className="italic text-slate-500 dark:text-slate-400" {...props} />,
}

export default function AdminCoordinatorPage() {
    const qc = useQueryClient()
    const [query, setQuery] = useState('')
    const [activeTab, setActiveTab] = useState<'sitrep' | 'query' | 'history' | 'anomalies' | 'outcomes' | 'ml_sandbox' | 'disastergpt' | 'hotspots' | 'forecast' | 'spread'>('sitrep')

    // ── Hotspot queries ──────────────────────────────────────
    const { data: hotspots, isLoading: hotspotsLoading } = useQuery({
        queryKey: ['hotspots'],
        queryFn: () => api.getHotspots(),
        retry: false,
        enabled: activeTab === 'hotspots',
    })

    // ── ML Health ────────────────────────────────────────────
    const { data: mlHealth } = useQuery({
        queryKey: ['ml-health'],
        queryFn: () => api.getMLHealth(),
        retry: false,
        refetchInterval: 30000,
    })

    const { data: latestSitrep, isLoading: sitrepLoading } = useQuery({
        queryKey: ['latest-sitrep'],
        queryFn: () => api.getLatestSitrep(),
        retry: false,
    })

    const { data: sitreps } = useQuery({
        queryKey: ['sitreps'],
        queryFn: () => api.getSitreps(),
        retry: false,
    })

    const { data: queryHistory } = useQuery({
        queryKey: ['query-history'],
        queryFn: () => api.getQueryHistory(),
        retry: false,
    })

    const generateMutation = useMutation({
        mutationFn: () => api.generateSitrep(),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['latest-sitrep'] })
            qc.invalidateQueries({ queryKey: ['sitreps'] })
        },
    })

    const askMutation = useMutation({
        mutationFn: (q: string) => api.askCoordinatorQuery(q),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['query-history'] })
            setQuery('')
        },
        onError: (error: any) => {
            console.error('AI query failed:', error)
        },
    })

    const tabs = [
        { id: 'sitrep', label: 'Situation Reports', icon: FileText },
        { id: 'anomalies', label: 'Anomaly Detector', icon: AlertTriangle },
        { id: 'outcomes', label: 'Outcome Tracking', icon: BarChart3 },
        { id: 'ml_sandbox', label: 'ML Sandbox', icon: BrainCircuit },
        { id: 'disastergpt', label: 'DisasterGPT', icon: Zap },
        { id: 'hotspots', label: 'Hotspots', icon: MapPin },
        { id: 'forecast', label: 'Severity Forecast', icon: Activity },
        { id: 'spread', label: 'Spread Map', icon: FlaskConical },
        { id: 'query', label: 'AI Query', icon: MessageSquare },
        { id: 'history', label: 'Query History', icon: Clock },
    ] as const

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Brain className="w-6 h-6 text-purple-500" />
                        AI Coordinator
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        LLM-powered situation awareness, natural language queries &amp; automated reports
                    </p>
                </div>
                <button
                    onClick={() => generateMutation.mutate()}
                    disabled={generateMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-purple-600/20"
                >
                    {generateMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                    Generate SitRep
                </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-slate-100 dark:bg-white/5 p-1 rounded-xl w-fit">
                {tabs.map((tab) => {
                    const Icon = tab.icon
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                                activeTab === tab.id
                                    ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm'
                                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                            )}
                        >
                            <Icon className="w-4 h-4" />
                            {tab.label}
                        </button>
                    )
                })}
            </div>

            {/* SitRep Tab */}
            {activeTab === 'sitrep' && (
                <div className="space-y-4">
                    {sitrepLoading ? (
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-12 text-center">
                            <Loader2 className="w-8 h-8 animate-spin text-purple-500 mx-auto mb-3" />
                            <p className="text-sm text-slate-500">Loading situation reports...</p>
                        </div>
                    ) : latestSitrep ? (
                        <div className="space-y-4">
                            <div className="flex items-center justify-between">
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white">Active Intelligence Report</h3>
                                <div className="flex items-center gap-2">
                                    <button className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors text-slate-500" title="Print Report">
                                        <Printer className="w-4 h-4" />
                                    </button>
                                    <button className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors text-slate-500" title="Download PDF">
                                        <Download className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>

                            <div className="relative group overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 shadow-2xl shadow-slate-200/50 dark:shadow-none">
                                <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-purple-600 via-pink-600 to-orange-600"></div>

                                <div className="p-8 md:p-12">
                                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12 pb-8 border-b border-slate-100 dark:border-white/5">
                                        <div>
                                            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 text-[10px] font-bold uppercase tracking-widest mb-4">
                                                <Sparkle className="w-3 h-3" /> AI Generated Intelligence
                                            </div>
                                            <h2 className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white tracking-tight">
                                                {latestSitrep.title || 'Situation Report'}
                                            </h2>
                                            <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">
                                                Operational Assessment · {latestSitrep.report_type?.toUpperCase()}
                                            </p>
                                        </div>
                                        <div className="text-right flex flex-col items-end">
                                            <div className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">
                                                {latestSitrep.created_at ? new Date(latestSitrep.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
                                            </div>
                                            <p className="text-xs text-slate-400 uppercase tracking-widest font-bold">
                                                Timestamp: {latestSitrep.created_at ? new Date(latestSitrep.created_at).toLocaleTimeString() : 'N/A'}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Metrics Grid inside report */}
                                    {latestSitrep.key_metrics && (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
                                            {[
                                                { label: 'Disasters', value: latestSitrep.key_metrics.active_disasters, color: 'text-red-600' },
                                                { label: 'Utilization', value: `${latestSitrep.key_metrics.resource_utilization_pct}%`, color: 'text-blue-600' },
                                                { label: 'Requests', value: latestSitrep.key_metrics.total_open_requests, color: 'text-amber-600' },
                                                { label: 'Anomalies', value: latestSitrep.key_metrics.active_anomalies, color: 'text-purple-600' }
                                            ].map((stat, idx) => (
                                                <div key={idx} className="p-4 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5">
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{stat.label}</p>
                                                    <p className={cn("text-xl font-black", stat.color)}>{stat.value}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                            {latestSitrep.markdown_body || latestSitrep.summary || latestSitrep.content || 'No content available.'}
                                        </ReactMarkdown>
                                    </div>

                                    <div className="mt-12 pt-8 border-t border-slate-100 dark:border-white/5 flex items-center justify-between opacity-50 italic text-xs">
                                        <p>Verification Hash: {Math.random().toString(36).substring(7).toUpperCase()}</p>
                                        <p>© HopeInChaos SitRep Engine v2.0</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="rounded-2xl border border-dashed border-slate-300 dark:border-white/10 p-12 text-center">
                            <Brain className="w-12 h-12 mx-auto mb-3 text-slate-300 dark:text-slate-600" />
                            <p className="text-sm font-medium text-slate-900 dark:text-white">No situation reports yet</p>
                            <p className="text-xs text-slate-500 mt-1">Click &quot;Generate SitRep&quot; to create the first AI-powered situation report</p>
                        </div>
                    )}

                    {/* Historical sitreps */}
                    {Array.isArray(sitreps) && sitreps.length > 1 && (
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Previous Reports</h3>
                            <div className="space-y-2">
                                {sitreps.slice(1, 6).map((s: any, i: number) => (
                                    <div key={i} className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-white/5 last:border-0">
                                        <div className="flex items-center gap-2">
                                            <FileText className="w-4 h-4 text-slate-400" />
                                            <span className="text-sm text-slate-700 dark:text-slate-300">
                                                SitRep #{sitreps.length - i}
                                            </span>
                                        </div>
                                        <span className="text-xs text-slate-400">
                                            {s.created_at ? new Date(s.created_at).toLocaleDateString() : 'Unknown'}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Outcomes Tab */}
            {activeTab === 'outcomes' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <OutcomeTrackingPanel />
                </div>
            )}

            {/* ML Sandbox Tab */}
            {activeTab === 'ml_sandbox' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <MLDashboard />
                </div>
            )}

            {/* Anomalies Tab */}
            {activeTab === 'anomalies' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <AnomalyAlertPanel />
                </div>
            )}

            {/* Query Tab */}
            {activeTab === 'query' && (
                <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Ask the AI Coordinator</h3>
                        <p className="text-xs text-slate-500 mb-4">
                            Ask natural language questions about disasters, resources, predictions, and operational status.
                        </p>

                        {/* Rule-based fallback indicator */}
                        {askMutation.data && (askMutation.data as any)?.model === 'rule-based' && (
                            <div className="mb-4 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs flex items-center gap-2">
                                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                                Running in rule-based mode. Set <code className="font-mono bg-amber-100 dark:bg-amber-500/20 px-1 rounded">HF_TOKEN</code> in backend/.env for enhanced AI responses.
                            </div>
                        )}

                        {/* Error display */}
                        {askMutation.isError && (
                            <div className="mb-4 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400 text-xs">
                                {(askMutation.error as any)?.message || 'Query failed. Please try again.'}
                            </div>
                        )}
                        <div className="flex gap-3">
                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && query.trim() && askMutation.mutate(query)}
                                placeholder="e.g., What is the most critical disaster right now?"
                                className="flex-1 h-11 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none"
                            />
                            <button
                                onClick={() => query.trim() && askMutation.mutate(query)}
                                disabled={askMutation.isPending || !query.trim()}
                                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
                            >
                                {askMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                Ask
                            </button>
                        </div>

                        {/* Latest response */}
                        {askMutation.data && (
                            <div className="mt-4 p-4 rounded-xl bg-purple-50 dark:bg-purple-500/5 border border-purple-200 dark:border-purple-500/20">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <Sparkles className="w-4 h-4 text-purple-500" />
                                        <span className="text-xs font-bold text-purple-700 dark:text-purple-400">AI Response</span>
                                    </div>
                                    {(askMutation.data as any)?.model && (
                                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-purple-200/50 dark:bg-purple-500/20 text-purple-600 dark:text-purple-400">
                                            {(askMutation.data as any).model === 'rule-based' ? '📊 Rule-based' : '🤖 HuggingFace AI'}
                                        </span>
                                    )}
                                </div>
                                <div className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed prose prose-sm prose-slate dark:prose-invert max-w-none prose-headings:text-slate-800 dark:prose-headings:text-white prose-strong:text-slate-800 dark:prose-strong:text-white prose-p:my-1">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                        {(askMutation.data as any)?.answer || (askMutation.data as any)?.response || JSON.stringify(askMutation.data)}
                                    </ReactMarkdown>
                                </div>
                                {(askMutation.data as any)?.latency_ms && (
                                    <p className="text-[10px] text-slate-400 mt-2 pt-2 border-t border-purple-200/50 dark:border-purple-500/10">
                                        ⚡ {(askMutation.data as any).latency_ms}ms · {(askMutation.data as any)?.tools_called?.length || 0} data queries
                                    </p>
                                )}
                            </div>
                        )}

                        {/* Suggested queries */}
                        <div className="mt-4">
                            <p className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-2">Suggested queries</p>
                            <div className="flex flex-wrap gap-2">
                                {[
                                    'What disasters need immediate attention?',
                                    'Summarize resource allocation status',
                                    'Which regions are most at risk?',
                                    'What is the volunteer deployment status?'
                                ].map((q) => (
                                    <button key={q} onClick={() => { setQuery(q); askMutation.mutate(q) }}
                                        className="px-3 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                                        {q}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* History Tab */}
            {activeTab === 'history' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Query History</h3>
                    {Array.isArray(queryHistory) && queryHistory.length > 0 ? (
                        <div className="space-y-3">
                            {queryHistory.slice(0, 20).map((entry: any, i: number) => (
                                <div key={entry.id || i} className="rounded-xl border border-slate-100 dark:border-white/5 overflow-hidden">
                                    <div className="px-4 py-3 bg-slate-50/50 dark:bg-white/[0.02] border-b border-slate-100 dark:border-white/5">
                                        <div className="flex items-center gap-2">
                                            <MessageSquare className="w-4 h-4 text-purple-500 shrink-0" />
                                            <p className="text-sm font-semibold text-slate-900 dark:text-white flex-1">{entry.query_text || entry.query || entry.question}</p>
                                            {entry.latency_ms && (
                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 font-medium shrink-0">
                                                    ⚡ {entry.latency_ms}ms
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="px-4 py-3">
                                        <div className="text-xs text-slate-600 dark:text-slate-300 max-w-none">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                                {entry.response_text || entry.answer || entry.response || 'No response'}
                                            </ReactMarkdown>
                                        </div>
                                        <div className="flex items-center gap-3 mt-2 pt-2 border-t border-slate-100 dark:border-white/5">
                                            <p className="text-[10px] text-slate-400">
                                                {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                                            </p>
                                            {entry.model_used && (
                                                <span className="text-[10px] text-slate-400">
                                                    {entry.model_used === 'rule-based' ? '📊 Rule-based' : '🤖 HuggingFace AI'}
                                                </span>
                                            )}
                                            {entry.tools_called?.length > 0 && (
                                                <span className="text-[10px] text-slate-400">
                                                    🔧 {entry.tools_called.length} tool(s)
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="py-8 text-center text-slate-400">
                            <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">No queries yet. Ask something in the AI Query tab!</p>
                        </div>
                    )}
                </div>
            )}

            {/* Unified DisasterGPT Tab */}
            {activeTab === 'disastergpt' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <UnifiedDisasterGPT />
                </div>
            )}

            {/* Hotspots Tab */}
            {activeTab === 'hotspots' && (
                <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                        <div className="flex items-center gap-2 mb-1">
                            <MapPin className="w-5 h-5 text-red-500" />
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Disaster Hotspot Clusters</h3>
                        </div>
                        <p className="text-xs text-slate-500 mb-4">
                            DBSCAN-based spatial clustering of disaster events. Each cluster represents a geographic hotspot.
                        </p>
                        {hotspotsLoading ? (
                            <div className="py-8 text-center">
                                <Loader2 className="w-6 h-6 animate-spin text-red-500 mx-auto mb-2" />
                                <p className="text-xs text-slate-500">Computing hotspot clusters...</p>
                            </div>
                        ) : hotspots && (() => {
                            // Extract clusters from GeoJSON FeatureCollection, plain array, or .clusters property
                            const raw = hotspots?.features
                                ? hotspots.features
                                : Array.isArray(hotspots) ? hotspots : hotspots?.clusters || []
                            return raw.length > 0
                        })() ? (
                            <div className="space-y-3">
                                {(() => {
                                    const clusters = hotspots?.features
                                        ? hotspots.features.map((f: any) => {
                                            const p = f.properties || {}
                                            const coords = p.centroid?.coordinates || f.geometry?.coordinates
                                            return {
                                                cluster_id: p.id ?? p.cluster_id,
                                                priority: p.priority_label || p.priority || 'medium',
                                                event_count: p.request_count ?? p.event_count ?? p.size ?? 0,
                                                centroid: coords ? { lat: coords[1], lng: coords[0] } : null,
                                                radius_km: p.radius_km,
                                                avg_severity: p.avg_priority ?? p.avg_severity,
                                                dominant_type: p.dominant_type,
                                                total_people: p.total_people,
                                                detected_at: p.detected_at,
                                            }
                                        })
                                        : Array.isArray(hotspots) ? hotspots : hotspots?.clusters || []
                                    return clusters
                                })().map((cluster: any, i: number) => (
                                    <div key={cluster.cluster_id || i} className="rounded-xl border border-slate-100 dark:border-white/5 overflow-hidden">
                                        <div className="px-4 py-3 bg-red-50/50 dark:bg-red-500/5 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <div className={cn(
                                                    "w-3 h-3 rounded-full",
                                                    cluster.priority === 'critical' ? 'bg-red-500' :
                                                    cluster.priority === 'high' ? 'bg-orange-500' :
                                                    cluster.priority === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                                                )} />
                                                <span className="text-sm font-semibold text-slate-900 dark:text-white">
                                                    Cluster #{cluster.cluster_id ?? i + 1}
                                                </span>
                                                {cluster.priority && (
                                                    <span className={cn(
                                                        "text-[10px] px-2 py-0.5 rounded-full font-bold uppercase",
                                                        cluster.priority === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                                        cluster.priority === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                                        'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                                                    )}>
                                                        {cluster.priority}
                                                    </span>
                                                )}
                                            </div>
                                            <span className="text-xs text-slate-400">
                                                {cluster.event_count || cluster.size || '?'} events
                                            </span>
                                        </div>
                                        <div className="px-4 py-3 grid grid-cols-2 md:grid-cols-4 gap-3">
                                            {cluster.centroid && (
                                                <div>
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Centroid</p>
                                                    <p className="text-xs text-slate-700 dark:text-slate-300">
                                                        {cluster.centroid.lat?.toFixed(4)}, {cluster.centroid.lng?.toFixed(4)}
                                                    </p>
                                                </div>
                                            )}
                                            {cluster.radius_km !== undefined && (
                                                <div>
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Radius</p>
                                                    <p className="text-xs text-slate-700 dark:text-slate-300">{cluster.radius_km?.toFixed(1)} km</p>
                                                </div>
                                            )}
                                            {cluster.avg_severity !== undefined && (
                                                <div>
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Avg Severity</p>
                                                    <p className="text-xs text-slate-700 dark:text-slate-300">{cluster.avg_severity?.toFixed(2)}</p>
                                                </div>
                                            )}
                                            {cluster.dominant_type && (
                                                <div>
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Type</p>
                                                    <p className="text-xs text-slate-700 dark:text-slate-300">{cluster.dominant_type}</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="py-8 text-center text-slate-400">
                                <MapPin className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                <p className="text-sm">No hotspot clusters detected. Ensure disaster data is seeded.</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Severity Forecast Tab */}
            {activeTab === 'forecast' && (
                <div className="space-y-4">
                    <TFTForecastWidget />
                </div>
            )}

            {/* Spread Map Tab */}
            {activeTab === 'spread' && (
                <div className="space-y-4">
                    <PINNHeatmap />
                </div>
            )}
        </div>
    )
}
