'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Brain, Loader2, FileText, RefreshCw, Send, Clock, CheckCircle2,
    AlertTriangle, Sparkles, MessageSquare, BarChart3, ChevronDown
} from 'lucide-react'
import { cn } from '@/lib/utils'

export default function AdminCoordinatorPage() {
    const qc = useQueryClient()
    const [query, setQuery] = useState('')
    const [activeTab, setActiveTab] = useState<'sitrep' | 'query' | 'history'>('sitrep')

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
    })

    const tabs = [
        { id: 'sitrep', label: 'Situation Reports', icon: FileText },
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
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Latest Situation Report</h3>
                                    </div>
                                    <p className="text-xs text-slate-400">
                                        Generated: {latestSitrep.created_at ? new Date(latestSitrep.created_at).toLocaleString() : 'N/A'}
                                    </p>
                                </div>
                            </div>
                            <div className="prose dark:prose-invert max-w-none text-sm">
                                <div className="whitespace-pre-wrap leading-relaxed text-slate-700 dark:text-slate-300">
                                    {latestSitrep.summary || latestSitrep.content || 'No content available.'}
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

            {/* Query Tab */}
            {activeTab === 'query' && (
                <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Ask the AI Coordinator</h3>
                        <p className="text-xs text-slate-500 mb-4">
                            Ask natural language questions about disasters, resources, predictions, and operational status.
                        </p>
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
                                <div className="flex items-center gap-2 mb-2">
                                    <Sparkles className="w-4 h-4 text-purple-500" />
                                    <span className="text-xs font-bold text-purple-700 dark:text-purple-400">AI Response</span>
                                </div>
                                <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                                    {(askMutation.data as any)?.answer || (askMutation.data as any)?.response || JSON.stringify(askMutation.data)}
                                </p>
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
                                <div key={i} className="p-3 rounded-xl border border-slate-100 dark:border-white/5">
                                    <div className="flex items-start gap-2">
                                        <MessageSquare className="w-4 h-4 text-purple-500 mt-0.5 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-slate-900 dark:text-white">{entry.query || entry.question}</p>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">
                                                {entry.answer || entry.response || 'No response'}
                                            </p>
                                            <p className="text-[10px] text-slate-400 mt-1">
                                                {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                                            </p>
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
        </div>
    )
}
