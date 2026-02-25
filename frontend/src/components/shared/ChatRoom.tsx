'use client'

import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { createClient } from '@/lib/supabase/client'
import { Loader2, Send, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { format } from 'date-fns'

interface ChatMessage {
    id: string;
    disaster_id: string;
    user_id: string;
    user_name: string;
    user_role: string;
    content: string;
    created_at: string;
}

export function ChatRoom({ disasterId, currentUserId }: { disasterId: string, currentUserId?: string }) {
    const [content, setContent] = useState('')
    const queryClient = useQueryClient()
    const bottomRef = useRef<HTMLDivElement>(null)
    const supabase = createClient()

    const { data: messages, isLoading } = useQuery<ChatMessage[]>({
        queryKey: ['disaster-chat', disasterId],
        queryFn: () => api.getDisasterChat(disasterId)
    })

    const mutation = useMutation({
        mutationFn: (msg: string) => api.postDisasterChat(disasterId, { content: msg }),
        onSuccess: () => {
            setContent('')
        }
    })

    useEffect(() => {
        // Scroll to bottom on load/new messages
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    useEffect(() => {
        const channel = supabase.channel(`chat-${disasterId}`)
            .on(
                'postgres_changes',
                { event: 'INSERT', schema: 'public', table: 'disaster_messages', filter: `disaster_id=eq.${disasterId}` },
                (payload) => {
                    const newMsg = payload.new as ChatMessage;
                    queryClient.setQueryData(['disaster-chat', disasterId], (old: ChatMessage[] | undefined) => {
                        if (!old) return [newMsg]
                        return [...old, newMsg]
                    })
                }
            )
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [disasterId, queryClient, supabase])

    const isMessageFromSelf = (msg: ChatMessage) => {
        // As fallback just check user_id if passed, or matching role formatting logic
        return msg.user_id === currentUserId
    }

    return (
        <div className="flex flex-col h-[500px] bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-white/10 rounded-2xl overflow-hidden shadow-lg">
            <div className="p-4 bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <MessageSquare className="w-5 h-5 text-blue-500" />
                    <h3 className="font-semibold text-slate-900 dark:text-white">Field Operations Comms</h3>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {isLoading ? (
                    <div className="flex justify-center h-full items-center text-slate-400">
                        <Loader2 className="w-6 h-6 animate-spin" />
                    </div>
                ) : messages?.length === 0 ? (
                    <div className="flex justify-center h-full items-center text-slate-400 text-sm">
                        No messages yet. Start the coordination.
                    </div>
                ) : (
                    messages?.map(msg => (
                        <div key={msg.id} className={cn("flex flex-col max-w-[80%]", isMessageFromSelf(msg) ? "ml-auto items-end" : "mr-auto items-start")}>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-slate-700 dark:text-slate-300 capitalize">{msg.user_name}</span>
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-semibold uppercase">{msg.user_role}</span>
                            </div>
                            <div className={cn("px-4 py-2 rounded-2xl text-sm",
                                isMessageFromSelf(msg)
                                    ? "bg-blue-600 text-white rounded-tr-sm"
                                    : "bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-white/10 rounded-tl-sm"
                            )}>
                                {msg.content}
                            </div>
                            <span className="text-[10px] text-slate-400 mt-1">{format(new Date(msg.created_at), 'h:mm a')}</span>
                        </div>
                    ))
                )}
                <div ref={bottomRef} />
            </div>

            <div className="p-3 bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-white/10">
                <form
                    onSubmit={(e) => {
                        e.preventDefault()
                        if (content.trim()) mutation.mutate(content.trim())
                    }}
                    className="flex gap-2"
                >
                    <input
                        type="text"
                        value={content}
                        onChange={e => setContent(e.target.value)}
                        placeholder="Broadcast message to task force..."
                        className="flex-1 h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        disabled={mutation.isPending}
                    />
                    <button
                        type="submit"
                        disabled={!content.trim() || mutation.isPending}
                        className="h-10 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl flex items-center justify-center transition-colors disabled:opacity-50"
                    >
                        {mutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                    </button>
                </form>
            </div>
        </div>
    )
}
