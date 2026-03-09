'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Loader2, Send, Bot, User, Sparkles, BookOpen, AlertTriangle,
    X, Maximize2, Minimize2, RotateCcw
} from 'lucide-react'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── Types ──────────────────────────────────────────────────────────────────────

interface LLMSource {
    content_preview: string
    source: string
    type: string
    relevance: number
}

interface LLMResponse {
    response: string
    sources: LLMSource[]
    confidence: number
    disaster_id?: string
    documents_retrieved: number
}

interface ChatMessage {
    id: string
    role: 'user' | 'assistant'
    content: string
    sources?: LLMSource[]
    confidence?: number
    timestamp: Date
    isStreaming?: boolean
}

interface ChatInterfaceProps {
    disasterId?: string
    className?: string
    defaultExpanded?: boolean
}

// ── Streaming SSE parser ───────────────────────────────────────────────────────

async function* streamLLMResponse(
    query: string,
    disasterId?: string,
): AsyncGenerator<{ type: string; data?: any; confidence?: number }> {
    const token = await getAccessTokenForStream()
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

    const res = await fetch(`${API_BASE}/api/llm/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query, disaster_id: disasterId }),
    })

    if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err?.detail || `Stream error ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue

            // SSE format: "data: {...}"
            const payload = trimmed.startsWith('data: ') ? trimmed.slice(6) : trimmed

            try {
                const parsed = JSON.parse(payload)
                yield parsed
            } catch {
                // Skip non-JSON lines
            }
        }
    }
}

async function getAccessTokenForStream(): Promise<string | null> {
    try {
        const { getSupabaseClient } = await import('@/lib/supabase/client')
        const sb = getSupabaseClient()
        const { data: { session } } = await sb.auth.getSession()
        return session?.access_token ?? null
    } catch {
        return null
    }
}

// ── Confidence badge ───────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: number }) {
    const pct = Math.round(confidence * 100)
    const color =
        pct >= 70 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' :
        pct >= 40 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400' :
                    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
    return (
        <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold', color)}>
            <Sparkles className="w-3 h-3" />
            {pct}% confidence
        </span>
    )
}

// ── Source pills ────────────────────────────────────────────────────────────────

function SourcesList({ sources }: { sources: LLMSource[] }) {
    const [expanded, setExpanded] = useState(false)

    if (!sources.length) return null

    return (
        <div className="mt-2">
            <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400 hover:text-blue-500 transition-colors"
            >
                <BookOpen className="w-3 h-3" />
                {sources.length} source{sources.length !== 1 ? 's' : ''}
                <span className="text-[10px]">{expanded ? '▲' : '▼'}</span>
            </button>
            {expanded && (
                <div className="mt-1.5 space-y-1.5">
                    {sources.map((src, i) => (
                        <div
                            key={i}
                            className="text-[11px] p-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                        >
                            <div className="flex items-center gap-2 mb-0.5">
                                <span className="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-semibold uppercase text-[9px]">
                                    {src.source}
                                </span>
                                <span className="text-slate-400">{src.type}</span>
                                <span className="ml-auto text-slate-400">
                                    {Math.round(src.relevance * 100)}% match
                                </span>
                            </div>
                            <p className="text-slate-600 dark:text-slate-300 line-clamp-2">
                                {src.content_preview}
                            </p>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

// ── Suggested prompts ──────────────────────────────────────────────────────────

const SUGGESTED_PROMPTS = [
    'What resources are typically needed for a critical flood response?',
    'Generate a situation report template for earthquake response.',
    'What are the priority actions for a Category 4 cyclone?',
    'Recommend resource allocation for a large-scale displacement event.',
]

// ── Main component ─────────────────────────────────────────────────────────────

export function ChatInterface({ disasterId, className, defaultExpanded = false }: ChatInterfaceProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [input, setInput] = useState('')
    const [isStreaming, setIsStreaming] = useState(false)
    const [expanded, setExpanded] = useState(defaultExpanded)
    const bottomRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)
    const abortRef = useRef<AbortController | null>(null)

    // Auto-scroll on new messages
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    // Focus input on expand
    useEffect(() => {
        if (expanded) inputRef.current?.focus()
    }, [expanded])

    // Non-streaming fallback mutation
    const queryMutation = useMutation({
        mutationFn: (query: string) => api.queryLLM({ query, disaster_id: disasterId }),
        onSuccess: (data: LLMResponse) => {
            setMessages(prev => [
                ...prev.filter(m => !m.isStreaming),
                {
                    id: crypto.randomUUID(),
                    role: 'assistant',
                    content: data.response,
                    sources: data.sources,
                    confidence: data.confidence,
                    timestamp: new Date(),
                },
            ])
        },
        onError: (err: Error) => {
            setMessages(prev => [
                ...prev.filter(m => !m.isStreaming),
                {
                    id: crypto.randomUUID(),
                    role: 'assistant',
                    content: `Error: ${err.message}. Please try again.`,
                    timestamp: new Date(),
                },
            ])
        },
    })

    // Streaming handler
    const handleStreamingQuery = useCallback(async (query: string) => {
        setIsStreaming(true)
        const assistantId = crypto.randomUUID()

        // Add placeholder assistant message
        setMessages(prev => [
            ...prev,
            {
                id: assistantId,
                role: 'assistant',
                content: '',
                timestamp: new Date(),
                isStreaming: true,
            },
        ])

        try {
            let fullContent = ''
            let sources: LLMSource[] = []
            let confidence = 0

            for await (const event of streamLLMResponse(query, disasterId)) {
                if (event.type === 'sources') {
                    sources = event.data || []
                } else if (event.type === 'token') {
                    fullContent += event.data || ''
                    setMessages(prev =>
                        prev.map(m =>
                            m.id === assistantId
                                ? { ...m, content: fullContent, sources, isStreaming: true }
                                : m
                        )
                    )
                } else if (event.type === 'done') {
                    confidence = event.confidence || 0
                } else if (event.type === 'error') {
                    throw new Error(event.data)
                }
            }

            // Finalize message
            setMessages(prev =>
                prev.map(m =>
                    m.id === assistantId
                        ? { ...m, content: fullContent, sources, confidence, isStreaming: false }
                        : m
                )
            )
        } catch (err: any) {
            setMessages(prev =>
                prev.map(m =>
                    m.id === assistantId
                        ? {
                            ...m,
                            content: `Error: ${err.message || 'Stream failed'}. Please try again.`,
                            isStreaming: false,
                        }
                        : m
                )
            )
        } finally {
            setIsStreaming(false)
        }
    }, [disasterId])

    const handleSubmit = useCallback(
        (query: string) => {
            if (!query.trim() || isStreaming) return

            const userMsg: ChatMessage = {
                id: crypto.randomUUID(),
                role: 'user',
                content: query.trim(),
                timestamp: new Date(),
            }
            setMessages(prev => [...prev, userMsg])
            setInput('')

            // Try streaming first, fall back to non-streaming
            handleStreamingQuery(query.trim())
        },
        [isStreaming, handleStreamingQuery],
    )

    const handleReset = () => {
        setMessages([])
        setInput('')
    }

    // ── Minimized view ──────────────────────────────────────────────────

    if (!expanded) {
        return (
            <button
                onClick={() => setExpanded(true)}
                className={cn(
                    'fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full',
                    'bg-gradient-to-br from-blue-600 to-indigo-700 text-white',
                    'shadow-lg shadow-blue-500/25 hover:shadow-xl hover:scale-105',
                    'flex items-center justify-center transition-all duration-200',
                    className,
                )}
                title="Open DisasterGPT"
            >
                <Bot className="w-6 h-6" />
                {messages.length > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                        {messages.filter(m => m.role === 'assistant').length}
                    </span>
                )}
            </button>
        )
    }

    // ── Expanded view ───────────────────────────────────────────────────

    return (
        <div
            className={cn(
                'fixed bottom-6 right-6 z-50 w-[440px] max-h-[680px]',
                'bg-white dark:bg-slate-950 rounded-2xl shadow-2xl shadow-black/20',
                'border border-slate-200 dark:border-white/10',
                'flex flex-col overflow-hidden',
                'animate-in slide-in-from-bottom-4 fade-in duration-300',
                className,
            )}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
                <div className="flex items-center gap-2">
                    <Bot className="w-5 h-5" />
                    <div>
                        <h3 className="font-semibold text-sm">DisasterGPT</h3>
                        <p className="text-[10px] text-blue-200">
                            AI-powered disaster management assistant
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={handleReset}
                        className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                        title="Reset conversation"
                    >
                        <RotateCcw className="w-4 h-4" />
                    </button>
                    <button
                        onClick={() => setExpanded(false)}
                        className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                        title="Minimise"
                    >
                        <Minimize2 className="w-4 h-4" />
                    </button>
                    <button
                        onClick={() => setExpanded(false)}
                        className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
                        title="Close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Disaster context banner */}
            {disasterId && (
                <div className="px-4 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800/40 flex items-center gap-2 text-xs text-amber-700 dark:text-amber-400">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>Context: Disaster <span className="font-mono font-semibold">{disasterId.slice(0, 8)}…</span></span>
                </div>
            )}

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[200px] max-h-[440px]">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-8">
                        <Bot className="w-10 h-10 text-blue-400 mb-3" />
                        <h4 className="font-semibold text-slate-700 dark:text-slate-200 mb-1">
                            DisasterGPT
                        </h4>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                            Ask about disaster response, resource needs, situation analysis, and more.
                        </p>
                        <div className="space-y-2 w-full">
                            {SUGGESTED_PROMPTS.map((prompt, i) => (
                                <button
                                    key={i}
                                    onClick={() => handleSubmit(prompt)}
                                    className="w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-blue-50 dark:hover:bg-blue-950/30 hover:border-blue-300 dark:hover:border-blue-700 text-slate-600 dark:text-slate-400 transition-colors"
                                >
                                    {prompt}
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    messages.map(msg => (
                        <div
                            key={msg.id}
                            className={cn(
                                'flex gap-2.5',
                                msg.role === 'user' ? 'flex-row-reverse' : 'flex-row',
                            )}
                        >
                            {/* Avatar */}
                            <div
                                className={cn(
                                    'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center',
                                    msg.role === 'user'
                                        ? 'bg-slate-200 dark:bg-slate-700'
                                        : 'bg-gradient-to-br from-blue-500 to-indigo-600',
                                )}
                            >
                                {msg.role === 'user' ? (
                                    <User className="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />
                                ) : (
                                    <Bot className="w-3.5 h-3.5 text-white" />
                                )}
                            </div>

                            {/* Bubble */}
                            <div
                                className={cn(
                                    'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm',
                                    msg.role === 'user'
                                        ? 'bg-blue-600 text-white rounded-tr-sm'
                                        : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 rounded-tl-sm',
                                )}
                            >
                                {msg.role === 'assistant' ? (
                                    <div className="prose prose-sm dark:prose-invert prose-p:my-1 prose-headings:my-2 max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {msg.content || (msg.isStreaming ? '...' : '')}
                                        </ReactMarkdown>
                                        {msg.isStreaming && (
                                            <span className="inline-block w-1.5 h-4 bg-blue-500 animate-pulse ml-0.5 rounded-sm" />
                                        )}
                                    </div>
                                ) : (
                                    <p>{msg.content}</p>
                                )}

                                {/* Confidence + Sources */}
                                {msg.role === 'assistant' && !msg.isStreaming && msg.confidence !== undefined && (
                                    <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                                        <ConfidenceBadge confidence={msg.confidence} />
                                    </div>
                                )}
                                {msg.role === 'assistant' && !msg.isStreaming && msg.sources && (
                                    <SourcesList sources={msg.sources} />
                                )}
                            </div>
                        </div>
                    ))
                )}
                <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-3 bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-white/10">
                <form
                    onSubmit={e => {
                        e.preventDefault()
                        handleSubmit(input)
                    }}
                    className="flex gap-2"
                >
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        placeholder="Ask DisasterGPT..."
                        className="flex-1 h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                        disabled={isStreaming}
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || isStreaming}
                        className={cn(
                            'h-10 px-4 rounded-xl flex items-center justify-center transition-all',
                            'bg-gradient-to-r from-blue-600 to-indigo-600 text-white',
                            'hover:from-blue-700 hover:to-indigo-700',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                        )}
                    >
                        {isStreaming ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <Send className="w-5 h-5" />
                        )}
                    </button>
                </form>
                <p className="text-center text-[10px] text-slate-400 mt-1.5">
                    DisasterGPT may produce inaccurate information. Verify critical decisions.
                </p>
            </div>
        </div>
    )
}

export default ChatInterface
