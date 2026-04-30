'use client'

import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from 'react'
import { 
    Send, Bot, User, X, MessageCircle, Loader2, 
    Copy, Check, ThumbsUp, ThumbsDown, Search, 
    Sparkles, Zap, FileText, AlertTriangle,
    Clock, Wifi, WifiOff, Trash2, Download,
    TrendingUp, MapPin, Activity, BarChart3, Play,
    CheckCircle2, AlertCircle, ArrowRight
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { getSupabaseClient } from '@/lib/supabase/client'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface ChatMessage {
    role: 'user' | 'assistant'
    content: string
    timestamp: string
    feedback?: 'positive' | 'negative' | null
    context_data?: Record<string, unknown>
    intent?: string
    follow_up_suggestions?: string[]
    action_cards?: ActionCard[]
}

interface ActionCard {
    type: string
    title: string
    description: string
    action: { endpoint: string; method: string; payload: Record<string, unknown> }
    confirm_label: string
    style: 'primary' | 'warning' | 'destructive'
}

interface ChatContext { disaster_id?: string }
interface ChatResponse {
    message: string
    session_id: string
    intent: string
    context_data?: Record<string, unknown>
    follow_up_suggestions?: string[]
    action_cards?: ActionCard[]
}

interface SSEEvent { type: string; data?: string; intent?: string; session_id?: string; suggestions?: string[]; cards?: ActionCard[] }
interface SessionHistory { session_id: string; messages: ChatMessage[]; created_at: string; message_count: number }

const PROMPTS_BY_ROLE: Record<string, { icon: React.ReactNode; label: string }[]> = {
    victim: [
        { icon: <AlertTriangle className="w-4 h-4" />, label: "What's the status of my requests?" },
        { icon: <Sparkles className="w-4 h-4" />, label: "How do I request food or water?" },
        { icon: <Zap className="w-4 h-4" />, label: "What resources are available right now?" }
    ],
    ngo: [
        { icon: <FileText className="w-4 h-4" />, label: "Show me my assigned requests" },
        { icon: <Zap className="w-4 h-4" />, label: "Which requests are highest priority?" },
        { icon: <Sparkles className="w-4 h-4" />, label: "What's our current inventory status?" }
    ],
    admin: [
        { icon: <Sparkles className="w-4 h-4" />, label: "Give me an admin briefing" },
        { icon: <Zap className="w-4 h-4" />, label: "Where are our biggest resource gaps?" },
        { icon: <TrendingUp className="w-4 h-4" />, label: "Are things getting better or worse?" },
        { icon: <MapPin className="w-4 h-4" />, label: "Which areas have the most requests?" },
        { icon: <Activity className="w-4 h-4" />, label: "Compare disaster performance scorecards" },
        { icon: <BarChart3 className="w-4 h-4" />, label: "Give me a comprehensive daily digest" },
    ],
}

const DEFAULT_PROMPTS = [
    { icon: <Sparkles className="w-4 h-4" />, label: "Give me an admin briefing" },
    { icon: <Zap className="w-4 h-4" />, label: "How many requests are pending right now?" },
    { icon: <AlertTriangle className="w-4 h-4" />, label: "What resources are running low?" },
]

const QUICK_ACTIONS = [
    { icon: <Sparkles className="w-4 h-4" />, label: "Briefing", action: "Give me an admin briefing" },
    { icon: <Zap className="w-4 h-4" />, label: "Resource Gaps", action: "Where are our biggest resource gaps?" },
    { icon: <TrendingUp className="w-4 h-4" />, label: "Trends", action: "Are things getting better or worse?" },
    { icon: <MapPin className="w-4 h-4" />, label: "Geography", action: "Which areas have the most requests?" },
    { icon: <Activity className="w-4 h-4" />, label: "Scorecards", action: "Compare disaster performance scorecards" },
    { icon: <BarChart3 className="w-4 h-4" />, label: "Digest", action: "Give me a comprehensive daily digest" },
]

async function sendChatMessage(message: string, sessionId?: string, context?: ChatContext): Promise<ChatResponse> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    const userRole = session?.user?.user_metadata?.role ?? null
    const userName = session?.user?.user_metadata?.full_name ?? null
    const userId = session?.user?.id ?? null
    const response = await fetch(`${API_BASE}/api/llm/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        body: JSON.stringify({ message, session_id: sessionId, context, user_context: { role: userRole, name: userName, user_id: userId } }),
    })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    return response.json()
}

async function sendChatMessageStream(message: string, sessionId?: string, context?: ChatContext, onEvent?: (event: SSEEvent) => void): Promise<void> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    const userRole = session?.user?.user_metadata?.role ?? null
    const userName = session?.user?.user_metadata?.full_name ?? null
    const userId = session?.user?.id ?? null
    const response = await fetch(`${API_BASE}/api/llm/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        body: JSON.stringify({ message, session_id: sessionId, context, user_context: { role: userRole, name: userName, user_id: userId } }),
    })
    if (!response.ok) throw new Error(`Stream failed (${response.status})`)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('No reader')
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
            if (line.startsWith('data: ')) { try { onEvent?.(JSON.parse(line.slice(6))) } catch {} }
        }
    }
}

async function executeAction(actionType: string, payload: Record<string, unknown>, sessionId?: string): Promise<{ success: boolean; message: string }> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    const response = await fetch(`${API_BASE}/api/llm/actions/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        body: JSON.stringify({ action_type: actionType, action_payload: payload, session_id: sessionId }),
    })
    if (!response.ok) throw new Error(`Action failed (${response.status})`)
    return response.json()
}

async function getSessionHistory(sessionId: string): Promise<SessionHistory> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    const response = await fetch(`${API_BASE}/api/llm/sessions/${sessionId}`, {
        headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
    })
    if (!response.ok) throw new Error(`Failed: ${response.statusText}`)
    return response.json()
}

function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16) })
}

function formatRelativeTime(timestamp: string): string {
    const diff = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000)
    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
}

const CHART_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#14b8a6']

function FollowUpChips({ suggestions, onSelect }: { suggestions: string[]; onSelect: (s: string) => void }) {
    return (
        <div className="flex flex-wrap gap-2 mt-3">
            {suggestions.map((s, i) => (
                <button key={i} onClick={() => onSelect(s)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 border border-blue-200 dark:border-blue-800 transition-all hover:scale-105 active:scale-95">
                    <ArrowRight className="w-3 h-3" />{s}
                </button>
            ))}
        </div>
    )
}

function ActionCardComponent({ card, sessionId, onActionComplete, onSendChat }: { card: ActionCard; sessionId: string; onActionComplete: (success: boolean, message: string) => void, onSendChat?: (message: string) => void }) {
    const [isExecuting, setIsExecuting] = useState(false)
    const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
    const handleExecute = async () => {
        setIsExecuting(true)
        try {
            if ((card.action?.endpoint === '/api/llm/chat' || card.type === 'view_alerts' || card.type === 'review_stale') && card.action?.payload?.message) {
                if (onSendChat) {
                    onSendChat(card.action.payload.message as string)
                    setResult({ success: true, message: 'Request sent to chat' })
                    onActionComplete(true, 'Request sent to chat')
                } else {
                    setResult({ success: false, message: 'Chat interaction not supported here' })
                    onActionComplete(false, 'Chat interaction not supported here')
                }
            } else {
                const response = await executeAction(card.type, card.action.payload, sessionId)
                setResult({ success: response.success, message: response.message })
                onActionComplete(response.success, response.message)
            }
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Action failed'
            setResult({ success: false, message })
            onActionComplete(false, message)
        } finally { setIsExecuting(false) }
    }
    const styles = { primary: 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20', warning: 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20', destructive: 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20' }
    const btnStyles = { primary: 'bg-blue-600 hover:bg-blue-700 text-white', warning: 'bg-amber-600 hover:bg-amber-700 text-white', destructive: 'bg-red-600 hover:bg-red-700 text-white' }
    if (result) {
        return (
            <div className={`my-3 p-3 rounded-lg border ${result.success ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20' : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20'}`}>
                <div className="flex items-center gap-2">{result.success ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : <AlertCircle className="w-4 h-4 text-red-600" />}<span className="text-sm font-medium">{result.message}</span></div>
            </div>
        )
    }
    return (
        <div className={`my-3 p-3 rounded-lg border ${styles[card.style]}`}>
            <div className="flex items-start justify-between gap-3">
                <div className="flex-1"><p className="text-sm font-semibold">{card.title}</p><p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">{card.description}</p></div>
                <Button onClick={handleExecute} disabled={isExecuting} className={`shrink-0 ${btnStyles[card.style]}`}>
                    {isExecuting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <><Play className="w-3.5 h-3.5 mr-1" />{card.confirm_label}</>}
                </Button>
            </div>
        </div>
    )
}

function InlineChart({ contextData }: { contextData: Record<string, unknown> }) {
    const dataType = contextData?.type as string
    if (dataType === 'trends' && contextData?.data) {
        const trends = contextData.data as Record<string, { this_week: number; last_week: number }>
        const chartData = Object.entries(trends).map(([key, val]) => ({ name: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), 'This Week': val.this_week ?? 0, 'Last Week': val.last_week ?? 0 }))
        if (!chartData.length) return null
        return <div className="my-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg"><p className="text-xs font-semibold text-slate-500 mb-2"> TREND COMPARISON</p><ResponsiveContainer width="100%" height={180}><BarChart data={chartData} barGap={4}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="Last Week" fill="#94a3b8" radius={[4, 4, 0, 0]} /><Bar dataKey="This Week" fill="#6366f1" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
    }
    if (dataType === 'supply_demand_gap' && contextData?.data) {
        const gaps = (contextData.data as { gaps?: Array<{ type: string; demand: number; supply: number }> })?.gaps || []
        if (!gaps.length) return null
        const chartData = gaps.slice(0, 8).map(g => ({ name: g.type?.replace(/_/g, ' '), Demand: g.demand ?? 0, Supply: g.supply ?? 0 }))
        return <div className="my-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg"><p className="text-xs font-semibold text-slate-500 mb-2"> SUPPLY vs DEMAND</p><ResponsiveContainer width="100%" height={180}><BarChart data={chartData} barGap={4}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="Demand" fill="#ef4444" radius={[4, 4, 0, 0]} /><Bar dataKey="Supply" fill="#22c55e" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
    }
    if (dataType === 'request_pipeline' && contextData?.data) {
        const funnel = (contextData.data as { funnel?: Record<string, number> })?.funnel || {}
        const stages = ['pending', 'approved', 'assigned', 'in_progress', 'delivered', 'completed', 'rejected']
        const chartData = stages.filter(s => (funnel[s] ?? 0) > 0).map((s, i) => ({ name: s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), count: funnel[s], fill: CHART_COLORS[i % CHART_COLORS.length] }))
        if (!chartData.length) return null
        return <div className="my-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg"><p className="text-xs font-semibold text-slate-500 mb-2"> REQUEST PIPELINE</p><ResponsiveContainer width="100%" height={180}><BarChart data={chartData} layout="vertical"><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis type="number" tick={{ fontSize: 11 }} /><YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={90} /><Tooltip /><Bar dataKey="count" radius={[0, 4, 4, 0]}>{chartData.map((e, i) => <Cell key={i} fill={e.fill} />)}</Bar></BarChart></ResponsiveContainer></div>
    }
    if (dataType === 'disaster_comparison' && Array.isArray(contextData?.data)) {
        const scorecards = contextData.data as Array<{ title: string; health_score: number; completion_rate: number }>
        if (!scorecards.length) return null
        const chartData = scorecards.map(sc => ({ name: sc.title?.slice(0, 20), 'Health Score': sc.health_score ?? 0, 'Completion %': sc.completion_rate ?? 0 }))
        return <div className="my-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg"><p className="text-xs font-semibold text-slate-500 mb-2"> DISASTER SCORECARDS</p><ResponsiveContainer width="100%" height={180}><BarChart data={chartData} barGap={4}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="Health Score" fill="#6366f1" radius={[4, 4, 0, 0]} /><Bar dataKey="Completion %" fill="#22c55e" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
    }
    if (dataType === 'geographic' && contextData?.data) {
        const locs = (contextData.data as { top_locations?: Array<{ location: string; total: number; pending: number }> })?.top_locations || []
        if (!locs.length) return null
        const chartData = locs.slice(0, 8).map(l => ({ name: l.location?.slice(0, 15), Total: l.total ?? 0, Pending: l.pending ?? 0 }))
        return <div className="my-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg"><p className="text-xs font-semibold text-slate-500 mb-2"> REQUESTS BY LOCATION</p><ResponsiveContainer width="100%" height={180}><BarChart data={chartData} barGap={4}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" height={50} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="Total" fill="#6366f1" radius={[4, 4, 0, 0]} /><Bar dataKey="Pending" fill="#f59e0b" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
    }
    return null
}

function exportContextAsCSV(contextData: Record<string, unknown>, intent?: string) {
    const dataType = contextData?.type as string
    let csv = ''
    const filename = `disastergpt-${dataType || intent || 'data'}-${new Date().toISOString().slice(0, 10)}.csv`
    if (dataType === 'geographic' && contextData?.data) {
        const locs = (contextData.data as { top_locations?: Array<Record<string, unknown>> })?.top_locations || []
        if (locs.length) { csv = 'Location,Total,Pending,Completed,High Priority\n'; locs.forEach(l => { csv += `"${l.location}",${l.total},${l.pending},${l.completed},${l.high_priority}\n` }) }
    } else if (dataType === 'disaster_comparison' && Array.isArray(contextData?.data)) {
        csv = 'Disaster,Health Score,Completion Rate,Pending,In Progress,Avg Fulfillment Hours\n'; (contextData.data as Array<Record<string, unknown>>).forEach(sc => { csv += `"${sc.title}",${sc.health_score},${sc.completion_rate}%,${sc.pending},${sc.in_progress},${sc.avg_fulfillment_hours ?? 'N/A'}\n` })
    }
    if (!csv) return
    const blob = new Blob([csv], { type: 'text/csv' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
}

interface DisasterGPTProps { embedded?: boolean; onClose?: () => void }

export function DisasterGPT({ embedded = false, onClose }: DisasterGPTProps) {
    const [sessionId, setSessionId] = useState<string | null>(null)
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [input, setInput] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [isLoadingHistory, setIsLoadingHistory] = useState(false)
    const [isStreaming, setIsStreaming] = useState(false)
    const [streamingContent, setStreamingContent] = useState('')
    const [suggestedPrompts, setSuggestedPrompts] = useState<{ icon: React.ReactNode; label: string }[]>(DEFAULT_PROMPTS)
    const [showSearch, setShowSearch] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [showQuickActions, setShowQuickActions] = useState(false)
    const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null)
    const [isOnline, setIsOnline] = useState(true)
    // Streaming is always enabled
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const searchInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        setIsOnline(navigator.onLine)
        const h1 = () => setIsOnline(true); const h2 = () => setIsOnline(false)
        window.addEventListener('online', h1); window.addEventListener('offline', h2)
        return () => { window.removeEventListener('online', h1); window.removeEventListener('offline', h2) }
    }, [])

    useEffect(() => {
        const stored = localStorage.getItem('disastergpt_session_id')
        if (stored) { setSessionId(stored); loadHistory(stored) }
        else { const id = generateUUID(); setSessionId(id); localStorage.setItem('disastergpt_session_id', id) }
    }, [])

    useEffect(() => { if (sessionId) loadHistory(sessionId) }, [sessionId])

    useEffect(() => {
        async function loadRole() {
            const supabase = getSupabaseClient()
            const { data: { session } } = await supabase.auth.getSession()
            const role = session?.user?.user_metadata?.role
            if (role && PROMPTS_BY_ROLE[role]) setSuggestedPrompts(PROMPTS_BY_ROLE[role])
        }
        loadRole()
    }, [])

    useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streamingContent])
    useEffect(() => { if (showSearch && searchInputRef.current) searchInputRef.current.focus() }, [showSearch])

    async function loadHistory(sessId: string) {
        setIsLoadingHistory(true)
        try { const h = await getSessionHistory(sessId); if (h.messages?.length > 0) setMessages(h.messages) }
        catch { console.log('No history') }
        finally { setIsLoadingHistory(false) }
    }

    async function handleSubmit(e: FormEvent) {
        e.preventDefault()
        const msg = input.trim()
        if (!msg || isLoading) return
        setMessages(prev => [...prev, { role: 'user', content: msg, timestamp: new Date().toISOString() }])
        setInput(''); setIsLoading(true); setShowQuickActions(false)
        await handleStreamingSubmit(msg)
    }

    async function handleAutoSend(message: string) {
        if (!message || isLoading) return
        setMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date().toISOString() }])
        setIsLoading(true); setShowQuickActions(false)
        await handleStreamingSubmit(message)
    }

    async function handleRegularSubmit(userMessage: string) {
        try {
            const r = await sendChatMessage(userMessage, sessionId || undefined)
            if (r.session_id !== sessionId) { setSessionId(r.session_id); localStorage.setItem('disastergpt_session_id', r.session_id) }
            setMessages(prev => [...prev, { role: 'assistant', content: r.message, timestamp: new Date().toISOString(), context_data: r.context_data, intent: r.intent, follow_up_suggestions: r.follow_up_suggestions, action_cards: r.action_cards }])
        } catch (error) {
            const msg = error instanceof Error ? error.message : 'Unknown error'
            setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${msg}`, timestamp: new Date().toISOString() }])
        } finally { setIsLoading(false) }
    }

    async function handleStreamingSubmit(userMessage: string) {
        setIsStreaming(true); setStreamingContent('')
        let content = ''; let ctx: Record<string, unknown> | undefined; let intent = ''; let followUp: string[] | undefined; let cards: ActionCard[] | undefined
        try {
            await sendChatMessageStream(userMessage, sessionId || undefined, undefined, (event: SSEEvent) => {
                if (event.type === 'token') { content += event.data || ''; setStreamingContent(content) }
                else if (event.type === 'context_data') ctx = (event as unknown as { data: Record<string, unknown> }).data
                else if (event.type === 'meta') { intent = event.intent || ''; if (event.session_id && event.session_id !== sessionId) { setSessionId(event.session_id); localStorage.setItem('disastergpt_session_id', event.session_id) } }
                else if (event.type === 'follow_up') followUp = event.suggestions
                else if (event.type === 'action_cards') cards = event.cards
                else if (event.type === 'error') throw new Error(event.data)
            })
            setMessages(prev => [...prev, { role: 'assistant', content, timestamp: new Date().toISOString(), context_data: ctx, intent, follow_up_suggestions: followUp, action_cards: cards }])
            setStreamingContent('')
        } catch (error) {
            const msg = error instanceof Error ? error.message : 'Unknown error'
            setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${msg}`, timestamp: new Date().toISOString() }])
            setStreamingContent('')
        } finally { setIsStreaming(false); setIsLoading(false) }
    }

    function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) { if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) { e.preventDefault(); handleSubmit(e as unknown as FormEvent) } }
    function handleSuggestedPrompt(p: string) { setInput(p); textareaRef.current?.focus() }
    function handleFollowUpSelect(s: string) { setInput(s); textareaRef.current?.focus() }
    function clearChat() { const id = generateUUID(); setSessionId(id); localStorage.setItem('disastergpt_session_id', id); setMessages([]) }
    function copyToClipboard(content: string, i: number) { navigator.clipboard.writeText(content); setCopiedMessageId(i); setTimeout(() => setCopiedMessageId(null), 2000) }
    function handleFeedback(i: number, feedback: 'positive' | 'negative') { setMessages(prev => prev.map((m, j) => j === i ? { ...m, feedback: m.feedback === feedback ? null : feedback } : m)) }
    function exportChat() { const text = messages.map(m => `${m.role === 'user' ? 'You' : 'DisasterGPT'}: ${m.content}`).join('\n\n'); const blob = new Blob([text], { type: 'text/plain' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `chat-${new Date().toISOString().slice(0, 10)}.txt`; a.click(); URL.revokeObjectURL(url) }

    function renderContent(content: string) {
        const lines = content.split('\n'); const elements: React.ReactNode[] = []; let inCode = false; let code = ''; let inTable = false; let table: string[][] = []
        const flushTable = () => { if (table.length) { elements.push(<div key={`t-${elements.length}`} className="overflow-x-auto my-3"><table className="min-w-full text-sm border border-slate-200 dark:border-slate-700 rounded-lg"><thead className="bg-slate-100 dark:bg-slate-800"><tr>{table[0].map((c, i) => <th key={i} className="px-3 py-2 text-left font-semibold border-b border-slate-200 dark:border-slate-600 text-slate-800 dark:text-slate-100">{c.trim()}</th>)}</tr></thead><tbody>{table.slice(1).map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} className="px-3 py-2 border-b border-slate-100 dark:border-slate-700 text-slate-700 dark:text-slate-300">{formatInline(c.trim())}</td>)}</tr>)}</tbody></table></div>); table = [] } inTable = false }
        function formatInline(text: string): React.ReactNode {
            const parts: React.ReactNode[] = []
            const regex = /\*\*(.+?)\*\*/g
            let lastIndex = 0; let match
            while ((match = regex.exec(text)) !== null) {
                if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index))
                parts.push(<strong key={`b-${match.index}`} className="font-semibold text-slate-900 dark:text-white">{match[1]}</strong>)
                lastIndex = regex.lastIndex
            }
            if (lastIndex < text.length) parts.push(text.slice(lastIndex))
            return parts.length === 1 ? parts[0] : <>{parts}</>
        }
        lines.forEach((line, i) => {
            if (line.trim().startsWith('```')) { if (inCode) { elements.push(<div key={`c-${i}`} className="my-3 rounded-lg bg-slate-900 p-3 overflow-x-auto"><pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">{code}</pre></div>); code = '' } inCode = !inCode; return }
            if (inCode) { code += line + '\n'; return }
            if (line.includes('|') && line.trim().startsWith('|')) { if (!inTable) { flushTable(); inTable = true } const cells = line.split('|').filter(c => c.trim()); if (cells.every(c => /^[-:]+$/.test(c.trim()))) return; table.push(cells); return } else if (inTable) flushTable()
            if (line.startsWith('### ')) { elements.push(<h3 key={i} className="text-base font-bold mt-3 mb-1.5 text-slate-800 dark:text-slate-200">{formatInline(line.slice(4))}</h3>); return }
            if (line.startsWith('## ')) { elements.push(<h2 key={i} className="text-xl font-bold mt-4 mb-2 text-slate-900 dark:text-white">{formatInline(line.slice(3))}</h2>); return }
            if (line.startsWith('# ')) { elements.push(<h1 key={i} className="text-2xl font-bold mt-4 mb-2 text-slate-900 dark:text-white">{formatInline(line.slice(2))}</h1>); return }
            if (line.trim() === '---') { elements.push(<hr key={i} className="my-4 border-slate-200 dark:border-slate-700" />); return }
            if (line.trim().startsWith('- ')) { elements.push(<div key={i} className="flex items-start gap-2 mb-1 ml-2 text-sm text-slate-700 dark:text-slate-300"><span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500 shrink-0" /><span className="leading-relaxed">{formatInline(line.trim().slice(2))}</span></div>); return }
            if (line.trim() === '') { elements.push(<br key={i} />); return }
            if (line.startsWith('*') && line.endsWith('*') && !line.startsWith('**')) { elements.push(<p key={i} className="mb-2 text-xs text-slate-500 dark:text-slate-400 italic leading-relaxed">{line.slice(1, -1)}</p>); return }
            elements.push(<p key={i} className="mb-2 text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{formatInline(line)}</p>)
        })
        flushTable(); return elements
    }

    const filtered = searchQuery ? messages.filter(m => m.content.toLowerCase().includes(searchQuery.toLowerCase())) : messages

    return (
        <div className="flex flex-col h-full bg-white dark:bg-slate-900 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-slate-100 dark:from-slate-800 dark:to-slate-850">
                <div className="flex items-center gap-3">
                    <div className="relative"><div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20"><Bot className="w-5 h-5 text-white" /></div><div className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 ${isOnline ? 'bg-green-500' : 'bg-red-500'}`} /></div>
                    <div><h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">DisasterGPT {isStreaming && <span className="text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded-full animate-pulse">Streaming</span>}</h2><p className="text-xs text-slate-500">{isOnline ? <><Wifi className="w-3 h-3 inline text-green-500" /> Online</> : <><WifiOff className="w-3 h-3 inline text-red-500" /> Offline</>}</p></div>
                </div>
                <div className="flex items-center gap-1">
                    <Button variant="ghost" onClick={() => setShowSearch(!showSearch)} className={`h-8 w-8 p-0 ${showSearch ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100' : ''}`}><Search className="w-4 h-4" /></Button>
                    <Button variant="ghost" onClick={() => setShowQuickActions(!showQuickActions)} className={`h-8 w-8 p-0 ${showQuickActions ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100' : ''}`}><Zap className="w-4 h-4" /></Button>
                    <Button variant="ghost" onClick={exportChat} className="h-8 w-8 p-0"><Download className="w-4 h-4" /></Button>
                    <Button variant="ghost" onClick={clearChat} className="h-8 w-8 p-0 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"><Trash2 className="w-4 h-4" /></Button>
                    {onClose && <Button variant="ghost" onClick={onClose} className="h-8 w-8 p-0"><X className="w-4 h-4" /></Button>}
                </div>
            </div>
            {showSearch && <div className="px-4 py-2 border-b bg-slate-50 dark:bg-slate-800/50"><div className="flex items-center gap-2"><Search className="w-4 h-4 text-slate-400" /><input ref={searchInputRef} type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search messages..." className="flex-1 bg-transparent border-none outline-none text-sm text-slate-800 dark:text-white placeholder:text-slate-400" />{searchQuery && <button onClick={() => setSearchQuery('')} className="text-slate-400"><X className="w-4 h-4" /></button>}</div></div>}
            {showQuickActions && <div className="px-4 py-3 border-b bg-slate-50 dark:bg-slate-800/50"><div className="grid grid-cols-3 gap-2">{QUICK_ACTIONS.map((a, i) => <button key={i} onClick={() => { handleSuggestedPrompt(a.action); setShowQuickActions(false) }} className="flex items-center gap-2 px-3 py-2 text-xs rounded-lg bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600 text-left text-slate-700 dark:text-slate-200"><span className="text-blue-500">{a.icon}</span><span>{a.label}</span></button>)}</div></div>}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {isLoadingHistory ? <div className="flex items-center justify-center h-32"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div> :
                !filtered.length && !searchQuery && !isStreaming ? (
                    <div className="text-center py-8">
                        <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-xl"><Bot className="w-10 h-10 text-white" /></div>
                        <h3 className="text-lg font-semibold mb-2 text-slate-900 dark:text-white">Welcome to DisasterGPT!</h3>
                        <p className="text-sm text-slate-500 mb-6 max-w-xs mx-auto">Your AI assistant with streaming, follow-up suggestions, and actionable cards.</p>
                        <div className="space-y-2 max-w-sm mx-auto">{suggestedPrompts.map((p, i) => <button key={i} onClick={() => handleSuggestedPrompt(p.label)} className="flex items-center gap-3 w-full text-left px-4 py-3 text-sm rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all group text-slate-700 dark:text-slate-200"><span className="text-blue-500 group-hover:scale-110 transition-transform">{p.icon}</span><span>{p.label}</span></button>)}</div>
                    </div>
                ) : filtered.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`flex gap-2 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                            <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 shadow-md ${msg.role === 'user' ? 'bg-gradient-to-br from-slate-400 to-slate-600' : 'bg-gradient-to-br from-blue-500 to-purple-600'}`}>{msg.role === 'user' ? <User className="w-4 h-4 text-white" /> : <Bot className="w-4 h-4 text-white" />}</div>
                            <div className="group">
                                <div className={`relative rounded-2xl px-4 py-3 shadow-sm ${msg.role === 'user' ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'}`}>
                                    {msg.role === 'assistant' && <div className="flex items-center gap-2 mb-2"><span className="text-xs font-semibold bg-gradient-to-r from-blue-500 to-purple-500 bg-clip-text text-transparent">DisasterGPT</span><span className="text-xs text-slate-400">•</span><span className="text-xs text-slate-500"><Clock className="w-3 h-3 inline" /> {formatRelativeTime(msg.timestamp)}</span></div>}
                                    <div className="text-sm whitespace-pre-wrap leading-relaxed">{renderContent(msg.content)}</div>
                                    {msg.role === 'assistant' && msg.context_data && <InlineChart contextData={msg.context_data} />}
                                    {msg.role === 'assistant' && msg.action_cards && msg.action_cards.length > 0 && <div className="mt-2">{msg.action_cards.map((card, ci) => <ActionCardComponent key={ci} card={card} sessionId={sessionId || ''} onActionComplete={() => {}} onSendChat={handleAutoSend} />)}</div>}
                                    {msg.role === 'assistant' && msg.follow_up_suggestions && msg.follow_up_suggestions.length > 0 && <FollowUpChips suggestions={msg.follow_up_suggestions} onSelect={handleFollowUpSelect} />}
                                    {msg.role === 'assistant' && <div className="absolute -top-3 left-4 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 bg-white dark:bg-slate-700 rounded-full shadow-md p-1"><button onClick={() => copyToClipboard(msg.content, i)} className="p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-600">{copiedMessageId === i ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5 text-slate-500" />}</button><button onClick={() => handleFeedback(i, 'positive')} className={`p-1.5 rounded-full hover:bg-slate-100 ${msg.feedback === 'positive' ? 'text-green-500' : 'text-slate-400'}`}><ThumbsUp className="w-3.5 h-3.5" /></button><button onClick={() => handleFeedback(i, 'negative')} className={`p-1.5 rounded-full hover:bg-slate-100 ${msg.feedback === 'negative' ? 'text-red-500' : 'text-slate-400'}`}><ThumbsDown className="w-3.5 h-3.5" /></button></div>}
                                </div>
                                {msg.role === 'user' && <div className="flex items-center gap-1 mt-1 text-xs text-slate-400"><Clock className="w-3 h-3" />{formatRelativeTime(msg.timestamp)}</div>}
                            </div>
                        </div>
                    </div>
                ))}
                {isStreaming && streamingContent && <div className="flex justify-start"><div className="flex gap-2 max-w-[80%]"><div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0 shadow-md"><Bot className="w-4 h-4 text-white" /></div><div className="bg-slate-100 dark:bg-slate-800 rounded-2xl px-4 py-3 shadow-sm text-slate-900 dark:text-slate-100"><div className="flex items-center gap-2 mb-2"><span className="text-xs font-semibold bg-gradient-to-r from-blue-500 to-purple-500 bg-clip-text text-transparent">DisasterGPT</span><span className="text-xs text-green-500 animate-pulse">● streaming</span></div><div className="text-sm whitespace-pre-wrap leading-relaxed">{renderContent(streamingContent)}<span className="inline-block w-1.5 h-4 bg-blue-500 animate-pulse ml-0.5" /></div></div></div></div>}
                {isLoading && !isStreaming && <div className="flex justify-start"><div className="flex gap-2"><div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-md"><Bot className="w-4 h-4 text-white" /></div><div className="bg-slate-100 dark:bg-slate-800 rounded-2xl px-4 py-3 shadow-sm text-slate-900 dark:text-slate-100"><div className="flex gap-1"><span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" /><span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay:'150ms'}} /><span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay:'300ms'}} /></div></div></div></div>}
                <div ref={messagesEndRef} />
            </div>
            <form onSubmit={handleSubmit} className="p-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <div className="flex gap-2 items-end">
                    <div className="flex-1 relative">
                        <Textarea ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder="Ask about disasters, resources, or generate reports..." className="min-h-[52px] max-h-40 resize-none pr-12 text-sm" disabled={isLoading} />
                        <div className="absolute right-3 bottom-3"><span className="text-xs text-slate-400 hidden sm:inline"><kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">Enter</kbd></span></div>
                    </div>
                    <Button type="submit" disabled={isLoading || !input.trim()} className="h-12 w-12 p-0 bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 shadow-lg shadow-blue-500/20">{isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}</Button>
                </div>
            </form>
        </div>
    )
}

export function ChatWidget() {
    const [isOpen, setIsOpen] = useState(false)
    return (
        <>
            <Button onClick={() => setIsOpen(!isOpen)} className="fixed bottom-6 right-6 w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 shadow-xl shadow-blue-500/25 hover:shadow-blue-500/40 transition-all z-50 hover:scale-110 active:scale-95">{isOpen ? <X className="w-7 h-7 text-white" /> : <MessageCircle className="w-7 h-7 text-white" />}</Button>
            {isOpen && <div className="fixed bottom-24 right-6 w-[420px] h-[600px] rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50 bg-white dark:bg-slate-900"><DisasterGPT embedded onClose={() => setIsOpen(false)} /></div>}
        </>
    )
}