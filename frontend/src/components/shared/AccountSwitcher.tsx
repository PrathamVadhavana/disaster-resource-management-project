'use client'

import { useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth-provider'
import { ChevronDown, Check, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'

export function AccountSwitcher() {
    const { user, profile, signOut } = useAuth()
    const router = useRouter()
    const pathname = usePathname()
    const [open, setOpen] = useState(false)

    if (!user || !profile) return null

    const primaryRole = profile.role || 'victim'
    const additionalRoles: string[] = [] // Additional roles from Supabase custom claims if needed

    // De-duplicate and get all accessible roles
    const allRoles = Array.from(new Set([primaryRole, ...additionalRoles]))

    // Sort so primary is first, just convention
    allRoles.sort((a, b) => a === primaryRole ? -1 : b === primaryRole ? 1 : a.localeCompare(b))

    const handleSwitch = (targetRole: string) => {
        setOpen(false)
        if (targetRole === 'admin') router.push('/admin')
        else router.push(`/${targetRole}`)
    }

    const currentRoleActive = allRoles.find(r => pathname.startsWith(`/${r}`)) || primaryRole

    return (
        <div className="relative">
            <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-2 pt-1 pb-1 px-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                aria-expanded={open}
            >
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-500 flex items-center justify-center text-white font-bold text-sm">
                    {profile.full_name?.charAt(0) || 'U'}
                </div>
                <div className="hidden md:flex flex-col items-start translate-y-px">
                    <span className="text-sm font-semibold text-slate-900 dark:text-white leading-none">{profile.full_name}</span>
                    <span className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">{currentRoleActive} Portal</span>
                </div>
                <ChevronDown className={cn("w-4 h-4 text-slate-500 transition-transform hidden md:block", open && "rotate-180")} />
            </button>

            {open && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
                    <div className="absolute top-full right-0 mt-2 w-56 rounded-xl bg-white dark:bg-slate-900 shadow-xl border border-slate-200 dark:border-white/10 z-50 overflow-hidden transform origin-top-right transition-all">
                        <div className="px-3 py-2 border-b border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-slate-900">
                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Switch Portal</p>
                        </div>
                        <div className="p-1">
                            {allRoles.map(role => {
                                const isActive = currentRoleActive === role
                                return (
                                    <button
                                        key={role}
                                        onClick={() => handleSwitch(role)}
                                        className={cn(
                                            "w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                                            isActive
                                                ? "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400"
                                                : "text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                                        )}
                                    >
                                        <span className="capitalize">{role}</span>
                                        {isActive && <Check className="w-4 h-4" />}
                                    </button>
                                )
                            })}
                        </div>
                        <div className="border-t border-slate-100 dark:border-white/5 p-1">
                            <button
                                onClick={() => { setOpen(false); signOut(); }}
                                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                            >
                                <LogOut className="w-4 h-4" />
                                Log Out
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
