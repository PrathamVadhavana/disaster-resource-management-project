'use client'

import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from 'react'
import { 
    Send, Bot, User, X, MessageCircle, Loader2, 
    Copy, Check, ThumbsUp, ThumbsDown, Search, 
    MoreVertical, Sparkles, Zap, FileText, AlertTriangle,
    Clock, Wifi, WifiOff, ChevronDown, Trash2, Download
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { getSupabaseClient } from '@/lib/supabase/client'

// Types for the chat API
interface ChatMessage {
    role: 'user' | 'assistant'
    content: string
    timestamp: string
    feedback?: 'positive' | 'negative' | null
}

interface ChatContext {
    disaster_id?: string
}

interface ChatRequest {
    message: string
    session_id?: string
    context?: ChatContext
}

interface ChatResponse {
    message: string
    session_id: string
    intent: string
    context_data?: Record<string, unknown>
}

interface SessionHistory {
    session_id: string
    messages: ChatMessage[]
    created_at: string
    message_count: number
}

// Role-aware suggested prompts
const PROMPTS_BY_ROLE: Record<string, { icon: React.ReactNode, label: string }[]> = {
    victim: [
        { icon: <AlertTriangle className="w-4 h-4" />, label: "What's the status of my requests?" },
        { icon: <Sparkles className="w-4 h-4" />, label: "How do I request food or water?" },
        { icon: <AlertTriangle className="w-4 h-4" />, label: "Are there active disasters near me?" },
        { icon: <Zap className="w-4 h-4" />, label: "What resources are available right now?" }
    ],
    ngo: [
        { icon: <FileText className="w-4 h-4" />, label: "Show me my assigned requests" },
        { icon: <Zap className="w-4 h-4" />, label: "Which requests are highest priority?" },
        { icon: <Sparkles className="w-4 h-4" />, label: "What's our current inventory status?" },
        { icon: <FileText className="w-4 h-4" />, label: "Generate a situation report" }
    ],
    volunteer: [
        { icon: <FileText className="w-4 h-4" />, label: "What are my current assignments?" },
        { icon: <AlertTriangle className="w-4 h-4" />, label: "Which disasters need volunteers?" },
        { icon: <Zap className="w-4 h-4" />, label: "Show me high-priority requests near me" },
        { icon: <Sparkles className="w-4 h-4" />, label: "What skills are most needed right now?" }
    ],
    donor: [
        { icon: <FileText className="w-4 h-4" />, label: "Show me my recent pledges" },
        { icon: <Zap className="w-4 h-4" />, label: "What resources are most needed?" },
        { icon: <AlertTriangle className="w-4 h-4" />, label: "Which disasters need urgent support?" },
        { icon: <Sparkles className="w-4 h-4" />, label: "How is my donation being used?" }
    ],
    admin: [
        { icon: <Zap className="w-4 h-4" />, label: "How many requests are pending right now?" },
        { icon: <AlertTriangle className="w-4 h-4" />, label: "What resources are running low?" },
        { icon: <FileText className="w-4 h-4" />, label: "Generate a situation report" },
        { icon: <AlertTriangle className="w-4 h-4" />, label: "Are there any active anomalies?" }
    ],
}

const DEFAULT_PROMPTS = [
    { icon: <Zap className="w-4 h-4" />, label: "How many requests are pending right now?" },
    { icon: <AlertTriangle className="w-4 h-4" />, label: "What resources are running low?" },
    { icon: <FileText className="w-4 h-4" />, label: "Generate a situation report" },
    { icon: <AlertTriangle className="w-4 h-4" />, label: "Are there any active anomalies?" }
]

// Quick action buttons
const QUICK_ACTIONS = [
    { icon: <AlertTriangle className="w-4 h-4" />, label: "Active Disasters", action: "Show me all active disasters" },
    { icon: <Zap className="w-4 h-4" />, label: "Resource Status", action: "What's our current resource status?" },
    { icon: <FileText className="w-4 h-4" />, label: "Situation Report", action: "Generate a situation report" },
    { icon: <Zap className="w-4 h-4" />, label: "Priority Requests", action: "Show me highest priority requests" },
]

// API functions
async function sendChatMessage(message: string, sessionId?: string, context?: ChatContext): Promise<ChatResponse> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const getToken = async (forceRefresh = false): Promise<string | undefined> => {
        if (forceRefresh) {
            await supabase.auth.refreshSession()
        }
        const { data: { session } } = await supabase.auth.getSession()
        return session?.access_token
    }

    const token = await getToken(false)
    const { data: { session } } = await supabase.auth.getSession()
    const userRole = session?.user?.user_metadata?.role ?? null
    const userName = session?.user?.user_metadata?.full_name ?? null
    const userId = session?.user?.id ?? null

    const doRequest = async (authToken?: string): Promise<Response> => {
        return fetch(`${API_BASE}/api/llm/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {}),
            },
            body: JSON.stringify({
                message,
                session_id: sessionId,
                context,
                user_context: { role: userRole, name: userName, user_id: userId }
            }),
        })
    }

    let response = await doRequest(token)
    if (response.status === 401) {
        const refreshedToken = await getToken(true)
        response = await doRequest(refreshedToken)
    }

    if (!response.ok) {
        const errText = await response.text()
        let detail = errText
        try {
            const parsed = JSON.parse(errText)
            if (parsed?.detail) {
                detail = String(parsed.detail)
            }
        } catch {
            // keep raw text detail
        }
        throw new Error(`Request failed (${response.status}): ${detail || 'Unknown server error'}`)
    }

    return response.json()
}

async function getSessionHistory(sessionId: string): Promise<SessionHistory> {
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const supabase = getSupabaseClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token

    const response = await fetch(`${API_BASE}/api/llm/sessions/${sessionId}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
    })

    if (!response.ok) {
        throw new Error(`Failed to get session history: ${response.statusText}`)
    }

    return response.json()
}

// Generate UUID for session
function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0
        const v = c === 'x' ? r : (r & 0x3 | 0x8)
        return v.toString(16)
    })
}

// Format relative time
function formatRelativeTime(timestamp: string): string {
    const now = new Date()
    const date = new Date(timestamp)
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
    return date.toLocaleDateString()
}

// Format full time
function formatTime(timestamp: string): string {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

interface DisasterGPTProps {
    embedded?: boolean
    onClose?: () => void
}

export function DisasterGPT({ embedded = false, onClose }: DisasterGPTProps) {
    const [sessionId, setSessionId] = useState<string | null>(null)
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [input, setInput] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [isLoadingHistory, setIsLoadingHistory] = useState(false)
    const [isCheckingLive, setIsCheckingLive] = useState(false)
    const [suggestedPrompts, setSuggestedPrompts] = useState<{ icon: React.ReactNode, label: string }[]>(DEFAULT_PROMPTS)
    const [showSearch, setShowSearch] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [showQuickActions, setShowQuickActions] = useState(false)
    const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null)
    const [isOnline, setIsOnline] = useState(true)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const searchInputRef = useRef<HTMLInputElement>(null)

    // Check online status
    useEffect(() => {
        setIsOnline(navigator.onLine)
        const handleOnline = () => setIsOnline(true)
        const handleOffline = () => setIsOnline(false)
        window.addEventListener('online', handleOnline)
        window.addEventListener('offline', handleOffline)
        return () => {
            window.removeEventListener('online', handleOnline)
            window.removeEventListener('offline', handleOffline)
        }
    }, [])

    // Initialize session on mount
    useEffect(() => {
        const storedSessionId = localStorage.getItem('disastergpt_session_id')
        
        if (storedSessionId) {
            setSessionId(storedSessionId)
            loadHistory(storedSessionId)
        } else {
            const newSessionId = generateUUID()
            setSessionId(newSessionId)
            localStorage.setItem('disastergpt_session_id', newSessionId)
        }
    }, [])

    // Load history when session changes
    useEffect(() => {
        if (sessionId) {
            loadHistory(sessionId)
        }
    }, [sessionId])

    // Load role-specific prompts
    useEffect(() => {
        async function loadRole() {
            const supabase = getSupabaseClient()
            const { data: { session } } = await supabase.auth.getSession()
            const role = session?.user?.user_metadata?.role
            if (role && PROMPTS_BY_ROLE[role]) {
                setSuggestedPrompts(PROMPTS_BY_ROLE[role])
            }
        }
        loadRole()
    }, [])

    // Scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    // Focus search when opened
    useEffect(() => {
        if (showSearch && searchInputRef.current) {
            searchInputRef.current.focus()
        }
    }, [showSearch])

    async function loadHistory(sessId: string) {
        setIsLoadingHistory(true)
        try {
            const history = await getSessionHistory(sessId)
            if (history.messages && history.messages.length > 0) {
                setMessages(history.messages)
            }
        } catch (error) {
            console.log('No history found or error loading history:', error)
        } finally {
            setIsLoadingHistory(false)
        }
    }

    async function handleSubmit(e: FormEvent) {
        e.preventDefault()
        
        const userMessage = input.trim()
        if (!userMessage || isLoading) return

        const userMsg: ChatMessage = {
            role: 'user',
            content: userMessage,
            timestamp: new Date().toISOString()
        }
        
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setIsLoading(true)
        setIsCheckingLive(true)
        setShowQuickActions(false)

        try {
            const response = await sendChatMessage(userMessage, sessionId || undefined)
            
            if (response.session_id !== sessionId) {
                setSessionId(response.session_id)
                localStorage.setItem('disastergpt_session_id', response.session_id)
            }

            const assistantMsg: ChatMessage = {
                role: 'assistant',
                content: response.message,
                timestamp: new Date().toISOString()
            }
            
            setMessages(prev => [...prev, assistantMsg])
        } catch (error) {
            console.error('Error sending message:', error)
            const message = error instanceof Error ? error.message : 'Unknown error'
            const userFacingError = message.includes('401')
                ? 'Your session expired. Please refresh the page or sign in again, then retry.'
                : `Sorry, I encountered an error: ${message}`
            const errorMsg: ChatMessage = {
                role: 'assistant',
                content: userFacingError,
                timestamp: new Date().toISOString()
            }
            setMessages(prev => [...prev, errorMsg])
        } finally {
            setIsLoading(false)
            setIsCheckingLive(false)
        }
    }

    function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault()
            handleSubmit(e as unknown as FormEvent)
        }
        // Ctrl+Shift+Enter for new line
        if (e.key === 'Enter' && e.ctrlKey && e.shiftKey) {
            // Allow default behavior (new line)
        }
    }

    function handleSuggestedPrompt(prompt: string) {
        setInput(prompt)
        textareaRef.current?.focus()
    }

    function clearChat() {
        const newSessionId = generateUUID()
        setSessionId(newSessionId)
        localStorage.setItem('disastergpt_session_id', newSessionId)
        setMessages([])
    }

    function copyToClipboard(content: string, index: number) {
        navigator.clipboard.writeText(content)
        setCopiedMessageId(index)
        setTimeout(() => setCopiedMessageId(null), 2000)
    }

    function handleFeedback(index: number, feedback: 'positive' | 'negative') {
        setMessages(prev => prev.map((msg, i) => 
            i === index ? { ...msg, feedback: msg.feedback === feedback ? null : feedback } : msg
        ))
    }

    function exportChat() {
        const chatText = messages.map(m => 
            `${m.role === 'user' ? 'You' : 'DisasterGPT'}: ${m.content}`
        ).join('\n\n')
        
        const blob = new Blob([chatText], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `disastergpt-chat-${new Date().toISOString().slice(0, 10)}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    // Enhanced markdown rendering
    function renderContent(content: string) {
        const lines = content.split('\n')
        const elements: React.ReactNode[] = []
        let inCodeBlock = false
        let codeContent = ''
        let codeLanguage = ''
        let inTable = false
        let tableRows: string[][] = []

        const flushTable = () => {
            if (tableRows.length > 0) {
                elements.push(
                    <div key={`table-${elements.length}`} className="overflow-x-auto my-3">
                        <table className="min-w-full text-sm border border-slate-200 dark:border-slate-700 rounded-lg">
                            <thead className="bg-slate-50 dark:bg-slate-800">
                                <tr>
                                    {tableRows[0].map((cell, i) => (
                                        <th key={i} className="px-3 py-2 text-left font-semibold border-b border-slate-200 dark:border-slate-700">
                                            {cell.trim()}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {tableRows.slice(1).map((row, ri) => (
                                    <tr key={ri} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                        {row.map((cell, ci) => (
                                            <td key={ci} className="px-3 py-2 border-b border-slate-100 dark:border-slate-700">
                                                {cell.trim()}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
                tableRows = []
            }
            inTable = false
        }

        lines.forEach((line, i) => {
            if (line.trim().startsWith('```')) {
                if (inCodeBlock) {
                    elements.push(
                        <div key={`code-${i}`} className="my-3 rounded-lg bg-slate-900 dark:bg-slate-950 p-3 overflow-x-auto">
                            <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">{codeContent}</pre>
                            {codeLanguage && <div className="text-xs text-slate-500 mt-1">{codeLanguage}</div>}
                        </div>
                    )
                    codeContent = ''
                    codeLanguage = ''
                } else {
                    codeLanguage = line.trim().slice(3)
                }
                inCodeBlock = !inCodeBlock
                return
            }

            if (inCodeBlock) {
                codeContent += line + '\n'
                return
            }

            // Table detection
            if (line.includes('|') && line.trim().startsWith('|')) {
                const cells = line.split('|').filter(c => c.trim() !== '')
                if (!inTable) {
                    flushTable()
                    inTable = true
                }
                tableRows.push(cells)
                return
            } else if (inTable) {
                flushTable()
            }

            // Headers
            if (line.startsWith('#### ')) {
                elements.push(<h4 key={i} className="text-base font-semibold mt-4 mb-2 text-slate-800 dark:text-slate-200">{line.replace('#### ', '')}</h4>)
                return
            }
            if (line.startsWith('### ')) {
                elements.push(<h3 key={i} className="text-lg font-semibold mt-4 mb-2 text-slate-900 dark:text-slate-100">{line.replace('### ', '')}</h3>)
                return
            }
            if (line.startsWith('## ')) {
                elements.push(<h2 key={i} className="text-xl font-bold mt-4 mb-2 text-slate-900 dark:text-slate-100">{line.replace('## ', '')}</h2>)
                return
            }
            if (line.startsWith('# ')) {
                elements.push(<h1 key={i} className="text-2xl font-bold mt-4 mb-2 text-slate-900 dark:text-slate-100">{line.replace('# ', '')}</h1>)
                return
            }

            // Bold and italic
            if (line.includes('**') || line.includes('*') || line.includes('_')) {
                const processedLine = line
                    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong class="font-bold italic">$1</strong>')
                    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold">$1</strong>')
                    .replace(/\*(.+?)\*/g, '<em class="italic">$1</em>')
                    .replace(/_(.+?)_/g, '<em class="italic">$1</em>')
                elements.push(
                    <p key={i} className="mb-2 text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: processedLine }} />
                )
                return
            }

            // List items
            if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
                elements.push(
                    <li key={i} className="ml-4 mb-1 text-sm text-slate-700 dark:text-slate-300 flex items-start">
                        <span className="mr-2 text-blue-500">•</span>
                        {line.replace(/^[\-\*]\s/, '')}
                    </li>
                )
                return
            }
            
            // Numbered list
            if (/^\d+\.\s/.test(line.trim())) {
                const match = line.trim().match(/^(\d+)\.\s(.+)$/)
                if (match) {
                    elements.push(
                        <li key={i} className="ml-4 mb-1 text-sm text-slate-700 dark:text-slate-300 list-decimal">
                            {match[2]}
                        </li>
                    )
                    return
                }
            }

            // Horizontal rule
            if (line.trim() === '---' || line.trim() === '***') {
                elements.push(<hr key={i} className="my-4 border-slate-200 dark:border-slate-700" />)
                return
            }

            // Empty line
            if (line.trim() === '') {
                elements.push(<br key={i} />)
                return
            }

            // URLs
            const urlRegex = /(https?:\/\/[^\s<]+)/g
            if (urlRegex.test(line)) {
                const parts = line.split(urlRegex)
                elements.push(
                    <p key={i} className="mb-2 text-sm">
                        {parts.map((part, j) => 
                            urlRegex.test(part) 
                                ? <a key={j} href={part} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">{part}</a>
                                : part
                        )}
                    </p>
                )
                return
            }

            // Regular text
            elements.push(<p key={i} className="mb-2 text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{line}</p>)
        })

        flushTable()
        return elements
    }

    // Filter messages by search query
    const filteredMessages = searchQuery
        ? messages.filter(m => m.content.toLowerCase().includes(searchQuery.toLowerCase()))
        : messages

    return (
            <div className="flex flex-col h-full bg-white dark:bg-slate-900 rounded-lg overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-slate-100 dark:from-slate-800 dark:to-slate-850">
                    <div className="flex items-center gap-3">
                        <div className="relative">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <Bot className="w-5 h-5 text-white" />
                            </div>
                            <div className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 ${isOnline ? 'bg-green-500' : 'bg-red-500'}`} />
                        </div>
                        <div>
                            <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                DisasterGPT
                                <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-0.5 rounded-full font-medium">
                                    AI
                                </span>
                            </h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
                                {isOnline ? (
                                    <><Wifi className="w-3 h-3 text-green-500" /> Online</>
                                ) : (
                                    <><WifiOff className="w-3 h-3 text-red-500" /> Offline</>
                                )}
                                <span className="text-slate-300 dark:text-slate-600">•</span>
                                <Clock className="w-3 h-3" />
                                {formatRelativeTime(messages[messages.length - 1]?.timestamp || new Date().toISOString())}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1">
                        <Button 
                                    variant="ghost" 
                                    onClick={() => setShowSearch(!showSearch)}
                                    className={`h-8 w-8 p-0 ${showSearch ? 'bg-slate-100 dark:bg-slate-800' : ''}`}
                                >
                                    <Search className="w-4 h-4" />
                                </Button>
                        <Button 
                                    variant="ghost" 
                                    onClick={() => setShowQuickActions(!showQuickActions)}
                                    className={`h-8 w-8 p-0 ${showQuickActions ? 'bg-slate-100 dark:bg-slate-800' : ''}`}
                                >
                                    <Zap className="w-4 h-4" />
                                </Button>
                        <Button variant="ghost" onClick={exportChat} className="h-8 w-8 p-0">
                                    <Download className="w-4 h-4" />
                                </Button>
                        <Button variant="ghost" onClick={clearChat} className="h-8 w-8 p-0 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20">
                                    <Trash2 className="w-4 h-4" />
                                </Button>
                        {onClose && (
                            <Button variant="ghost" onClick={onClose} className="h-8 w-8 p-0">
                                <X className="w-4 h-4" />
                            </Button>
                        )}
                    </div>
                </div>

                {/* Search bar */}
                {showSearch && (
                    <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                        <div className="flex items-center gap-2">
                            <Search className="w-4 h-4 text-slate-400" />
                            <input
                                ref={searchInputRef}
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Search messages..."
                                className="flex-1 bg-transparent border-none outline-none text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400"
                            />
                            {searchQuery && (
                                <button onClick={() => setSearchQuery('')} className="text-slate-400 hover:text-slate-600">
                                    <X className="w-4 h-4" />
                                </button>
                            )}
                        </div>
                    </div>
                )}

                {/* Quick actions */}
                {showQuickActions && (
                    <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                        <div className="grid grid-cols-2 gap-2">
                            {QUICK_ACTIONS.map((action, i) => (
                                <button
                                    key={i}
                                    onClick={() => {
                                        handleSuggestedPrompt(action.action)
                                        setShowQuickActions(false)
                                    }}
                                    className="flex items-center gap-2 px-3 py-2 text-xs rounded-lg bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors text-left"
                                >
                                    <span className="text-blue-500">{action.icon}</span>
                                    <span className="text-slate-700 dark:text-slate-200">{action.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {isLoadingHistory ? (
                        <div className="flex items-center justify-center h-32">
                            <div className="flex flex-col items-center gap-2">
                                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                                <p className="text-sm text-slate-500">Loading conversation...</p>
                            </div>
                        </div>
                    ) : filteredMessages.length === 0 && !searchQuery ? (
                        <div className="text-center py-8">
                            <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-xl shadow-blue-500/20">
                                <Bot className="w-10 h-10 text-white" />
                            </div>
                            <h3 className="text-lg font-semibold mb-2 text-slate-900 dark:text-white">Welcome to DisasterGPT!</h3>
                            <p className="text-sm text-slate-500 mb-6 max-w-xs mx-auto">
                                Your AI assistant for disaster management. Ask me about disasters, resources, or generate reports.
                            </p>
                            
                            <div className="space-y-2 max-w-sm mx-auto">
                                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">Suggested prompts</p>
                                {suggestedPrompts.map((prompt, i) => (
                                    <button
                                        key={i}
                                        onClick={() => handleSuggestedPrompt(prompt.label)}
                                        className="flex items-center gap-3 w-full text-left px-4 py-3 text-sm rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all group"
                                    >
                                        <span className="text-blue-500 group-hover:scale-110 transition-transform">
                                            {prompt.icon}
                                        </span>
                                        <span className="text-slate-700 dark:text-slate-200">{prompt.label}</span>
                                        <Send className="w-3 h-3 ml-auto text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : filteredMessages.length === 0 && searchQuery ? (
                        <div className="text-center py-8">
                            <Search className="w-12 h-12 mx-auto mb-4 text-slate-300" />
                            <p className="text-slate-500">No messages found for "{searchQuery}"</p>
                            <Button variant="ghost" onClick={() => setSearchQuery('')} className="mt-2">
                                Clear search
                            </Button>
                        </div>
                    ) : (
                        filteredMessages.map((msg, i) => (
                            <div
                                key={i}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}
                                style={{ animationDelay: `${i * 50}ms` }}
                            >
                                <div className={`flex gap-2 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                                    <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 shadow-md ${
                                        msg.role === 'user' 
                                            ? 'bg-gradient-to-br from-slate-400 to-slate-600 dark:from-slate-600 dark:to-slate-700' 
                                            : 'bg-gradient-to-br from-blue-500 to-purple-600'
                                    }`}>
                                        {msg.role === 'user' ? (
                                            <User className="w-4 h-4 text-white" />
                                        ) : (
                                            <Bot className="w-4 h-4 text-white" />
                                        )}
                                    </div>
                                    <div className="group">
                                        <div className={`relative rounded-2xl px-4 py-3 shadow-sm ${
                                            msg.role === 'user'
                                                ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white'
                                                : 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                                        }`}>
                                            {msg.role === 'assistant' && (
                                                <div className="flex items-center gap-2 mb-2">
                                                    <span className="text-xs font-semibold bg-gradient-to-r from-blue-500 to-purple-500 bg-clip-text text-transparent">DisasterGPT</span>
                                                    <span className="text-xs text-slate-400">•</span>
                                                    <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
                                                        <Clock className="w-3 h-3" />
                                                        {formatRelativeTime(msg.timestamp)}
                                                    </span>
                                                </div>
                                            )}
                                            <div className="text-sm whitespace-pre-wrap leading-relaxed">
                                                {renderContent(msg.content)}
                                            </div>
                                            
                                            {/* Message actions for assistant messages */}
                                            {msg.role === 'assistant' && (
                                                <div className="absolute -top-3 left-4 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 bg-white dark:bg-slate-700 rounded-full shadow-md p-1">
                                                    <button
                                                        onClick={() => copyToClipboard(msg.content, i)}
                                                        className="p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors"
                                                    >
                                                        {copiedMessageId === i ? (
                                                            <Check className="w-3.5 h-3.5 text-green-500" />
                                                        ) : (
                                                            <Copy className="w-3.5 h-3.5 text-slate-500" />
                                                        )}
                                                    </button>
                                                    <button
                                                        onClick={() => handleFeedback(i, 'positive')}
                                                        className={`p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors ${msg.feedback === 'positive' ? 'text-green-500' : 'text-slate-400'}`}
                                                    >
                                                        <ThumbsUp className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleFeedback(i, 'negative')}
                                                        className={`p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors ${msg.feedback === 'negative' ? 'text-red-500' : 'text-slate-400'}`}
                                                    >
                                                        <ThumbsDown className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                        
                                        {/* Timestamp for user messages */}
                                        {msg.role === 'user' && (
                                            <div className="flex items-center gap-1 mt-1 text-xs text-slate-400">
                                                <Clock className="w-3 h-3" />
                                                {formatRelativeTime(msg.timestamp)}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                    
                    {/* Loading indicator */}
                    {isCheckingLive && (
                        <div className="flex justify-start animate-fadeIn">
                            <div className="flex gap-2 max-w-[80%]">
                                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0 shadow-md">
                                    <Bot className="w-4 h-4 text-white" />
                                </div>
                                <div className="bg-slate-100 dark:bg-slate-800 rounded-2xl px-4 py-3 shadow-sm">
                                    <div className="flex items-center gap-2 text-sm text-slate-500">
                                        <div className="flex gap-1">
                                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </div>
                                        <span>Thinking...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                    
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <form onSubmit={handleSubmit} className="p-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                    <div className="flex gap-2 items-end">
                        <div className="flex-1 relative">
                            <Textarea
                                ref={textareaRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Ask about disasters, resources, or generate reports..."
                                className="min-h-[52px] max-h-40 resize-none pr-12 text-sm"
                                disabled={isLoading}
                            />
                            <div className="absolute right-3 bottom-3 flex items-center gap-1">
                                <span className="text-xs text-slate-400 hidden sm:inline">
                                    <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">Enter</kbd> to send
                                </span>
                            </div>
                        </div>
                        <Button 
                            type="submit" 
                            disabled={isLoading || !input.trim()} 
                            className="h-12 w-12 p-0 bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 shadow-lg shadow-blue-500/20"
                        >
                            {isLoading ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Send className="w-5 h-5" />
                            )}
                        </Button>
                    </div>
                </form>
            </div>
    )
}

// Chat Widget with Floating Button
export function ChatWidget() {
    const [isOpen, setIsOpen] = useState(false)

    return (
        <>
            {/* Floating Button */}
            <Button
                onClick={() => setIsOpen(!isOpen)}
                className="fixed bottom-6 right-6 w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 shadow-xl shadow-blue-500/25 hover:shadow-blue-500/40 transition-all z-50 hover:scale-110 active:scale-95"
            >
                {isOpen ? (
                    <X className="w-7 h-7 text-white" />
                ) : (
                    <MessageCircle className="w-7 h-7 text-white" />
                )}
            </Button>

            {/* Chat Panel */}
            {isOpen && (
                <div className="fixed bottom-24 right-6 w-[420px] h-[600px] rounded-2xl shadow-2xl shadow-slate-900/25 border border-slate-200 dark:border-slate-700 overflow-hidden z-50 bg-white dark:bg-slate-900 animate-scaleIn">
                    <DisasterGPT embedded onClose={() => setIsOpen(false)} />
                </div>
            )}
        </>
    )
}
