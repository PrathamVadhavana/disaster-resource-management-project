'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Loader2, Save, CheckCircle2, User, Mail, Phone, Building2, ArrowRightLeft } from 'lucide-react'

const SWITCHABLE_ROLES = ['victim', 'volunteer', 'ngo'] as const

export default function DonorProfilePage() {
    const queryClient = useQueryClient()
    const [saved, setSaved] = useState(false)
    const [switchError, setSwitchError] = useState('')
    const [switchMessage, setSwitchMessage] = useState('')

    const { data: profile, isLoading } = useQuery({
        queryKey: ['my-profile'],
        queryFn: () => api.getMyProfile(),
    })

    const [fullName, setFullName] = useState('')
    const [phone, setPhone] = useState('')
    const [organization, setOrganization] = useState('')

    useEffect(() => {
        if (profile) {
            setFullName(profile.full_name || profile.display_name || '')
            setPhone(profile.phone || '')
            setOrganization(profile.organization || '')
        }
    }, [profile])

    const updateMut = useMutation({
        mutationFn: (data: Record<string, unknown>) => api.updateMyProfile(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['my-profile'] })
            setSaved(true)
            setTimeout(() => setSaved(false), 3000)
        },
    })

    const switchRoleMut = useMutation({
        mutationFn: (newRole: string) => api.switchRole(newRole),
        onMutate: () => {
            setSwitchError('')
            setSwitchMessage('')
        },
        onSuccess: (resp: any) => {
            if (resp?.status === 'switched') {
                window.location.href = '/'
                return
            }
            setSwitchMessage(resp?.message || 'Role switch request submitted. Waiting for admin approval.')
        },
        onError: (err: any) => {
            setSwitchError(err?.message || 'Failed to switch role')
        },
    })

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        updateMut.mutate({
            full_name: fullName,
            phone,
            organization,
        })
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6 max-w-2xl">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <User className="w-6 h-6 text-emerald-500" />
                    My Profile
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your donor profile and preferences</p>
            </div>

            {saved && (
                <div className="flex items-center gap-2 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-sm">
                    <CheckCircle2 className="w-4 h-4" /> Profile updated successfully
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Basic Information</h2>
                    </div>
                    <div className="p-5 space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                    <User className="w-3.5 h-3.5" /> Full Name
                                </label>
                                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30" />
                            </div>
                            <div>
                                <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                    <Phone className="w-3.5 h-3.5" /> Phone
                                </label>
                                <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91 ..."
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30" />
                            </div>
                        </div>
                        <div>
                            <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                <Mail className="w-3.5 h-3.5" /> Email
                            </label>
                            <input type="email" value={profile?.email || ''} disabled
                                className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 text-slate-500 text-sm cursor-not-allowed" />
                        </div>
                        <div>
                            <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                                <Building2 className="w-3.5 h-3.5" /> Organization (optional)
                            </label>
                            <input type="text" value={organization} onChange={e => setOrganization(e.target.value)} placeholder="Company or NGO name"
                                className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30" />
                        </div>
                    </div>
                </div>

                <button type="submit" disabled={updateMut.isPending}
                    className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-sm font-semibold hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50 transition-all">
                    {updateMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    Save Changes
                </button>
            </form>

            {/* Role Switching */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                    <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                        <ArrowRightLeft className="w-4 h-4" /> Switch Role
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">Victim switches happen instantly. Other role switches need admin approval.</p>
                </div>
                <div className="p-5 space-y-3">
                    {switchError && (
                        <p className="text-xs text-red-500 mb-2">{switchError}</p>
                    )}
                    {switchMessage && (
                        <p className="text-xs text-emerald-500 mb-2">{switchMessage}</p>
                    )}
                    <div className="flex gap-3">
                        {SWITCHABLE_ROLES.map(role => {
                            return (
                                <button key={role} onClick={() => switchRoleMut.mutate(role)}
                                    disabled={switchRoleMut.isPending}
                                    className={cn(
                                        "flex-1 py-3 rounded-xl border border-slate-200 dark:border-white/10 text-sm font-medium transition-all capitalize disabled:opacity-50",
                                        "text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5"
                                    )}>
                                    Switch to {role}
                                </button>
                            )
                        })}
                    </div>
                </div>
            </div>
        </div>
    )
}
