'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import { subscribeToTable } from '@/lib/realtime'
import { cn } from '@/lib/utils'
import { useState, useEffect, useRef } from 'react'
import {
    Bell, CheckCheck, X, AlertTriangle,
    CheckCircle2, XCircle, Package, Info
} from 'lucide-react'

const TYPE_ICONS: Record<string, { icon: any; color: string }> = {
    success: { icon: CheckCircle2, color: 'text-green-500' },
    error: { icon: XCircle, color: 'text-red-500' },
    warning: { icon: AlertTriangle, color: 'text-amber-500' },
    info: { icon: Info, color: 'text-blue-500' },
    request_update: { icon: Package, color: 'text-purple-500' },
    hotspot_alert: { icon: AlertTriangle, color: 'text-orange-500' },
}

export function NGOTopBar() {
    const { profile } = useAuth()
    const qc = useQueryClient()
    const [open, setOpen] = useState(false)
    const ref = useRef<HTMLDivElement>(null)
    const audioRef = useRef<HTMLAudioElement | null>(null)
    const [mounted, setMounted] = useState(false)

    useEffect(() => { setMounted(true) }, [])

    // Use the NGO-specific notification endpoint
    const { data: notifData } = useQuery({
        queryKey: ['ngo-notifications-topbar'],
        queryFn: () => api.getNgoNotifications({ limit: 30 }),
        refetchInterval: 10000,
        enabled: !!profile,
    })

    const markReadMutation = useMutation({
        mutationFn: (ids?: string[]) => api.markNgoNotificationsRead(ids),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-notifications-topbar'] })
            qc.invalidateQueries({ queryKey: ['ngo-notifications-feed'] })
            qc.invalidateQueries({ queryKey: ['ngo-notif-count'] })
        },
    })

    const notifications = notifData?.notifications || []
    const unread = notifData?.unread_count || 0

    // Track seen notification IDs for deduplication
    const seenNotifIds = useRef<Set<string>>(new Set())

    // SSE realtime subscription
    useEffect(() => {
        if (!profile?.id) return

        const unsub1 = subscribeToTable('notifications', (evt) => {
            if (evt.type !== 'INSERT') return
            if (evt.row?.user_id !== profile.id) return

            const notifId: string = evt.row?.id
            if (notifId && seenNotifIds.current.has(notifId)) return
            if (notifId) seenNotifIds.current.add(notifId)

            qc.invalidateQueries({ queryKey: ['ngo-notifications-topbar'] })
            qc.invalidateQueries({ queryKey: ['ngo-notifications-feed'] })
            qc.invalidateQueries({ queryKey: ['ngo-notif-count'] })
            try {
                if (audioRef.current) {
                    audioRef.current.currentTime = 0
                    audioRef.current.play().catch(() => { })
                }
            } catch { }
        })

        const unsub2 = subscribeToTable('ngo_alerts', (evt) => {
            if (evt.type !== 'INSERT') return
            if (evt.row?.ngo_id !== profile.id) return
            qc.invalidateQueries({ queryKey: ['ngo-notifications-topbar'] })
        })

        return () => { unsub1(); unsub2() }
    }, [profile?.id, qc])

    // Close on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    const markAllRead = () => {
        if (unread <= 0 || markReadMutation.isPending) return
        markReadMutation.mutate(undefined)
    }

    const getNotificationType = (n: any): string => {
        return n?.data?.type || n?.type || n?.alert_type || 'info'
    }

    const isNotificationRead = (n: any): boolean => {
        return Boolean(n?.read ?? n?.is_read ?? false)
    }

    const timeAgo = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime()
        const mins = Math.floor(diff / 60000)
        if (mins < 1) return 'just now'
        if (mins < 60) return `${mins}m ago`
        const hours = Math.floor(mins / 60)
        if (hours < 24) return `${hours}h ago`
        return `${Math.floor(hours / 24)}d ago`
    }

    if (!mounted) return <div className="hidden lg:block h-14" />

    return (
        <>
            {/* Hidden audio for notification sounds */}
            <audio ref={audioRef} preload="auto">
                <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgkKuunWFAOG6OqKaBVUE8cpiurI9bQThrkKadgnxXWXJ+gYKDg4OBf359fX19fX5+fn5+fn5+fn5+fin5+" type="audio/wav" />
            </audio>

            {/* Desktop top bar - hidden on mobile (mobile has its own bar in Sidebar) */}
            <div className="hidden lg:flex items-center justify-end h-14 px-6 border-b border-slate-200 dark:border-white/5 bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl sticky top-0 z-30">
                <div ref={ref} className="relative">
                    <button
                        onClick={() => setOpen(!open)}
                        className="relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-white/5 transition-all duration-200 group"
                        aria-label="Notifications"
                    >
                        <Bell className={cn(
                            "w-5 h-5 transition-colors",
                            unread > 0 ? "text-blue-500" : "text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300"
                        )} />
                        {unread > 0 && (
                            <span className="absolute -top-0.5 -right-0.5 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center animate-pulse shadow-lg shadow-red-500/30">
                                {unread > 99 ? '99+' : unread}
                            </span>
                        )}
                    </button>

                    {open && (
                        <div className="absolute right-0 top-full mt-2 w-[420px] max-h-[32rem] bg-white dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl shadow-black/10 dark:shadow-black/40 overflow-hidden z-50"
                            style={{ animation: 'fadeSlideIn 0.2s ease-out' }}
                        >
                            {/* Header */}
                            <div className="px-5 py-3.5 border-b border-slate-100 dark:border-white/5 flex items-center justify-between bg-slate-50/50 dark:bg-white/[0.02]">
                                <div className="flex items-center gap-2">
                                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Notifications</h3>
                                    {unread > 0 && (
                                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-red-500 text-white">
                                            {unread} new
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-2">
                                    {unread > 0 && (
                                        <button
                                            onClick={markAllRead}
                                            disabled={markReadMutation.isPending}
                                            className="text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors disabled:opacity-50"
                                        >
                                            <CheckCheck className="w-3.5 h-3.5" />
                                            Mark all read
                                        </button>
                                    )}
                                    <button onClick={() => setOpen(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                                        <X className="w-3.5 h-3.5 text-slate-400" />
                                    </button>
                                </div>
                            </div>

                            {/* Notification List */}
                            <div className="overflow-y-auto max-h-[26rem] divide-y divide-slate-50 dark:divide-white/5">
                                {notifications.length === 0 ? (
                                    <div className="py-16 text-center">
                                        <Bell className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
                                        <p className="text-sm text-slate-500">No notifications yet</p>
                                        <p className="text-xs text-slate-400 mt-1">You&apos;ll see alerts here when something important happens</p>
                                    </div>
                                ) : (
                                    notifications.map((n: any) => {
                                        const typeInfo = TYPE_ICONS[getNotificationType(n)] || TYPE_ICONS.info
                                        const Icon = typeInfo.icon
                                        const isRead = isNotificationRead(n)
                                        return (
                                            <div
                                                key={n.id}
                                                className={cn(
                                                    'px-5 py-3.5 flex items-start gap-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors cursor-pointer',
                                                    !isRead && 'bg-blue-50/60 dark:bg-blue-500/5'
                                                )}
                                                onClick={() => {
                                                    if (!isRead && n?.id && !markReadMutation.isPending) {
                                                        markReadMutation.mutate([n.id])
                                                    }
                                                }}
                                            >
                                                <div className={cn('w-8 h-8 rounded-full flex items-center justify-center shrink-0', typeInfo.color,
                                                    isRead ? 'bg-slate-100 dark:bg-white/5' : 'bg-blue-100/80 dark:bg-blue-500/10'
                                                )}>
                                                    <Icon className="w-4 h-4" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className={cn(
                                                            "text-xs truncate",
                                                            !isRead ? "font-bold text-slate-900 dark:text-white" : "font-medium text-slate-700 dark:text-slate-300"
                                                        )}>{n.title}</p>
                                                        {!isRead && <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />}
                                                    </div>
                                                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{n.message}</p>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        <p className="text-[10px] text-slate-400">{n.created_at ? timeAgo(n.created_at) : ''}</p>
                                                        {n.priority === 'critical' && (
                                                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/10 text-red-600 font-bold uppercase">Urgent</span>
                                                        )}
                                                        {n.severity === 'critical' && (
                                                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/10 text-red-600 font-bold uppercase">Critical</span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        )
                                    })
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Inline styles for animation */}
            <style jsx global>{`
                @keyframes fadeSlideIn {
                    from { opacity: 0; transform: translateY(-8px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </>
    )
}
