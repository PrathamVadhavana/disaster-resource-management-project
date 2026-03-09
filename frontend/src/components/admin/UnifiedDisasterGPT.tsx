'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { api } from '@/lib/api'
import {
    Brain, Loader2, Send, Sparkles, Zap, Network, Users,
    ChevronDown, AlertTriangle, TrendingDown, TrendingUp, ArrowRight,
    BookOpen, BarChart3, Target, Lightbulb, Trash2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── Markdown components ────────────────────────────────────────────────────

const mdComponents = {
    table: (props: any) => (
        <div className="overflow-x-auto my-3 rounded-xl border border-slate-200 dark:border-white/10">
            <table className="w-full text-sm" {...props} />
        </div>
    ),
    thead: (props: any) => <thead className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-500/10 dark:to-indigo-500/10" {...props} />,
    th: (props: any) => <th className="px-3 py-2 text-left text-xs font-bold text-purple-700 dark:text-purple-400 uppercase tracking-wider border-b border-slate-200 dark:border-white/10" {...props} />,
    td: (props: any) => <td className="px-3 py-2 text-sm text-slate-700 dark:text-slate-300 border-b border-slate-100 dark:border-white/5" {...props} />,
    tr: (props: any) => <tr className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02] transition-colors" {...props} />,
    h1: (props: any) => <h1 className="text-xl font-black text-slate-900 dark:text-white border-b border-slate-200 dark:border-white/10 pb-2 mb-4 mt-1" {...props} />,
    h2: (props: any) => <h2 className="text-lg font-bold text-purple-700 dark:text-purple-400 mt-5 mb-2 pb-1 border-b border-purple-100 dark:border-purple-500/10" {...props} />,
    h3: (props: any) => <h3 className="text-base font-semibold text-slate-800 dark:text-white mt-4 mb-1" {...props} />,
    strong: (props: any) => <strong className="font-semibold text-slate-900 dark:text-white" {...props} />,
    ul: (props: any) => <ul className="list-disc pl-5 my-2 space-y-1" {...props} />,
    ol: (props: any) => <ol className="list-decimal pl-5 my-2 space-y-1" {...props} />,
    li: (props: any) => <li className="text-slate-600 dark:text-slate-300 text-sm" {...props} />,
    p: (props: any) => <p className="text-slate-600 dark:text-slate-300 leading-relaxed my-1.5 text-sm" {...props} />,
    hr: () => <hr className="my-4 border-slate-200 dark:border-white/10" />,
    blockquote: (props: any) => <blockquote className="border-l-4 border-purple-300 dark:border-purple-500/30 pl-3 my-3 italic text-slate-500 dark:text-slate-400" {...props} />,
    code: ({ children, className, ...props }: any) => {
        const isInline = !className
        return isInline
            ? <code className="px-1 py-0.5 rounded bg-slate-100 dark:bg-white/10 text-xs font-mono text-purple-700 dark:text-purple-300" {...props}>{children}</code>
            : <code className={cn("block p-3 rounded-lg bg-slate-900 dark:bg-black/50 text-xs font-mono text-green-400 overflow-x-auto", className)} {...props}>{children}</code>
    },
}

// ── Types ──────────────────────────────────────────────────────────────────

type MessageRole = 'user' | 'assistant'
type AIMode = 'rag' | 'multi_agent' | 'causal'

interface CausalEffect {
    treatment: string
    outcome: string
    ate: number
    p_value?: number
    confidence_interval?: number[]
}

interface CausalIntervention {
    variable: string
    current_value: number
    proposed_value: number
    estimated_reduction: number
    explanation: string
}

interface AgentResult {
    agent: string
    data: any
}

interface Message {
    id: string
    role: MessageRole
    content: string
    mode?: AIMode
    timestamp: Date
    sources?: any[]
    confidence?: number
    causalEffects?: CausalEffect[]
    causalRootCauses?: CausalEffect[]
    causalInterventions?: CausalIntervention[]
    causalGraph?: { nodes: string[]; edges: { source: string; target: string }[] }
    agentResults?: AgentResult[]
    isStreaming?: boolean
}

// ── Mode badge ─────────────────────────────────────────────────────────────

function ModeBadge({ mode }: { mode?: AIMode }) {
    if (!mode) return null
    const config = {
        rag: { label: 'RAG Pipeline', icon: Zap, color: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400' },
        multi_agent: { label: 'Multi-Agent', icon: Users, color: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400' },
        causal: { label: 'Causal AI', icon: Network, color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400' },
    }
    const c = config[mode]
    const Icon = c.icon
    return (
        <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider", c.color)}>
            <Icon className="w-3 h-3" />
            {c.label}
        </span>
    )
}

// ── Causal effects inline card ─────────────────────────────────────────────

function CausalEffectsCard({ effects }: { effects: CausalEffect[] }) {
    if (!effects?.length) return null
    return (
        <div className="my-3 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20">
            <div className="flex items-center gap-1.5 mb-2">
                <BarChart3 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Causal Effects</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {effects.map((e, i) => (
                    <div key={i} className="p-2.5 rounded-lg bg-white dark:bg-white/5 border border-emerald-100 dark:border-emerald-500/10">
                        <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider mb-0.5">{e.treatment} → {e.outcome}</p>
                        <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{e.ate?.toFixed(4)}</p>
                        {e.p_value !== undefined && (
                            <p className="text-[10px] text-slate-400 mt-0.5">
                                p={e.p_value?.toFixed(4)} {e.p_value < 0.05 ? '✓ significant' : '— not significant'}
                            </p>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

// ── Causal interventions card ──────────────────────────────────────────────

function CausalInterventionsCard({ interventions }: { interventions: CausalIntervention[] }) {
    if (!interventions?.length) return null
    return (
        <div className="my-3 p-3 rounded-xl bg-blue-50 dark:bg-blue-500/5 border border-blue-200 dark:border-blue-500/20">
            <div className="flex items-center gap-1.5 mb-2">
                <Lightbulb className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                <span className="text-[10px] font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider">Recommended Interventions</span>
            </div>
            <div className="space-y-2">
                {interventions.map((iv, i) => (
                    <div key={i} className="p-2.5 rounded-lg bg-white dark:bg-white/5 border border-blue-100 dark:border-blue-500/10 flex items-center gap-3">
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
                                <span>{iv.variable}</span>
                                <span className="text-slate-400">{iv.current_value}</span>
                                <ArrowRight className="w-3 h-3 text-blue-400" />
                                <span className="text-blue-600 dark:text-blue-400">{iv.proposed_value}</span>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-0.5 truncate">{iv.explanation}</p>
                        </div>
                        <div className="text-right shrink-0">
                            <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                                <TrendingDown className="w-3.5 h-3.5" />
                                <span className="text-sm font-bold">-{iv.estimated_reduction}</span>
                            </div>
                            <p className="text-[9px] text-slate-400">est. reduction</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

// ── Root causes card ───────────────────────────────────────────────────────

function RootCausesCard({ causes }: { causes: CausalEffect[] }) {
    if (!causes?.length) return null
    return (
        <div className="my-3 p-3 rounded-xl bg-orange-50 dark:bg-orange-500/5 border border-orange-200 dark:border-orange-500/20">
            <div className="flex items-center gap-1.5 mb-2">
                <Target className="w-3.5 h-3.5 text-orange-600 dark:text-orange-400" />
                <span className="text-[10px] font-bold text-orange-700 dark:text-orange-400 uppercase tracking-wider">Root Causes (by impact)</span>
            </div>
            <div className="space-y-1.5">
                {causes.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-white dark:bg-white/5">
                        <div className="w-5 h-5 rounded-full bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center text-[10px] font-bold text-orange-600 dark:text-orange-400">
                            {i + 1}
                        </div>
                        <span className="text-xs font-medium text-slate-700 dark:text-slate-300 flex-1">{c.treatment}</span>
                        <span className={cn(
                            "text-xs font-bold",
                            c.ate > 0 ? "text-red-500" : "text-green-500"
                        )}>
                            {c.ate > 0 ? <TrendingUp className="w-3 h-3 inline mr-0.5" /> : <TrendingDown className="w-3 h-3 inline mr-0.5" />}
                            {Math.abs(c.ate).toFixed(4)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    )
}

// ── Agent activity card ────────────────────────────────────────────────────

function formatAgentData(agent: string, data: any): string {
    if (!data || typeof data !== 'object') return String(data || 'No data')
    if (data.summary) return data.summary
    if (data.response) return data.response
    switch (agent) {
        case 'predictor': {
            const sev = data.predicted_severity || 'unknown'
            const conf = data.confidence != null ? `${(data.confidence * 100).toFixed(0)}%` : 'N/A'
            const timeline = data.timeline_hours || 'N/A'
            const method = data.method || 'unknown'
            const affected = data.estimated_affected ? data.estimated_affected.toLocaleString() : null
            return `Severity: **${sev}** (confidence: ${conf}). Timeline: ${timeline}h. Method: ${method}.${affected ? ` Est. affected: ${affected}.` : ''}`
        }
        case 'allocator': {
            if (data.allocations?.length) {
                return `${data.allocations.length} resources allocated with ${data.coverage_pct || 0}% coverage.`
            }
            if (data.recommended_resources?.length) {
                const recs = data.recommended_resources.map((r: any) => `${r.type} (priority ${r.priority})`).join(', ')
                return `Urgency: **${data.recommended_urgency || '?'}/10**. Resources: ${recs}.`
            }
            return 'Allocation analysis completed.'
        }
        case 'analyst': {
            const analyses = data.analyses || {}
            const parts: string[] = []
            const nlp = analyses.nlp
            if (nlp) {
                parts.push(`Intent: **${nlp.query_intent || 'unknown'}**.`)
                if (nlp.key_entities?.length) parts.push(`Entities: ${nlp.key_entities.join(', ')}.`)
                const urg = nlp.urgency_signals
                if (urg?.is_urgent) parts.push(`⚠️ Urgent: ${urg.signals?.join(', ')}.`)
                else parts.push('No urgency signals detected.')
            }
            const causal = analyses.causal
            if (causal?.insight) parts.push(causal.insight + '.')
            return parts.length > 0 ? parts.join(' ') : 'Analysis completed.'
        }
        case 'responder':
            return data.response || 'Generating response...'
        default:
            return data.summary || data.response || JSON.stringify(data).slice(0, 200)
    }
}

function AgentResultsCard({ results }: { results: AgentResult[] }) {
    if (!results?.length) return null
    const agentIcons: Record<string, string> = {
        predictor: '🔮',
        allocator: '📦',
        analyst: '🔬',
        responder: '💬',
    }
    const agentLabels: Record<string, string> = {
        predictor: 'Predictor',
        allocator: 'Allocator',
        analyst: 'Analyst',
        responder: 'Responder',
    }
    return (
        <div className="my-3 p-3 rounded-xl bg-indigo-50 dark:bg-indigo-500/5 border border-indigo-200 dark:border-indigo-500/20">
            <div className="flex items-center gap-1.5 mb-2">
                <Users className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                <span className="text-[10px] font-bold text-indigo-700 dark:text-indigo-400 uppercase tracking-wider">Agent Results</span>
            </div>
            <div className="space-y-2">
                {results.map((ar, i) => {
                    const summary = formatAgentData(ar.agent, ar.data)
                    return (
                        <div key={i} className="p-2.5 rounded-lg bg-white dark:bg-white/5 border border-indigo-100 dark:border-indigo-500/10">
                            <div className="flex items-center gap-1.5 mb-1">
                                <span>{agentIcons[ar.agent] || '🤖'}</span>
                                <span className="text-xs font-bold text-indigo-700 dark:text-indigo-400">{agentLabels[ar.agent] || ar.agent}</span>
                                {ar.data?.method && (
                                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-500/10 text-indigo-500 dark:text-indigo-400">
                                        {ar.data.method}
                                    </span>
                                )}
                            </div>
                            <div className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed prose prose-xs prose-slate dark:prose-invert max-w-none">
                                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{summary}</ReactMarkdown>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

// ── Sources card ───────────────────────────────────────────────────────────

function SourcesCard({ sources }: { sources: any[] }) {
    if (!sources?.length) return null
    return (
        <details className="my-3 group">
            <summary className="flex items-center gap-1.5 cursor-pointer text-[10px] font-bold text-slate-400 uppercase tracking-wider hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                <BookOpen className="w-3 h-3" />
                {sources.length} source{sources.length > 1 ? 's' : ''} retrieved
                <ChevronDown className="w-3 h-3 group-open:rotate-180 transition-transform" />
            </summary>
            <div className="mt-2 space-y-1.5">
                {sources.map((s: any, i: number) => (
                    <div key={i} className="p-2 rounded-lg bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5">
                        <div className="flex items-center justify-between mb-0.5">
                            <span className="text-[10px] font-semibold text-purple-600 dark:text-purple-400">{s.source || 'unknown'}</span>
                            <span className="text-[9px] text-slate-400">{s.type} · {(s.relevance * 100).toFixed(0)}% relevant</span>
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">{s.content_preview}</p>
                    </div>
                ))}
            </div>
        </details>
    )
}

// ── Suggested queries ──────────────────────────────────────────────────────

const SUGGESTED_QUERIES = [
    { text: 'What disasters need immediate attention?', mode: 'rag' as AIMode },
    { text: 'Coordinate emergency response for all active disasters', mode: 'multi_agent' as AIMode },
    { text: 'What are the root causes of casualties?', mode: 'causal' as AIMode },
    { text: 'Deploy resources to the most critical zones', mode: 'multi_agent' as AIMode },
    { text: 'What if response time was reduced by 50%?', mode: 'causal' as AIMode },
    { text: 'Summarize current resource allocation status', mode: 'rag' as AIMode },
    { text: 'Which interventions would reduce damage the most?', mode: 'causal' as AIMode },
    { text: 'Prioritize and triage all pending requests', mode: 'multi_agent' as AIMode },
]

// ── Main component ─────────────────────────────────────────────────────────

export default function UnifiedDisasterGPT() {
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState('')
    const [isStreaming, setIsStreaming] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    const scrollToBottom = useCallback(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [])

    useEffect(() => {
        scrollToBottom()
    }, [messages, scrollToBottom])

    const handleSubmit = useCallback(async (queryText?: string) => {
        const q = (queryText || input).trim()
        if (!q || isStreaming) return

        setInput('')

        // Add user message
        const userMsg: Message = {
            id: `user-${Date.now()}`,
            role: 'user',
            content: q,
            timestamp: new Date(),
        }

        // Create assistant message placeholder
        const assistantMsg: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            isStreaming: true,
            sources: [],
            agentResults: [],
        }

        setMessages(prev => [...prev, userMsg, assistantMsg])
        setIsStreaming(true)

        try {
            let mode: AIMode | undefined
            let textContent = ''
            let sources: any[] = []
            let confidence: number | undefined
            let causalEffects: CausalEffect[] = []
            let causalRootCauses: CausalEffect[] = []
            let causalInterventions: CausalIntervention[] = []
            let causalGraph: any = undefined
            let agentResults: AgentResult[] = []

            for await (const chunk of api.streamUnifiedQuery({ query: q })) {
                if (typeof chunk === 'string') {
                    textContent += chunk
                } else if (typeof chunk === 'object' && chunk !== null) {
                    const type = chunk.type

                    if (type === 'meta') {
                        mode = chunk.mode
                    } else if (type === 'sources') {
                        sources = chunk.data || []
                    } else if (type === 'token') {
                        textContent += chunk.data || ''
                    } else if (type === 'done') {
                        confidence = chunk.confidence
                    } else if (type === 'causal_data') {
                        if (chunk.subtype === 'effects') {
                            causalEffects = chunk.data || []
                        } else if (chunk.subtype === 'root_causes') {
                            causalRootCauses = chunk.data || []
                        } else if (chunk.subtype === 'interventions') {
                            causalInterventions = chunk.data || []
                        } else if (chunk.subtype === 'graph') {
                            causalGraph = chunk.data
                        }
                    } else if (type === 'agent_start') {
                        // show in-progress agent
                    } else if (type === 'agent_result') {
                        agentResults = [...agentResults, { agent: chunk.agent, data: chunk.data }]
                    } else if (type === 'agent_error') {
                        agentResults = [...agentResults, { agent: chunk.agent, data: { summary: `Error: ${chunk.error}` } }]
                    } else if (type === 'error') {
                        textContent += `\n\n**Error:** ${chunk.data || 'Unknown error'}`
                    }
                }

                // Update assistant message in real-time
                setMessages(prev => {
                    const updated = [...prev]
                    const lastIdx = updated.length - 1
                    if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                        updated[lastIdx] = {
                            ...updated[lastIdx],
                            content: textContent,
                            mode,
                            sources: sources.length > 0 ? sources : updated[lastIdx].sources,
                            confidence,
                            causalEffects: causalEffects.length > 0 ? causalEffects : updated[lastIdx].causalEffects,
                            causalRootCauses: causalRootCauses.length > 0 ? causalRootCauses : updated[lastIdx].causalRootCauses,
                            causalInterventions: causalInterventions.length > 0 ? causalInterventions : updated[lastIdx].causalInterventions,
                            causalGraph: causalGraph || updated[lastIdx].causalGraph,
                            agentResults: agentResults.length > 0 ? agentResults : updated[lastIdx].agentResults,
                            isStreaming: true,
                        }
                    }
                    return updated
                })
            }

            // Finalize
            setMessages(prev => {
                const updated = [...prev]
                const lastIdx = updated.length - 1
                if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = {
                        ...updated[lastIdx],
                        content: textContent || 'No response generated.',
                        isStreaming: false,
                    }
                }
                return updated
            })
        } catch (e: any) {
            setMessages(prev => {
                const updated = [...prev]
                const lastIdx = updated.length - 1
                if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = {
                        ...updated[lastIdx],
                        content: `**Error:** ${e.message || 'Failed to get response'}`,
                        isStreaming: false,
                    }
                }
                return updated
            })
        } finally {
            setIsStreaming(false)
            inputRef.current?.focus()
        }
    }, [input, isStreaming])

    const clearChat = useCallback(() => {
        setMessages([])
    }, [])

    return (
        <div className="flex flex-col h-[calc(100vh-280px)] min-h-[500px]">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-white/10">
                <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center shadow-lg shadow-purple-600/20">
                        <Brain className="w-4 h-4 text-white" />
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">DisasterGPT</h3>
                        <p className="text-[10px] text-slate-400">RAG + Multi-Agent + Causal AI — auto-routes to the best model</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5">
                        <ModeBadge mode="rag" />
                        <ModeBadge mode="multi_agent" />
                        <ModeBadge mode="causal" />
                    </div>
                    {messages.length > 0 && (
                        <button
                            onClick={clearChat}
                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                            title="Clear chat"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    )}
                </div>
            </div>

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-600/10 to-pink-600/10 dark:from-purple-500/20 dark:to-pink-500/20 flex items-center justify-center mb-4">
                            <Brain className="w-8 h-8 text-purple-500" />
                        </div>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">DisasterGPT</h3>
                        <p className="text-sm text-slate-500 max-w-md mb-6">
                            Ask anything about disasters, resources, predictions, or causal analysis.
                            I'll automatically route your question to the right AI system.
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg w-full">
                            {SUGGESTED_QUERIES.map((sq, i) => (
                                <button
                                    key={i}
                                    onClick={() => handleSubmit(sq.text)}
                                    className="flex items-start gap-2 p-3 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:bg-purple-50 dark:hover:bg-purple-500/5 hover:border-purple-200 dark:hover:border-purple-500/20 transition-all text-left group"
                                >
                                    <Sparkles className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-500 mt-0.5 shrink-0 transition-colors" />
                                    <div>
                                        <p className="text-xs text-slate-700 dark:text-slate-300 group-hover:text-purple-700 dark:group-hover:text-purple-300 font-medium transition-colors">{sq.text}</p>
                                        <ModeBadge mode={sq.mode} />
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div key={msg.id} className={cn("flex", msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                            <div className={cn(
                                "max-w-[85%] rounded-2xl",
                                msg.role === 'user'
                                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white px-4 py-3 shadow-lg shadow-purple-600/10'
                                    : 'bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/10 px-4 py-3 shadow-sm'
                            )}>
                                {msg.role === 'assistant' && (
                                    <div className="flex items-center gap-2 mb-2">
                                        <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                                            <Brain className="w-3 h-3 text-white" />
                                        </div>
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">DisasterGPT</span>
                                        <ModeBadge mode={msg.mode} />
                                        {msg.confidence !== undefined && (
                                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-white/5 text-slate-400">
                                                {(msg.confidence * 100).toFixed(0)}% confidence
                                            </span>
                                        )}
                                        {msg.isStreaming && (
                                            <Loader2 className="w-3 h-3 animate-spin text-purple-500" />
                                        )}
                                    </div>
                                )}

                                {/* Agent results (inline, before text) */}
                                {msg.agentResults && msg.agentResults.length > 0 && (
                                    <AgentResultsCard results={msg.agentResults} />
                                )}

                                {/* Causal data cards (inline) */}
                                {msg.causalEffects && msg.causalEffects.length > 0 && (
                                    <CausalEffectsCard effects={msg.causalEffects} />
                                )}
                                {msg.causalRootCauses && msg.causalRootCauses.length > 0 && (
                                    <RootCausesCard causes={msg.causalRootCauses} />
                                )}
                                {msg.causalInterventions && msg.causalInterventions.length > 0 && (
                                    <CausalInterventionsCard interventions={msg.causalInterventions} />
                                )}

                                {/* Main text content */}
                                {msg.role === 'user' ? (
                                    <p className="text-sm leading-relaxed">{msg.content}</p>
                                ) : (
                                    <div className="prose prose-sm prose-slate dark:prose-invert max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                                            {msg.content || (msg.isStreaming ? '▍' : '')}
                                        </ReactMarkdown>
                                    </div>
                                )}

                                {/* Sources */}
                                {msg.sources && msg.sources.length > 0 && (
                                    <SourcesCard sources={msg.sources} />
                                )}

                                {/* Timestamp */}
                                <p className={cn(
                                    "text-[9px] mt-2",
                                    msg.role === 'user' ? 'text-white/50 text-right' : 'text-slate-400'
                                )}>
                                    {msg.timestamp.toLocaleTimeString()}
                                </p>
                            </div>
                        </div>
                    ))
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="px-4 py-3 border-t border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.02] backdrop-blur-sm">
                <div className="flex gap-2">
                    <input
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault()
                                handleSubmit()
                            }
                        }}
                        placeholder="Ask about disasters, request coordination, or explore causal relationships..."
                        disabled={isStreaming}
                        className="flex-1 h-11 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none disabled:opacity-50"
                    />
                    <button
                        onClick={() => handleSubmit()}
                        disabled={isStreaming || !input.trim()}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 shadow-lg shadow-purple-600/20 transition-all"
                    >
                        {isStreaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                </div>
                <p className="text-[9px] text-slate-400 mt-1.5 text-center">
                    Auto-routes to RAG, Multi-Agent, or Causal AI based on your query. Press Enter to send.
                </p>
            </div>
        </div>
    )
}
