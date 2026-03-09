'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { subscribeToTable } from '@/lib/realtime'
import { useAuth } from '@/lib/auth-provider'
import { cn } from '@/lib/utils'
import {
    Bell, Check, CheckCheck, X, Clock, AlertTriangle,
    CheckCircle2, XCircle, Package, Info, Volume2
} from 'lucide-react'

const TYPE_ICONS: Record<string, { icon: any; color: string }> = {
    success: { icon: CheckCircle2, color: 'text-green-500' },
    error: { icon: XCircle, color: 'text-red-500' },
    warning: { icon: AlertTriangle, color: 'text-amber-500' },
    info: { icon: Info, color: 'text-blue-500' },
    request_update: { icon: Package, color: 'text-purple-500' },
}

export function NotificationBell() {
    const { profile } = useAuth()
    const qc = useQueryClient()
    const [open, setOpen] = useState(false)
    const ref = useRef<HTMLDivElement>(null)
    const audioRef = useRef<HTMLAudioElement | null>(null)

    const { data } = useQuery({
        queryKey: ['notifications'],
        queryFn: () => api.getNotifications({ limit: 30 }),
        refetchInterval: 15000,
        enabled: !!profile,
    })

    const markReadMutation = useMutation({
        mutationFn: (ids?: string[]) => api.markNotificationsRead(ids),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
    })

    const notifications = data?.notifications || []
    const unread = data?.unread_count || 0

    // SSE realtime subscription for instant notifications
    useEffect(() => {
        if (!profile?.id) return

        const unsub = subscribeToTable('notifications', (evt) => {
            // Only care about inserts for this user
            if (evt.type !== 'INSERT') return
            if (evt.row?.user_id !== profile.id) return

            qc.invalidateQueries({ queryKey: ['notifications'] })
            // Play sound for new notification
            try {
                if (audioRef.current) {
                    audioRef.current.currentTime = 0
                    audioRef.current.play().catch(() => { })
                }
            } catch { }
            // Browser notification
            if ('Notification' in window && Notification.permission === 'granted') {
                const n = evt.row as any
                new Notification(n.title || 'New notification', {
                    body: n.message || '',
                    icon: '/favicon.ico',
                })
            }
        })

        return () => { unsub() }
    }, [profile?.id, qc])

    // Request browser notification permission
    useEffect(() => {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission()
        }
    }, [])

    // Close on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    const markAllRead = () => markReadMutation.mutate(undefined)

    const timeAgo = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime()
        const mins = Math.floor(diff / 60000)
        if (mins < 1) return 'just now'
        if (mins < 60) return `${mins}m ago`
        const hours = Math.floor(mins / 60)
        if (hours < 24) return `${hours}h ago`
        return `${Math.floor(hours / 24)}d ago`
    }

    return (
        <div ref={ref} className="relative">
            {/* Hidden audio for notification sounds */}
            <audio ref={audioRef} preload="auto">
                <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgkKuunWFAOG6OqKaBVUE8cpiurI9bQThrkKadgnxXWXJ+gYKDg4OBf359fX19fX5+fn5+fn5+fn5+fin5+" type="audio/wav" />
            </audio>

            <button
                onClick={() => setOpen(!open)}
                className="relative p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
            >
                <Bell className="w-5 h-5 text-slate-500 dark:text-slate-400" />
                {unread > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 w-5 h-5 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center animate-pulse">
                        {unread > 9 ? '9+' : unread}
                    </span>
                )}
            </button>

            {open && (
                <div className="absolute right-0 top-full mt-2 w-96 max-h-[480px] bg-white dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-2">
                    {/* Header */}
                    <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Notifications</h3>
                        <div className="flex items-center gap-2">
                            {unread > 0 && (
                                <button
                                    onClick={markAllRead}
                                    className="text-[10px] font-medium text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                                >
                                    <CheckCheck className="w-3 h-3" /> Mark all read
                                </button>
                            )}
                            <button onClick={() => setOpen(false)} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                <X className="w-3.5 h-3.5 text-slate-400" />
                            </button>
                        </div>
                    </div>

                    {/* List */}
                    <div className="overflow-y-auto max-h-[380px] divide-y divide-slate-50 dark:divide-white/5">
                        {notifications.length === 0 ? (
                            <div className="py-12 text-center">
                                <Bell className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
                                <p className="text-sm text-slate-500">No notifications yet</p>
                            </div>
                        ) : (
                            notifications.map((n: any) => {
                                const typeInfo = TYPE_ICONS[n.type] || TYPE_ICONS.info
                                const Icon = typeInfo.icon
                                return (
                                    <div
                                        key={n.id}
                                        className={cn(
                                            'px-4 py-3 flex items-start gap-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors cursor-pointer',
                                            !n.is_read && 'bg-blue-50/50 dark:bg-blue-500/5'
                                        )}
                                        onClick={() => {
                                            if (!n.is_read) markReadMutation.mutate([n.id])
                                        }}
                                    >
                                        <div className={cn('w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-slate-100 dark:bg-white/5', typeInfo.color)}>
                                            <Icon className="w-4 h-4" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">{n.title}</p>
                                                {!n.is_read && <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />}
                                            </div>
                                            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{n.message}</p>
                                            <p className="text-[10px] text-slate-400 mt-1">{timeAgo(n.created_at)}</p>
                                        </div>
                                    </div>
                                )
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
