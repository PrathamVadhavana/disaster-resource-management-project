'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Brain, Loader2, FileText, RefreshCw, Send, Clock, CheckCircle2,
    AlertTriangle, Sparkles, MessageSquare, BarChart3, ChevronDown,
    Zap, MapPin, FlaskConical, Activity, Play, X, ChevronRight,
    Download, Printer, Search, Sparkle, BrainCircuit, Calendar,
    Timer, TrendingUp, Eye, Trash2, RotateCcw, Plus, Settings,
    Filter, Globe
} from 'lucide-react'
import { cn } from '@/lib/utils'
import AnomalyAlertPanel from '@/components/coordinator/AnomalyAlertPanel'
import OutcomeTrackingPanel from '@/components/coordinator/OutcomeTrackingPanel'
import MLDashboard from '@/components/coordinator/MLDashboard'
import { TFTForecastWidget } from '@/components/admin/TFTForecastWidget'
import { PINNHeatmap } from '@/components/admin/PINNHeatmap'
import ScheduleSitrepButton from '@/components/admin/ScheduleSitrepButton'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import HotspotPanel from '@/components/coordinator/HotspotPanel'

const mdComponents = {
    table: (props: any) => (
        <div className="w-full overflow-x-auto my-6 rounded-xl border border-slate-200 dark:border-white/10">
            <table className="w-full min-w-[600px] border-collapse text-sm" {...props} />
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

const REPORT_TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
    daily: { bg: 'bg-blue-50 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400', border: 'border-blue-200 dark:border-blue-500/20' },
    incident: { bg: 'bg-red-50 dark:bg-red-500/10', text: 'text-red-700 dark:text-red-400', border: 'border-red-200 dark:border-red-500/20' },
    custom: { bg: 'bg-purple-50 dark:bg-purple-500/10', text: 'text-purple-700 dark:text-purple-400', border: 'border-purple-200 dark:border-purple-500/20' },
}

const SEVERITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-yellow-500',
    low: 'bg-green-500',
}

export default function AdminCoordinatorPage() {
    const qc = useQueryClient()
    const [query, setQuery] = useState('')
    const [activeTab, setActiveTab] = useState<'sitrep' | 'query' | 'history' | 'anomalies' | 'outcomes' | 'ml_sandbox' | 'disastergpt' | 'hotspots' | 'forecast' | 'spread'>('sitrep')
    const [selectedSitrep, setSelectedSitrep] = useState<any>(null)
    const [showGeneratePanel, setShowGeneratePanel] = useState(false)
    const [generateConfig, setGenerateConfig] = useState({
        report_type: 'daily',
        date_range: '7d',
        sections: ['executive_summary', 'resource_status', 'active_incidents', 'recommendations']
    })
    const [streamingOutput, setStreamingOutput] = useState('')
    const [isStreaming, setIsStreaming] = useState(false)
    const [showMoreTabs, setShowMoreTabs] = useState(false)
    const [selectedDisasterId, setSelectedDisasterId] = useState<string | null>(null)
    const [showDisasterFilter, setShowDisasterFilter] = useState(false)
    
    // AI Query conversation memory
    const [conversationHistory, setConversationHistory] = useState<Array<{
        question: string
        answer: string
        timestamp: Date
    }>>([])

    // Fetch disasters for filter dropdown
    const { data: disasterList } = useQuery({
        queryKey: ['disasters-for-filter'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 50 }),
        retry: false,
    })

    // ── Hotspot queries ──────────────────────────────────────
    const { data: hotspots, isLoading: hotspotsLoading } = useQuery({
        queryKey: ['hotspots', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterHotspots(selectedDisasterId) : api.getHotspots(),
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
        queryKey: ['latest-sitrep', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterSitrep(selectedDisasterId, { limit: 1 }).then(r => Array.isArray(r) ? r[0] : r) : api.getLatestSitrep(),
        retry: false,
    })

    const { data: sitreps } = useQuery({
        queryKey: ['sitreps', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterSitrep(selectedDisasterId) : api.getSitreps(),
        retry: false,
    })

    const { data: queryHistory } = useQuery({
        queryKey: ['query-history', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterQueryHistory(selectedDisasterId) : api.getQueryHistory(),
        retry: false,
    })

    // Get latest disaster for context
    const { data: disasters } = useQuery({
        queryKey: ['disasters-for-sitrep'],
        queryFn: () => api.getDisasters({ limit: 5, status: 'active' }),
        retry: false,
    })

    // ── Anomaly queries ──────────────────────────────────────
    const { data: anomalyAlerts, isLoading: anomaliesLoading } = useQuery({
        queryKey: ['anomaly-alerts', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterAnomalies(selectedDisasterId) : api.getAnomalyAlerts(),
        retry: false,
        enabled: activeTab === 'anomalies',
    })

    // ── Outcome queries ──────────────────────────────────────
    const { data: outcomes, isLoading: outcomesLoading } = useQuery({
        queryKey: ['outcomes', selectedDisasterId],
        queryFn: () => selectedDisasterId ? api.getDisasterOutcomes(selectedDisasterId) : api.getOutcomes(),
        retry: false,
        enabled: activeTab === 'outcomes',
    })

    const generateMutation = useMutation({
        mutationFn: (config: any) => api.generateSitrep(config),
        onMutate: () => {
            setIsRefreshing(true)
            setIsStreaming(true)
            setStreamingOutput('')
        },
        onSuccess: async (data) => {
            // Simulate streaming output
            const output = data?.markdown_body || data?.summary || 'Report generated successfully'
            for (let i = 0; i <= output.length; i += 20) {
                setStreamingOutput(output.slice(0, i))
                await new Promise(r => setTimeout(r, 30))
            }
            setStreamingOutput(output)
            setIsStreaming(false)
            await Promise.all([
                qc.invalidateQueries({ queryKey: ['latest-sitrep'] }),
                qc.invalidateQueries({ queryKey: ['sitreps'] })
            ])
            setIsRefreshing(false)
        },
        onError: () => {
            setIsRefreshing(false)
            setIsStreaming(false)
        }
    })

    const askMutation = useMutation({
        mutationFn: (q: string) => {
            const context = conversationHistory.slice(-5).map(item => ({
                question: item.question,
                answer: item.answer
            }))
            // Include disaster context in query if a disaster is selected
            const queryWithContext = selectedDisasterId 
                ? `[Disaster ID: ${selectedDisasterId}] ${q}`
                : q
            return api.askCoordinatorQuery(queryWithContext, undefined, undefined, context)
        },
        onSuccess: (data, queryText) => {
            const answer = (data as any)?.answer || (data as any)?.response || 'No response available'
            setConversationHistory(prev => {
                const newHistory = [...prev, {
                    question: queryText,
                    answer: answer,
                    timestamp: new Date()
                }]
                return newHistory.slice(-5)
            })
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
        { id: 'hotspots', label: 'Hotspots', icon: MapPin },
        { id: 'forecast', label: 'Severity Forecast', icon: Activity },
        { id: 'spread', label: 'Spread Map', icon: FlaskConical },
        { id: 'query', label: 'AI Query', icon: MessageSquare },
        { id: 'history', label: 'Query History', icon: Clock },
    ] as const

    const [isRefreshing, setIsRefreshing] = useState(false)
    const visibleTabs = tabs.slice(0, 6)
    const hiddenTabs = tabs.slice(6)

    const toggleSection = (section: string) => {
        setGenerateConfig(prev => ({
            ...prev,
            sections: prev.sections.includes(section)
                ? prev.sections.filter(s => s !== section)
                : [...prev.sections, section]
        }))
    }

    const lastDisaster = Array.isArray(disasters) ? disasters[0] : null
    const timeSince = lastDisaster?.created_at 
        ? Math.floor((Date.now() - new Date(lastDisaster.created_at).getTime()) / (1000 * 60 * 60))
        : null

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Brain className="w-6 h-6 text-purple-500" />
                        AI Coordinator
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        LLM-powered situation awareness, natural language queries & automated reports
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {/* Disaster Filter Dropdown */}
                    <div className="relative">
                        <button
                            onClick={() => setShowDisasterFilter(!showDisasterFilter)}
                            className={cn(
                                "flex items-center gap-2 px-3 py-2 rounded-xl border text-sm font-medium transition-all",
                                selectedDisasterId
                                    ? "bg-purple-50 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20 text-purple-700 dark:text-purple-400"
                                    : "bg-white dark:bg-slate-800 border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-white/20"
                            )}
                        >
                            {selectedDisasterId ? <Filter className="w-4 h-4" /> : <Globe className="w-4 h-4" />}
                            <span className="hidden sm:inline">{selectedDisasterId ? 'Filtered' : 'All Disasters'}</span>
                            <ChevronDown className={cn("w-3 h-3 transition-transform", showDisasterFilter && "rotate-180")} />
                        </button>
                        {showDisasterFilter && (
                            <>
                                <div className="fixed inset-0 z-10" onClick={() => setShowDisasterFilter(false)} />
                                <div className="absolute right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-xl z-20 py-1 min-w-[250px] max-h-[300px] overflow-y-auto">
                                    <button
                                        onClick={() => { setSelectedDisasterId(null); setShowDisasterFilter(false) }}
                                        className={cn(
                                            "flex items-center gap-2 w-full px-4 py-2 text-sm text-left transition-colors",
                                            !selectedDisasterId
                                                ? "bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400"
                                                : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                                        )}
                                    >
                                        <Globe className="w-4 h-4" />
                                        All Disasters
                                    </button>
                                    {Array.isArray(disasterList) && disasterList.map((d: any) => (
                                        <button
                                            key={d.id}
                                            onClick={() => { setSelectedDisasterId(d.id); setShowDisasterFilter(false) }}
                                            className={cn(
                                                "flex items-center gap-2 w-full px-4 py-2 text-sm text-left transition-colors",
                                                selectedDisasterId === d.id
                                                    ? "bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400"
                                                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                                            )}
                                        >
                                            <div className={cn(
                                                "w-2 h-2 rounded-full shrink-0",
                                                d.severity === 'critical' ? 'bg-red-500' :
                                                d.severity === 'high' ? 'bg-orange-500' :
                                                d.severity === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                                            )} />
                                            <div className="flex-1 min-w-0">
                                                <p className="font-medium truncate">{d.title || d.type}</p>
                                                <p className="text-xs text-slate-400 truncate">{d.location_name || 'Unknown location'}</p>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                    <button
                        onClick={() => setShowGeneratePanel(true)}
                        disabled={generateMutation.isPending || isRefreshing}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-purple-600/20"
                    >
                        {generateMutation.isPending || isRefreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                        {generateMutation.isPending || isRefreshing ? 'Generating...' : 'Generate SitRep'}
                    </button>
                    <ScheduleSitrepButton />
                </div>
            </div>

            {/* Tabs with overflow handling */}
            <div className="relative">
                <div className="overflow-x-auto -mx-1 px-1 pb-1 scrollbar-hide">
                    <div className="flex gap-1 bg-slate-100 dark:bg-white/5 p-1 rounded-xl w-max min-w-full sm:w-fit">
                        {visibleTabs.map((tab) => {
                            const Icon = tab.icon
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={cn(
                                        'flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap',
                                        activeTab === tab.id
                                            ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm'
                                            : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                                    )}
                                >
                                    <Icon className="w-4 h-4 shrink-0" />
                                    <span className="hidden sm:inline">{tab.label}</span>
                                    <span className="sm:hidden">{tab.label.split(' ')[0]}</span>
                                </button>
                            )
                        })}
                        {hiddenTabs.length > 0 && (
                            <button
                                onClick={() => setShowMoreTabs(!showMoreTabs)}
                                className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs sm:text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            >
                                <span>More</span>
                                <span className="px-1.5 py-0.5 rounded-full bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-400 text-[10px] font-bold">
                                    {hiddenTabs.length}
                                </span>
                                <ChevronDown className={cn("w-3 h-3 transition-transform", showMoreTabs && "rotate-180")} />
                            </button>
                        )}
                    </div>
                </div>
                {/* Fade gradient */}
                <div className="absolute right-0 top-0 bottom-1 w-8 bg-gradient-to-l from-slate-50 dark:from-slate-950 pointer-events-none" />
                
                {/* More Tabs Dropdown - positioned outside scroll container */}
                {showMoreTabs && hiddenTabs.length > 0 && (
                    <>
                        <div className="fixed inset-0 z-10" onClick={() => setShowMoreTabs(false)} />
                        <div className="absolute right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-xl z-20 py-1 min-w-[180px]">
                            {hiddenTabs.map((tab) => {
                                const Icon = tab.icon
                                return (
                                    <button
                                        key={tab.id}
                                        onClick={() => { setActiveTab(tab.id); setShowMoreTabs(false) }}
                                        className={cn(
                                            'flex items-center gap-2 w-full px-4 py-2 text-sm text-left transition-colors',
                                            activeTab === tab.id
                                                ? 'bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400'
                                                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5'
                                        )}
                                    >
                                        <Icon className="w-4 h-4" />
                                        {tab.label}
                                    </button>
                                )
                            })}
                        </div>
                    </>
                )}
            </div>

            {/* Generate SitRep Slide-over Panel */}
            {showGeneratePanel && (
                <div className="fixed inset-0 z-50 flex justify-end">
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowGeneratePanel(false)} />
                    <div className="relative w-full max-w-lg bg-white dark:bg-slate-900 shadow-2xl h-full overflow-y-auto">
                        <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-white/10 p-4 flex items-center justify-between z-10">
                            <h3 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <Sparkles className="w-5 h-5 text-purple-500" />
                                Generate Situation Report
                            </h3>
                            <button onClick={() => setShowGeneratePanel(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                <X className="w-5 h-5 text-slate-500" />
                            </button>
                        </div>
                        
                        <div className="p-6 space-y-6">
                            {/* Report Type */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                    Report Type
                                </label>
                                <div className="grid grid-cols-3 gap-2">
                                    {['daily', 'incident', 'custom'].map(type => (
                                        <button
                                            key={type}
                                            onClick={() => setGenerateConfig(prev => ({ ...prev, report_type: type }))}
                                            className={cn(
                                                'px-3 py-2 rounded-lg text-sm font-medium border transition-all capitalize',
                                                generateConfig.report_type === type
                                                    ? 'bg-purple-600 text-white border-purple-600'
                                                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-white/10 hover:border-purple-300'
                                            )}
                                        >
                                            {type}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Date Range */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                    Date Range
                                </label>
                                <select
                                    value={generateConfig.date_range}
                                    onChange={(e) => setGenerateConfig(prev => ({ ...prev, date_range: e.target.value }))}
                                    className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
                                >
                                    <option value="24h">Last 24 hours</option>
                                    <option value="7d">Last 7 days</option>
                                    <option value="14d">Last 14 days</option>
                                    <option value="30d">Last 30 days</option>
                                </select>
                            </div>

                            {/* Include Sections */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                    Include Sections
                                </label>
                                <div className="space-y-2">
                                    {[
                                        { id: 'executive_summary', label: 'Executive Summary' },
                                        { id: 'resource_status', label: 'Resource Status' },
                                        { id: 'active_incidents', label: 'Active Incidents' },
                                        { id: 'recommendations', label: 'Recommendations' }
                                    ].map(section => (
                                        <label key={section.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={generateConfig.sections.includes(section.id)}
                                                onChange={() => toggleSection(section.id)}
                                                className="w-4 h-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                                            />
                                            <span className="text-sm text-slate-700 dark:text-slate-300">{section.label}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            {/* Streaming Output Preview */}
                            {(isStreaming || streamingOutput) && (
                                <div className="rounded-xl border border-purple-200 dark:border-purple-500/20 bg-purple-50/50 dark:bg-purple-500/5 p-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        {isStreaming && <Loader2 className="w-4 h-4 animate-spin text-purple-500" />}
                                        <span className="text-xs font-medium text-purple-700 dark:text-purple-400">
                                            {isStreaming ? 'Generating report...' : 'Preview'}
                                        </span>
                                    </div>
                                    <div className="text-sm text-slate-600 dark:text-slate-400 max-h-48 overflow-y-auto">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                            {streamingOutput}
                                        </ReactMarkdown>
                                    </div>
                                </div>
                            )}

                            {/* Generate Button */}
                            <button
                                onClick={() => generateMutation.mutate(generateConfig)}
                                disabled={generateMutation.isPending || isStreaming}
                                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-purple-600/20"
                            >
                                {generateMutation.isPending || isStreaming ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Sparkles className="w-5 h-5" />
                                )}
                                {generateMutation.isPending || isStreaming ? 'Generating...' : 'Generate Report'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SitRep Tab */}
            {activeTab === 'sitrep' && (
                <div className="space-y-4">
                    {sitrepLoading ? (
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-12 text-center">
                            <Loader2 className="w-8 h-8 animate-spin text-purple-500 mx-auto mb-3" />
                            <p className="text-sm text-slate-500">Loading situation reports...</p>
                        </div>
                    ) : (selectedSitrep || latestSitrep) ? (() => {
                        const displaySitrep = selectedSitrep || latestSitrep;
                        return (
                        <div className="space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    {selectedSitrep && (
                                        <button onClick={() => setSelectedSitrep(null)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 text-slate-500" title="Back to latest">
                                            ←
                                        </button>
                                    )}
                                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                                        {selectedSitrep ? 'Historical Report' : 'Active Intelligence Report'}
                                    </h3>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button 
                                        onClick={() => window.print()}
                                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors text-slate-500" 
                                        title="Print Report"
                                    >
                                        <Printer className="w-4 h-4" />
                                    </button>
                                    <button 
                                        onClick={() => {
                                            const blob = new Blob([displaySitrep.markdown_body || displaySitrep.summary || displaySitrep.content || 'No content'], { type: 'text/markdown' });
                                            const url = URL.createObjectURL(blob);
                                            const a = document.createElement('a');
                                            a.href = url;
                                            a.download = `sitrep-${displaySitrep.id || 'report'}.md`;
                                            document.body.appendChild(a);
                                            a.click();
                                            document.body.removeChild(a);
                                            URL.revokeObjectURL(url);
                                        }}
                                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors text-slate-500" 
                                        title="Download Markdown"
                                    >
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
                                                {displaySitrep.title || 'Situation Report'}
                                            </h2>
                                            <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">
                                                Operational Assessment · {displaySitrep.report_type?.toUpperCase()}
                                            </p>
                                        </div>
                                        <div className="text-right flex flex-col items-end">
                                            <div className="text-2xl font-bold text-slate-900 dark:text-white tabular-nums">
                                                {displaySitrep.created_at ? new Date(displaySitrep.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
                                            </div>
                                            <p className="text-xs text-slate-400 uppercase tracking-widest font-bold">
                                                Timestamp: {displaySitrep.created_at ? new Date(displaySitrep.created_at).toLocaleTimeString() : 'N/A'}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Metrics Grid inside report */}
                                    {displaySitrep.key_metrics ? (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
                                            {[
                                                { label: 'Intelligence', value: displaySitrep.key_metrics.active_disasters, color: 'text-red-600' },
                                                { label: 'Utilization', value: `${displaySitrep.key_metrics.resource_utilization_pct}%`, color: 'text-blue-600' },
                                                { label: 'Requests', value: displaySitrep.key_metrics.total_open_requests, color: 'text-amber-600' },
                                                { label: 'Anomalies', value: displaySitrep.key_metrics.active_anomalies, color: 'text-purple-600' }
                                            ].map((stat, idx) => (
                                                <div key={idx} className="p-4 rounded-xl bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5">
                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{stat.label}</p>
                                                    <p className={cn("text-xl font-black", stat.color)}>{stat.value}</p>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-3 mb-12 p-6 rounded-2xl bg-slate-50 dark:bg-white/5 border border-dashed border-slate-200 dark:border-white/10">
                                            <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
                                            <span className="text-sm font-medium text-slate-500 italic">Analyzing intelligence metrics...</span>
                                        </div>
                                    )}

                                    <div className="max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                            {(displaySitrep.markdown_body || displaySitrep.summary || displaySitrep.content || 'No content available.')
                                                .replace(/^#\s+.*?\n/i, '')
                                                .trim()}
                                        </ReactMarkdown>
                                    </div>

                                    <div className="mt-12 pt-8 border-t border-slate-100 dark:border-white/5 flex items-center justify-between opacity-50 italic text-xs">
                                        <p>Verification Hash: {displaySitrep.id?.slice(-8)?.toUpperCase() || 'N/A'}</p>
                                        <p>© HopeInChaos SitRep Engine v2.0</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        );
                    })() : (
                        /* Empty State - Quick Start Cards */
                        <div className="space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                {/* Last Disaster Context Card */}
                                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                                            <Zap className="w-4 h-4 text-red-600 dark:text-red-400" />
                                        </div>
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Latest Disaster</h3>
                                    </div>
                                    {lastDisaster ? (
                                        <div className="space-y-2">
                                            <p className="text-lg font-bold text-slate-900 dark:text-white capitalize">{lastDisaster.type || 'Unknown'}</p>
                                            <p className="text-sm text-slate-500 flex items-center gap-1">
                                                <MapPin className="w-3 h-3" />
                                                {lastDisaster.location_name || 'Location pending'}
                                            </p>
                                            {timeSince !== null && (
                                                <p className="text-xs text-slate-400 flex items-center gap-1">
                                                    <Clock className="w-3 h-3" />
                                                    {timeSince}h ago
                                                </p>
                                            )}
                                            <span className={cn(
                                                "inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                                                lastDisaster.severity === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400' :
                                                lastDisaster.severity === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' :
                                                'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                                            )}>
                                                {lastDisaster.severity || 'medium'}
                                            </span>
                                        </div>
                                    ) : (
                                        <p className="text-sm text-slate-500">No active disasters</p>
                                    )}
                                </div>

                                {/* Suggested Report Type Card */}
                                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                            <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Suggested Report</h3>
                                    </div>
                                    <div className="space-y-2">
                                        <button
                                            onClick={() => { setGenerateConfig(prev => ({ ...prev, report_type: 'daily' })); setShowGeneratePanel(true) }}
                                            className="w-full text-left p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                                        >
                                            <p className="text-sm font-medium text-slate-900 dark:text-white">Daily Summary</p>
                                            <p className="text-xs text-slate-500">24h operational overview</p>
                                        </button>
                                        <button
                                            onClick={() => { setGenerateConfig(prev => ({ ...prev, report_type: 'incident' })); setShowGeneratePanel(true) }}
                                            className="w-full text-left p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                                        >
                                            <p className="text-sm font-medium text-slate-900 dark:text-white">Incident Report</p>
                                            <p className="text-xs text-slate-500">Focused on specific event</p>
                                        </button>
                                        <button
                                            onClick={() => { setGenerateConfig(prev => ({ ...prev, report_type: 'custom' })); setShowGeneratePanel(true) }}
                                            className="w-full text-left p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                                        >
                                            <p className="text-sm font-medium text-slate-900 dark:text-white">Custom Report</p>
                                            <p className="text-xs text-slate-500">Tailored analysis</p>
                                        </button>
                                    </div>
                                </div>

                                {/* Estimated Generation Time Card */}
                                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                            <Timer className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                        </div>
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Generation Time</h3>
                                    </div>
                                    <div className="space-y-3">
                                        <div>
                                            <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">~15s</p>
                                            <p className="text-xs text-slate-500">Estimated for daily report</p>
                                        </div>
                                        <div className="pt-2 border-t border-slate-100 dark:border-white/5">
                                            <p className="text-xs text-slate-500 flex items-center gap-1">
                                                <TrendingUp className="w-3 h-3 text-green-500" />
                                                AI model: {mlHealth?.model || 'GPT-4'}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Primary CTA */}
                            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                                <button
                                    onClick={() => setShowGeneratePanel(true)}
                                    className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium hover:opacity-90 shadow-lg shadow-purple-600/20"
                                >
                                    <Sparkles className="w-5 h-5" />
                                    Generate SitRep
                                </button>
                                <button
                                    onClick={() => setShowGeneratePanel(true)}
                                    className="flex items-center gap-2 px-4 py-2 text-sm text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300"
                                >
                                    <Eye className="w-4 h-4" />
                                    View Template
                                </button>
                            </div>

                            {/* Schedule automated reports prompt */}
                            <div className="rounded-xl border border-dashed border-slate-300 dark:border-white/10 bg-slate-50/50 dark:bg-white/[0.02] p-4 text-center">
                                <p className="text-sm text-slate-600 dark:text-slate-400">
                                    <Calendar className="w-4 h-4 inline mr-1" />
                                    Schedule automated reports to be generated daily
                                </p>
                                <button className="mt-2 text-sm font-medium text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300">
                                    Configure Schedule →
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Historical sitreps - Timeline List */}
                    {Array.isArray(sitreps) && sitreps.length > 0 && (
                        <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Report Timeline</h3>
                            <div className="space-y-3">
                                {sitreps.slice(0, 10).map((s: any, i: number) => {
                                    const typeStyle = REPORT_TYPE_COLORS[s.report_type] || REPORT_TYPE_COLORS.custom
                                    const severity = s.key_metrics?.active_anomalies > 5 ? 'critical' : s.key_metrics?.active_anomalies > 2 ? 'high' : 'medium'
                                    return (
                                        <div
                                            key={s.id || i}
                                            className={cn(
                                                'rounded-xl border transition-colors overflow-hidden',
                                                selectedSitrep?.id === s.id
                                                    ? 'border-purple-200 dark:border-purple-500/20 bg-purple-50/50 dark:bg-purple-500/5'
                                                    : 'border-slate-100 dark:border-white/5 hover:border-slate-200 dark:hover:border-white/10'
                                            )}
                                        >
                                            <div className="p-4">
                                                <div className="flex items-start justify-between gap-4">
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2 mb-1">
                                                            {/* Report Type Badge */}
                                                            <span className={cn(
                                                                "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                                                                typeStyle.bg, typeStyle.text
                                                            )}>
                                                                {s.report_type || 'custom'}
                                                            </span>
                                                            {/* Severity Pills */}
                                                            {s.key_metrics && (
                                                                <div className="flex items-center gap-1">
                                                                    {s.key_metrics.active_disasters > 0 && (
                                                                        <span className="w-2 h-2 rounded-full bg-red-500" title="Active Disasters" />
                                                                    )}
                                                                    {s.key_metrics.active_anomalies > 0 && (
                                                                        <span className="w-2 h-2 rounded-full bg-orange-500" title="Anomalies" />
                                                                    )}
                                                                    {s.key_metrics.total_open_requests > 10 && (
                                                                        <span className="w-2 h-2 rounded-full bg-yellow-500" title="High Requests" />
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <h4 className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                                                            {s.title || `SitRep #${sitreps.length - i}`}
                                                        </h4>
                                                        {/* Summary Excerpt */}
                                                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                                                            {(s.markdown_body || s.summary || '').slice(0, 120)}...
                                                        </p>
                                                        {/* Metadata */}
                                                        <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-400">
                                                            <span className="flex items-center gap-1">
                                                                <Calendar className="w-3 h-3" />
                                                                {s.created_at ? new Date(s.created_at).toLocaleDateString() : 'Unknown'}
                                                            </span>
                                                            <span className="flex items-center gap-1">
                                                                <Clock className="w-3 h-3" />
                                                                {s.created_at ? new Date(s.created_at).toLocaleTimeString() : ''}
                                                            </span>
                                                            {s.ai_model && (
                                                                <span className="flex items-center gap-1">
                                                                    <Brain className="w-3 h-3" />
                                                                    {s.ai_model}
                                                                </span>
                                                            )}
                                                            {s.generation_time_ms && (
                                                                <span className="flex items-center gap-1">
                                                                    <Zap className="w-3 h-3" />
                                                                    {s.generation_time_ms}ms
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {/* Action Buttons */}
                                                    <div className="flex items-center gap-1 shrink-0">
                                                        <button
                                                            onClick={async () => {
                                                                try {
                                                                    if (s.id) {
                                                                        const fullReport = await api.getSitrep(s.id);
                                                                        setSelectedSitrep(fullReport);
                                                                    } else {
                                                                        setSelectedSitrep(s);
                                                                    }
                                                                } catch {
                                                                    setSelectedSitrep(s);
                                                                }
                                                            }}
                                                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 text-slate-500 transition-colors"
                                                            title="View"
                                                        >
                                                            <Eye className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => {
                                                                const blob = new Blob([s.markdown_body || s.summary || ''], { type: 'text/markdown' });
                                                                const url = URL.createObjectURL(blob);
                                                                const a = document.createElement('a');
                                                                a.href = url;
                                                                a.download = `sitrep-${s.id || 'report'}.md`;
                                                                document.body.appendChild(a);
                                                                a.click();
                                                                document.body.removeChild(a);
                                                                URL.revokeObjectURL(url);
                                                            }}
                                                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 text-slate-500 transition-colors"
                                                            title="Download PDF"
                                                        >
                                                            <Download className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => generateMutation.mutate({ report_type: s.report_type || 'daily' })}
                                                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 text-slate-500 transition-colors"
                                                            title="Re-generate"
                                                        >
                                                            <RotateCcw className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Outcomes Tab */}
            {activeTab === 'outcomes' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <ErrorBoundary>
                        <OutcomeTrackingPanel />
                    </ErrorBoundary>
                </div>
            )}

            {/* ML Sandbox Tab */}
            {activeTab === 'ml_sandbox' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <ErrorBoundary>
                        <MLDashboard />
                    </ErrorBoundary>
                </div>
            )}

            {/* Anomalies Tab */}
            {activeTab === 'anomalies' && (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                    <ErrorBoundary>
                        <AnomalyAlertPanel />
                    </ErrorBoundary>
                </div>
            )}

            {/* Query Tab */}
            {activeTab === 'query' && (
                <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                        <div className="flex items-center justify-between mb-4">
                            <div>
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white">AI Coordinator Chat</h3>
                                <p className="text-xs text-slate-500">Ask natural language questions about disasters, resources, predictions, and operational status.</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-slate-400">Memory: {conversationHistory.length}/5 Q&A pairs</span>
                                <button
                                    onClick={() => setConversationHistory([])}
                                    className="px-3 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                                >
                                    Clear Memory
                                </button>
                            </div>
                        </div>

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

                        {/* Chat Thread */}
                        {conversationHistory.length > 0 && (
                            <div className="mb-4 max-h-96 overflow-y-auto border border-slate-100 dark:border-white/5 rounded-xl bg-slate-50/30 dark:bg-white/[0.02]">
                                {conversationHistory.map((item, index) => (
                                    <div key={index} className="border-b border-slate-100 dark:border-white/5 last:border-0">
                                        {/* User Question */}
                                        <div className="p-4 bg-white dark:bg-slate-900/50">
                                            <div className="flex items-center gap-2 mb-1">
                                                <div className="w-6 h-6 rounded-full bg-purple-100 dark:bg-purple-500/20 flex items-center justify-center">
                                                    <MessageSquare className="w-3 h-3 text-purple-600 dark:text-purple-400" />
                                                </div>
                                                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">You</span>
                                                <span className="text-[10px] text-slate-400 ml-auto">
                                                    {item.timestamp.toLocaleTimeString()}
                                                </span>
                                            </div>
                                            <p className="text-sm text-slate-700 dark:text-slate-300">{item.question}</p>
                                        </div>
                                        
                                        {/* AI Response */}
                                        <div className="p-4 bg-slate-50/50 dark:bg-white/[0.02]">
                                            <div className="flex items-center gap-2 mb-1">
                                                <div className="w-6 h-6 rounded-full bg-purple-100 dark:bg-purple-500/20 flex items-center justify-center">
                                                    <Sparkles className="w-3 h-3 text-purple-600 dark:text-purple-400" />
                                                </div>
                                                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">AI Coordinator</span>
                                                <span className="text-[10px] text-slate-400 ml-auto">
                                                    {item.timestamp.toLocaleTimeString()}
                                                </span>
                                            </div>
                                            <div className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed prose prose-sm prose-slate dark:prose-invert max-w-none prose-headings:text-slate-800 dark:prose-headings:text-white prose-strong:text-slate-800 dark:prose-strong:text-white prose-p:my-1">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                                    {item.answer}
                                                </ReactMarkdown>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Input Area */}
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
                                Send
                            </button>
                        </div>

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
                                    <div 
                                        className="px-4 py-3 bg-slate-50/50 dark:bg-white/[0.02] border-b border-slate-100 dark:border-white/5 cursor-pointer"
                                        onClick={() => {
                                            setQuery(entry.query_text || entry.query || entry.question);
                                            setActiveTab('query');
                                        }}
                                    >
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
                                    <div 
                                        onClick={() => {
                                            setQuery(entry.query_text || entry.query || entry.question);
                                            setActiveTab('query');
                                            askMutation.mutate(entry.query_text || entry.query || entry.question);
                                        }}
                                        className="px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-white/[0.01] transition-colors"
                                    >
                                        <div className="text-xs text-slate-600 dark:text-slate-300 max-w-none pointer-events-none">
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


            {/* Hotspots Tab */}
            {activeTab === 'hotspots' && (
                <ErrorBoundary>
                    <HotspotPanel selectedDisasterId={null} />
                </ErrorBoundary>
            )}

            {/* Severity Forecast Tab */}
            {activeTab === 'forecast' && (
                <div className="space-y-4">
                    <ErrorBoundary>
                        <TFTForecastWidget />
                    </ErrorBoundary>
                </div>
            )}

            {/* Spread Map Tab */}
            {activeTab === 'spread' && (
                <div className="space-y-4">
                    <ErrorBoundary>
                        <PINNHeatmap />
                    </ErrorBoundary>
                </div>
            )}
        </div>
    )
}