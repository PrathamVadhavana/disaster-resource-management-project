'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-provider'
import { useTheme } from 'next-themes'
import {
    LayoutDashboard, ListOrdered, Package, Map, Users,
    LogOut, ChevronLeft, Menu, Activity, Sun, Moon, Building2,
} from 'lucide-react'
import { useState, useEffect } from 'react'

const navItems = [
    { href: '/ngo', label: 'Overview', icon: LayoutDashboard },
    { href: '/ngo/requests', label: 'Requests Queue', icon: ListOrdered },
    { href: '/ngo/inventory', label: 'Inventory', icon: Package },
    { href: '/ngo/live-map', label: 'Live Map', icon: Map },
    { href: '/ngo/team', label: 'Team', icon: Users },
]

export function NGOSidebar() {
    const pathname = usePathname()
    const { signOut, profile } = useAuth()
    const { theme, setTheme } = useTheme()
    const [collapsed, setCollapsed] = useState(false)
    const [mounted, setMounted] = useState(false)

    useEffect(() => { setMounted(true) }, [])

    const isActive = (href: string) => {
        if (href === '/ngo') return pathname === '/ngo'
        return pathname?.startsWith(href) ?? false
    }

    return (
        <>
            {/* Mobile top bar */}
            <div className="lg:hidden fixed top-0 left-0 right-0 z-50 h-16 bg-white/80 dark:bg-slate-950/90 backdrop-blur-xl border-b border-slate-200 dark:border-white/5 flex items-center px-4 gap-3">
                <button onClick={() => setCollapsed(!collapsed)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                    <Menu className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                </button>
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
                        <Building2 className="w-4 h-4 text-white" />
                    </div>
                    <span className="font-bold text-slate-900 dark:text-white text-sm">NGO Portal</span>
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
                {/* Logo */}
                <div className="flex items-center justify-between h-16 px-5 border-b border-slate-200 dark:border-white/5 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <Building2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="font-bold text-slate-900 dark:text-white text-sm leading-tight">Relief Portal</h1>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-widest">NGO Dashboard</p>
                        </div>
                    </div>
                    <button onClick={() => setCollapsed(false)} className="lg:hidden p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                        <ChevronLeft className="w-4 h-4 text-slate-400" />
                    </button>
                </div>

                {/* User card */}
                <div className="p-4 border-b border-slate-200 dark:border-white/5 shrink-0">
                    <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200 dark:border-white/5">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500/80 to-cyan-500/80 flex items-center justify-center text-white font-bold text-sm shadow-lg">
                            {profile?.full_name?.charAt(0)?.toUpperCase() || 'N'}
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{profile?.full_name || profile?.organization || 'NGO User'}</p>
                            <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{profile?.email}</p>
                        </div>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
                    <p className="px-3 pt-2 pb-2 text-[10px] text-slate-400 dark:text-slate-600 uppercase tracking-widest font-semibold">Navigation</p>
                    {navItems.map((item) => {
                        const Icon = item.icon
                        const active = isActive(item.href)
                        return (
                            <Link key={item.href} href={item.href} onClick={() => setCollapsed(false)}
                                className={cn(
                                    'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                                    active
                                        ? 'bg-gradient-to-r from-blue-500/10 to-cyan-500/10 dark:from-blue-500/15 dark:to-cyan-500/10 text-blue-700 dark:text-white border border-blue-200 dark:border-blue-500/20 shadow-sm'
                                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-white/[0.04]'
                                )}>
                                <Icon className={cn('w-[18px] h-[18px] shrink-0', active ? 'text-blue-500 dark:text-blue-400' : '')} />
                                <span>{item.label}</span>
                            </Link>
                        )
                    })}
                </nav>

                {/* Bottom */}
                <div className="p-3 border-t border-slate-200 dark:border-white/5 space-y-1 shrink-0">
                    <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-all">
                        {mounted ? (theme === 'dark' ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />) : <div className="w-[18px] h-[18px]" />}
                        <span>{mounted ? (theme === 'dark' ? 'Light Mode' : 'Dark Mode') : 'Toggle Theme'}</span>
                    </button>
                    <button onClick={() => signOut()}
                        className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/5 transition-all">
                        <LogOut className="w-[18px] h-[18px]" />
                        <span>Sign Out</span>
                    </button>
                </div>
            </aside>
        </>
    )
}
