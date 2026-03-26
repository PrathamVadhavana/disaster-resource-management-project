'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-provider'
import { useTheme } from 'next-themes'
import {
    LayoutDashboard, Users, Map, Brain, Activity, Settings,
    LogOut, ChevronLeft, Menu, Sun, Moon, Shield, BarChart3,
    Inbox, Scale, Clock, FlaskConical, MessageCircle,
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { getSLAViolations } from '@/lib/api/workflow'
import { useNotificationCounts } from '@/hooks/useNotificationCounts'
import { NotificationBell } from '@/components/shared/NotificationBell'

const navItems = [
    { href: '/admin', label: 'Overview', icon: LayoutDashboard },
    { href: '/admin/requests', label: 'Requests', icon: Inbox },
    { href: '/admin/users', label: 'User Management', icon: Users },
    { href: '/admin/live-map', label: 'Live Map', icon: Map },
    { href: '/admin/ai-intelligence', label: 'AI Intelligence', icon: Brain },
    { href: '/admin/disastergpt', label: 'DisasterGPT', icon: MessageCircle },
    { href: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
    { href: '/admin/sla', label: 'SLA Monitor', icon: Clock },
    { href: '/admin/what-if', label: 'What-If Analysis', icon: FlaskConical },
    { href: '/admin/fairness', label: 'Fairness', icon: Scale },
    { href: '/admin/settings', label: 'Settings', icon: Settings },
]

export function AdminSidebar() {
    const pathname = usePathname()
    const { signOut, profile } = useAuth()
    const { theme, setTheme } = useTheme()
    const [collapsed, setCollapsed] = useState(false)
    const [mounted, setMounted] = useState(false)

    useEffect(() => { setMounted(true) }, [])

    // Use the notification counts hook
    const { slaViolations, activeDisasters, pendingRequests } = useNotificationCounts()

    const badges: Record<string, number> = {
        '/admin/sla': slaViolations,
        '/admin/requests': pendingRequests,
    }

    const isActive = (href: string) => {
        if (href === '/admin') return pathname === '/admin'
        return pathname?.startsWith(href) ?? false
    }

    // Render a non-interactive shell during SSR to prevent browser extensions
    // (e.g. password managers) from injecting attributes that cause hydration mismatch
    if (!mounted) {
        return (
            <>
                <div className="lg:hidden fixed top-0 left-0 right-0 z-50 h-16 bg-white/80 dark:bg-slate-950/90 backdrop-blur-xl border-b border-slate-200 dark:border-white/5" />
                <aside className={cn(
                    'fixed top-0 left-0 z-50 h-screen flex flex-col',
                    'bg-white/95 dark:bg-slate-950/95 backdrop-blur-2xl border-r border-slate-200 dark:border-white/5',
                    'lg:translate-x-0 lg:relative lg:z-auto',
                    '-translate-x-full w-72',
                    'lg:w-72'
                )} />
            </>
        )
    }

    return (
        <>
            <div className="lg:hidden fixed top-0 left-0 right-0 z-50 h-16 bg-white/80 dark:bg-slate-950/90 backdrop-blur-xl border-b border-slate-200 dark:border-white/5 flex items-center px-4 gap-3">
                <button onClick={() => setCollapsed(!collapsed)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                    <Menu className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                </button>
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-linear-to-br from-slate-700 to-slate-900 flex items-center justify-center">
                        <Shield className="w-4 h-4 text-white" />
                    </div>
                    <span className="font-bold text-slate-900 dark:text-white text-sm">Admin Panel</span>
                    <div className="ml-auto"><NotificationBell /></div>
                </div>
            </div>

            {collapsed && (
                <div className="lg:hidden fixed inset-0 z-40 bg-black/40 dark:bg-black/60 backdrop-blur-sm" onClick={() => setCollapsed(false)} />
            )}

            <aside className={cn(
                'fixed top-0 left-0 z-50 h-screen flex flex-col transition-all duration-300 ease-in-out',
                'bg-white/95 dark:bg-slate-950/95 backdrop-blur-2xl border-r border-slate-200 dark:border-white/5',
                'lg:translate-x-0 lg:relative lg:z-auto',
                collapsed ? 'translate-x-0 w-72' : '-translate-x-full w-72',
                'lg:w-72'
            )}>
                <div className="flex items-center justify-between h-16 px-5 border-b border-slate-200 dark:border-white/5 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-linear-to-br from-slate-700 to-slate-900 dark:from-slate-600 dark:to-slate-800 flex items-center justify-center shadow-lg">
                            <Shield className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="font-bold text-slate-900 dark:text-white text-sm leading-tight">HopeInChaos</h1>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-widest">Admin Panel</p>
                        </div>
                    </div>
                    <button onClick={() => setCollapsed(false)} className="lg:hidden p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                        <ChevronLeft className="w-4 h-4 text-slate-400" />
                    </button>
                </div>

                <div className="p-4 border-b border-slate-200 dark:border-white/5 shrink-0">
                    <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-white/3 border border-slate-200 dark:border-white/5">
                        <div className="w-10 h-10 rounded-full bg-linear-to-br from-slate-600 to-slate-800 flex items-center justify-center text-white font-bold text-sm shadow-lg">
                            {profile?.full_name?.charAt(0)?.toUpperCase() || 'A'}
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{profile?.full_name || 'Administrator'}</p>
                            <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{profile?.email}</p>
                        </div>
                    </div>
                </div>

                <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
                    <p className="px-3 pt-2 pb-2 text-[10px] text-slate-400 dark:text-slate-600 uppercase tracking-widest font-semibold">System</p>
                    {navItems.map((item) => {
                        const Icon = item.icon
                        const active = isActive(item.href)
                        return (
                            <Link key={item.href} href={item.href} onClick={() => setCollapsed(false)}
                                className={cn(
                                    'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                                    active
                                        ? 'bg-linear-to-r from-slate-500/10 to-slate-400/10 dark:from-white/10 dark:to-white/5 text-slate-900 dark:text-white border border-slate-300 dark:border-white/10 shadow-sm'
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-white/4'
                                )}>
                                <Icon className={cn('w-4.5 h-4.5 shrink-0', active ? 'text-slate-700 dark:text-white' : 'text-slate-500 dark:text-slate-300')} />
                                <span className="truncate">{item.label}</span>
                                {badges[item.href] > 0 && (
                                    <span className={cn(
                                        'ml-auto min-w-5 h-5 px-1.5 rounded-full text-[10px] font-bold flex items-center justify-center',
                                        item.href === '/admin/sla'
                                            ? 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400'
                                            : 'bg-purple-100 dark:bg-purple-500/15 text-purple-600 dark:text-purple-400'
                                    )}>
                                        {badges[item.href]}
                                    </span>
                                )}
                            </Link>
                        )
                    })}
                </nav>

                <div className="p-3 border-t border-slate-200 dark:border-white/5 space-y-1 shrink-0">
                    <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-white/4 transition-all">
                        {mounted ? (theme === 'dark' ? <Sun className="w-4.5 h-4.5" /> : <Moon className="w-4.5 h-4.5" />) : <div className="w-4.5 h-4.5" />}
                        <span>{mounted ? (theme === 'dark' ? 'Light Mode' : 'Dark Mode') : 'Toggle Theme'}</span>
                    </button>
                    <button onClick={() => signOut()}
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/5 transition-all">
                        <LogOut className="w-4.5 h-4.5" />
                        <span>Sign Out</span>
                    </button>
                </div>
            </aside>
        </>
    )
}
