'use client'

import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  MessageSquare, Send, Loader2, ThumbsUp, ThumbsDown,
  BarChart3, Database, Sparkles
} from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
  chartData?: any
  toolsCalled?: any[]
  latencyMs?: number
  queryId?: string
}

export default function NLQueryWidget() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random().toString(36).slice(2)}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const queryMutation = useMutation({
    mutationFn: (query: string) => api.askCoordinatorQuery(query, undefined, sessionId),
    onSuccess: (data) => {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: data.response || 'No response received.',
          chartData: data.chart_data,
          toolsCalled: data.tools_called,
          latencyMs: data.latency_ms,
        },
      ])
    },
    onError: (error: Error) => {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error.message}. Please check your backend configuration and try again.`,
        },
      ])
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const query = input.trim()
    if (!query || queryMutation.isPending) return

    setMessages(prev => [...prev, { role: 'user', content: query }])
    setInput('')
    queryMutation.mutate(query)
  }

  const handleSuggestion = (suggestion: string) => {
    setInput(suggestion)
    inputRef.current?.focus()
  }

  const suggestions = [
    'Which zone has the most unmet medical needs?',
    'Show resource utilization breakdown',
    'What are the active critical disasters?',
    'Compare predictions vs actual outcomes',
    'Any anomalies detected in the last 24h?',
  ]

  return (
    <div className="flex flex-col h-full rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
        <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-purple-500" />
          Chat with Your Data
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Ask questions about disasters, resources, predictions, and more
        </p>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[300px] max-h-[500px]">
        {messages.length === 0 && (
          <div className="space-y-4 pt-4">
            <div className="text-center">
              <MessageSquare className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Ask anything about your disaster management data
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-xs text-slate-400 text-center">Suggested queries:</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => handleSuggestion(s)}
                    className="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-100 dark:bg-white/5 text-slate-900 dark:text-white'
              }`}
            >
              {msg.role === 'assistant' ? (
                <div className="space-y-2">
                  <div className="text-sm whitespace-pre-wrap prose prose-sm dark:prose-invert max-w-none">
                    {msg.content}
                  </div>

                  {/* Tool calls indicator */}
                  {msg.toolsCalled && msg.toolsCalled.length > 0 && (
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-400 pt-1 border-t border-slate-200/50 dark:border-white/5">
                      <Database className="w-3 h-3" />
                      {msg.toolsCalled.length} data {msg.toolsCalled.length === 1 ? 'query' : 'queries'}
                      {msg.latencyMs && <span>· {msg.latencyMs}ms</span>}
                    </div>
                  )}

                  {/* Chart data indicator */}
                  {msg.chartData && (
                    <div className="flex items-center gap-1.5 text-[10px] text-purple-500">
                      <BarChart3 className="w-3 h-3" />
                      Chart data available
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {queryMutation.isPending && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-3 bg-slate-100 dark:bg-white/5">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                Querying data...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 px-4 py-3 border-t border-slate-100 dark:border-white/5"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about disasters, resources, predictions..."
          disabled={queryMutation.isPending}
          className="flex-1 bg-transparent text-sm text-slate-900 dark:text-white placeholder:text-slate-400 outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || queryMutation.isPending}
          className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white disabled:opacity-30 hover:bg-blue-600 transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  )
}
