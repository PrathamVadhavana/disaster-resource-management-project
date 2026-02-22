'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
    sendChatMessage, createResourceRequest, endChatSession,
    type ChatbotResponse, type ResourceItem, type RequestPriority,
} from '@/lib/api/victim'
import { cn } from '@/lib/utils'
import {
    ArrowLeft, Send, Loader2, Bot, User, AlertTriangle,
    CheckCircle2, MapPin, Sparkles, RotateCcw, FileText,
} from 'lucide-react'
import Link from 'next/link'

interface Message {
    id: string
    role: 'user' | 'assistant' | 'system'
    content: string
    timestamp: Date
    extractedData?: Record<string, any> | null
    requestReady?: boolean
}

const INITIAL_MESSAGE: Message = {
    id: 'init',
    role: 'assistant',
    content:
        "Hi, I'm your emergency assistance AI. I'll help you request the resources you need as quickly as possible. Tell me — what do you need help with right now?",
    timestamp: new Date(),
}

function generateMsgId() {
    return Math.random().toString(36).slice(2, 10)
}

// ── Priority color helpers ─────────────────────────────────────────────────
const PRIORITY_STYLES: Record<string, string> = {
    critical: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30',
    high: 'bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-500/30',
    medium: 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/30',
    low: 'bg-slate-100 dark:bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-500/30',
}

export function AIChatbot() {
    const router = useRouter()
    const queryClient = useQueryClient()
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLTextAreaElement>(null)

    const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE])
    const [input, setInput] = useState('')
    const [sessionId, setSessionId] = useState<string | null>(null)
    const [isTyping, setIsTyping] = useState(false)
    const [extractedData, setExtractedData] = useState<Record<string, any> | null>(null)
    const [requestReady, setRequestReady] = useState(false)
    const [submitted, setSubmitted] = useState(false)
    const [error, setError] = useState('')

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, isTyping])

    // Focus input on mount
    useEffect(() => {
        inputRef.current?.focus()
    }, [])

    // Send message mutation
    const chatMutation = useMutation({
        mutationFn: (message: string) => sendChatMessage(message, sessionId),
        onSuccess: (data: ChatbotResponse) => {
            setSessionId(data.session_id)
            setIsTyping(false)

            const assistantMsg: Message = {
                id: generateMsgId(),
                role: 'assistant',
                content: data.assistant_message,
                timestamp: new Date(),
                extractedData: data.extracted_data,
                requestReady: data.request_ready,
            }
            setMessages(prev => [...prev, assistantMsg])

            if (data.extracted_data) {
                setExtractedData(data.extracted_data)
            }
            if (data.request_ready) {
                setRequestReady(true)
            }
        },
        onError: (err: Error) => {
            setIsTyping(false)
            setMessages(prev => [
                ...prev,
                {
                    id: generateMsgId(),
                    role: 'system',
                    content: `Connection error: ${err.message}. Please try again.`,
                    timestamp: new Date(),
                },
            ])
        },
    })

    // Submit resource request from extracted data
    const submitMutation = useMutation({
        mutationFn: createResourceRequest,
        onSuccess: () => {
            setSubmitted(true)
            queryClient.invalidateQueries({ queryKey: ['victim-requests'] })
            queryClient.invalidateQueries({ queryKey: ['victim-stats'] })
            // Clean up session
            if (sessionId) endChatSession(sessionId).catch(() => {})
        },
        onError: (err: Error) => {
            setError(`Failed to submit request: ${err.message}`)
        },
    })

    const handleSend = useCallback(() => {
        const text = input.trim()
        if (!text || isTyping) return

        const userMsg: Message = {
            id: generateMsgId(),
            role: 'user',
            content: text,
            timestamp: new Date(),
        }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setIsTyping(true)
        setError('')
        chatMutation.mutate(text)
    }, [input, isTyping, chatMutation])

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
            }
        },
        [handleSend],
    )

    const handleSubmitRequest = useCallback(() => {
        if (!extractedData) return

        // Map extracted data to request payload
        const resourceTypes = extractedData.resource_types || ['Custom']
        const items: ResourceItem[] = resourceTypes.map((t: string) => ({
            resource_type: t,
            quantity: Math.max(1, Math.ceil((extractedData.estimated_quantity || 1) / resourceTypes.length)),
        }))

        const payload = {
            items,
            priority: (extractedData.priority || 'medium') as RequestPriority,
            description: extractedData.description || messages.filter(m => m.role === 'user').map(m => m.content).join(' | '),
            latitude: extractedData.latitude || undefined,
            longitude: extractedData.longitude || undefined,
            address_text: extractedData.address_text || undefined,
        }

        submitMutation.mutate(payload)
    }, [extractedData, messages, submitMutation])

    const handleReset = useCallback(() => {
        if (sessionId) endChatSession(sessionId).catch(() => {})
        setMessages([INITIAL_MESSAGE])
        setSessionId(null)
        setInput('')
        setExtractedData(null)
        setRequestReady(false)
        setSubmitted(false)
        setError('')
    }, [sessionId])

    // ── Render ────────────────────────────────────────────────────────────────

    if (submitted) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4 px-4">
                <div className="p-4 rounded-full bg-emerald-100 dark:bg-emerald-500/20">
                    <CheckCircle2 className="w-12 h-12 text-emerald-600 dark:text-emerald-400" />
                </div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
                    Request Submitted!
                </h2>
                <p className="text-slate-500 dark:text-slate-400 max-w-md">
                    Your request has been submitted and our team will review it shortly.
                    High-priority requests are processed first.
                </p>
                <div className="flex gap-3 mt-4">
                    <button
                        onClick={() => router.push('/victim/requests')}
                        className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-red-500 to-orange-600 text-white text-sm font-semibold shadow-lg"
                    >
                        View My Requests
                    </button>
                    <button
                        onClick={handleReset}
                        className="px-5 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 text-sm font-medium hover:bg-slate-50 dark:hover:bg-white/5"
                    >
                        New Request
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div className="flex flex-col h-[calc(100vh-12rem)] max-h-[800px]">
            {/* Header */}
            <div className="flex items-center gap-3 pb-4 border-b border-slate-200 dark:border-white/10">
                <Link
                    href="/victim/requests"
                    className="p-2 rounded-xl bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:bg-slate-50 dark:hover:bg-white/10 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                </Link>
                <div className="flex-1">
                    <div className="flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-amber-500" />
                        <h1 className="text-lg font-bold text-slate-900 dark:text-white">
                            AI Assistance
                        </h1>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Describe your situation — I'll help you get the right resources
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={handleReset}
                        className="p-2 rounded-xl border border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                        title="Start over"
                    >
                        <RotateCcw className="w-4 h-4" />
                    </button>
                    <Link
                        href="/victim/requests/new"
                        className="p-2 rounded-xl border border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5"
                        title="Switch to manual form"
                    >
                        <FileText className="w-4 h-4" />
                    </Link>
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto py-4 space-y-4 scrollbar-thin">
                {messages.map((msg) => (
                    <div key={msg.id} className={cn('flex gap-3', msg.role === 'user' && 'flex-row-reverse')}>
                        {/* Avatar */}
                        <div
                            className={cn(
                                'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                                msg.role === 'assistant'
                                    ? 'bg-gradient-to-br from-amber-400 to-orange-500'
                                    : msg.role === 'user'
                                      ? 'bg-gradient-to-br from-blue-500 to-indigo-600'
                                      : 'bg-red-100 dark:bg-red-500/20',
                            )}
                        >
                            {msg.role === 'assistant' ? (
                                <Bot className="w-4 h-4 text-white" />
                            ) : msg.role === 'user' ? (
                                <User className="w-4 h-4 text-white" />
                            ) : (
                                <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400" />
                            )}
                        </div>

                        {/* Bubble */}
                        <div
                            className={cn(
                                'max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
                                msg.role === 'assistant'
                                    ? 'bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/10 text-slate-800 dark:text-slate-200'
                                    : msg.role === 'user'
                                      ? 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white'
                                      : 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400',
                            )}
                        >
                            {msg.content.split('\n').map((line, i) => (
                                <p key={i} className={i > 0 ? 'mt-1.5' : ''}>
                                    {line.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
                                        part.startsWith('**') && part.endsWith('**') ? (
                                            <strong key={j}>{part.slice(2, -2)}</strong>
                                        ) : (
                                            <span key={j}>{part}</span>
                                        ),
                                    )}
                                </p>
                            ))}
                        </div>
                    </div>
                ))}

                {/* Typing indicator */}
                {isTyping && (
                    <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center flex-shrink-0">
                            <Bot className="w-4 h-4 text-white" />
                        </div>
                        <div className="bg-white dark:bg-white/[0.04] border border-slate-200 dark:border-white/10 rounded-2xl px-4 py-3">
                            <div className="flex gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                                <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                                <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Extracted Data Preview + Submit */}
            {requestReady && extractedData && !submitted && (
                <div className="rounded-2xl border-2 border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 p-4 mb-3 space-y-3">
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                        <h3 className="font-semibold text-emerald-800 dark:text-emerald-300 text-sm">
                            Request Ready to Submit
                        </h3>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                        <div className="p-2 rounded-lg bg-white/60 dark:bg-white/5">
                            <span className="text-slate-500 dark:text-slate-400">Resources</span>
                            <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                                {extractedData.resource_types?.join(', ') || 'Custom'}
                            </p>
                        </div>
                        <div className="p-2 rounded-lg bg-white/60 dark:bg-white/5">
                            <span className="text-slate-500 dark:text-slate-400">Priority</span>
                            <p className={cn('font-semibold mt-0.5 capitalize', PRIORITY_STYLES[extractedData.priority] ? 'text-slate-900 dark:text-white' : '')}>
                                {extractedData.priority || 'medium'}
                            </p>
                        </div>
                        <div className="p-2 rounded-lg bg-white/60 dark:bg-white/5">
                            <span className="text-slate-500 dark:text-slate-400">Quantity</span>
                            <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                                {extractedData.estimated_quantity || 1}
                            </p>
                        </div>
                        {extractedData.address_text && (
                            <div className="p-2 rounded-lg bg-white/60 dark:bg-white/5 col-span-2 sm:col-span-1">
                                <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1">
                                    <MapPin className="w-3 h-3" /> Location
                                </span>
                                <p className="font-semibold text-slate-900 dark:text-white mt-0.5 truncate">
                                    {extractedData.address_text}
                                </p>
                            </div>
                        )}
                    </div>
                    {error && (
                        <p className="text-red-600 dark:text-red-400 text-xs">{error}</p>
                    )}
                    <button
                        onClick={handleSubmitRequest}
                        disabled={submitMutation.isPending}
                        className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-semibold text-sm shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {submitMutation.isPending ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <CheckCircle2 className="w-4 h-4" />
                        )}
                        Submit Request
                    </button>
                </div>
            )}

            {/* Input */}
            <div className="pt-3 border-t border-slate-200 dark:border-white/10">
                <div className="flex gap-2">
                    <textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={requestReady ? 'Add details or click Submit above…' : 'Describe your situation…'}
                        rows={1}
                        className="flex-1 px-4 py-3 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500/30 focus:border-amber-500/50 resize-none"
                        style={{ minHeight: '44px', maxHeight: '120px' }}
                    />
                    <button
                        onClick={handleSend}
                        disabled={!input.trim() || isTyping}
                        className="px-4 py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 text-white font-semibold shadow-lg shadow-amber-500/20 hover:shadow-amber-500/30 hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        {isTyping ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <Send className="w-5 h-5" />
                        )}
                    </button>
                </div>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1.5 text-center">
                    Supports any language · Press Enter to send · Shift+Enter for new line
                </p>
            </div>
        </div>
    )
}
