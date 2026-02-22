'use client'

import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import {
    Users, Search, UserPlus, Mail, MapPin,
    Shield, CheckCircle2, Clock, MoreHorizontal,
    Star, Award, Loader2, X
} from 'lucide-react'
import { cn } from '@/lib/utils'

type RoleFilter = 'all' | 'admin' | 'ngo' | 'volunteer'

const ROLE_BADGES: Record<string, { bg: string; text: string; label: string }> = {
    admin: { bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-700 dark:text-purple-400', label: 'Admin' },
    ngo: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400', label: 'NGO Staff' },
    volunteer: { bg: 'bg-emerald-100 dark:bg-emerald-500/10', text: 'text-emerald-700 dark:text-emerald-400', label: 'Volunteer' },
    donor: { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400', label: 'Donor' },
    victim: { bg: 'bg-red-100 dark:bg-red-500/10', text: 'text-red-700 dark:text-red-400', label: 'Victim' },
}

const AVATAR_COLORS = [
    'from-blue-500 to-indigo-600', 'from-emerald-500 to-teal-600', 'from-purple-500 to-pink-600',
    'from-amber-500 to-orange-600', 'from-rose-500 to-red-600', 'from-cyan-500 to-blue-600',
]

export default function NGOTeamPage() {
    const { profile } = useAuth()
    const [search, setSearch] = useState('')
    const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
    const [openMenu, setOpenMenu] = useState<string | null>(null)
    const [viewMember, setViewMember] = useState<any>(null)

    // Fetch real users from Supabase - show NGO-relevant roles
    const { data: users, isLoading } = useQuery({
        queryKey: ['ngo-team-users'],
        queryFn: () => api.getUsers(),
        refetchInterval: 30000,
    })

    const userList = Array.isArray(users) ? users : []

    // Filter to NGO-relevant team members (ngo, volunteer, admin roles)
    const teamMembers = useMemo(() => {
        return userList.filter((u: any) => {
            const relevantRoles = ['ngo', 'volunteer', 'admin']
            if (roleFilter !== 'all') return u.role === roleFilter
            return relevantRoles.includes(u.role)
        })
    }, [userList, roleFilter])

    const filtered = useMemo(() => {
        return teamMembers.filter((m: any) => {
            const matchSearch = !search ||
                (m.full_name || '').toLowerCase().includes(search.toLowerCase()) ||
                (m.email || '').toLowerCase().includes(search.toLowerCase()) ||
                (m.organization || '').toLowerCase().includes(search.toLowerCase())
            return matchSearch
        })
    }, [search, teamMembers])

    const stats = {
        total: teamMembers.length,
        ngo: teamMembers.filter((m: any) => m.role === 'ngo').length,
        volunteers: teamMembers.filter((m: any) => m.role === 'volunteer').length,
        admins: teamMembers.filter((m: any) => m.role === 'admin').length,
    }

    const getInitials = (name: string | null, email: string) => {
        if (name) return name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
        return email.slice(0, 2).toUpperCase()
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Team Management</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        {stats.total} team members across operations
                    </p>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-4 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.total}</p>
                            <p className="text-xs text-slate-500">Total Members</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                            <Shield className="w-5 h-5 text-green-600 dark:text-green-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.ngo}</p>
                            <p className="text-xs text-slate-500">NGO Staff</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <Star className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.volunteers}</p>
                            <p className="text-xs text-slate-500">Volunteers</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center">
                            <Award className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.admins}</p>
                            <p className="text-xs text-slate-500">Admins</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Search & Filters */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search by name, email, or organization..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                    <option value="all">All Roles</option>
                    <option value="ngo">NGO Staff</option>
                    <option value="volunteer">Volunteer</option>
                    <option value="admin">Admin</option>
                </select>
            </div>

            {/* Team Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {filtered.map((member: any, idx: number) => {
                    const rb = ROLE_BADGES[member.role] || ROLE_BADGES.ngo
                    const gradient = AVATAR_COLORS[idx % AVATAR_COLORS.length]
                    return (
                        <div key={member.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-lg transition-shadow group relative">
                            <div className="flex items-start gap-4">
                                <div className={cn('w-12 h-12 rounded-xl bg-gradient-to-br flex items-center justify-center text-white text-sm font-bold shrink-0', gradient)}>
                                    {getInitials(member.full_name, member.email)}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{member.full_name || 'No Name'}</h3>
                                    </div>
                                    <span className={cn('inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase mt-1', rb.bg, rb.text)}>
                                        {rb.label}
                                    </span>
                                </div>
                                <button
                                    onClick={() => setOpenMenu(openMenu === member.id ? null : member.id)}
                                    className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    <MoreHorizontal className="w-4 h-4 text-slate-400" />
                                </button>
                                {openMenu === member.id && (
                                    <div className="absolute right-5 top-14 z-20 w-36 py-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl text-xs">
                                        <a href={`mailto:${member.email}`} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                                            <Mail className="w-3 h-3" /> Email
                                        </a>
                                        <button onClick={() => { setViewMember(member); setOpenMenu(null) }} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                                            <Users className="w-3 h-3" /> View Details
                                        </button>
                                    </div>
                                )}
                            </div>

                            {/* Contact */}
                            <div className="mt-4 space-y-1.5 text-xs text-slate-500 dark:text-slate-400">
                                <div className="flex items-center gap-2"><Mail className="w-3 h-3 shrink-0" /><span className="truncate">{member.email}</span></div>
                                {member.organization && <div className="flex items-center gap-2"><Shield className="w-3 h-3 shrink-0" />{member.organization}</div>}
                                {member.phone && <div className="flex items-center gap-2"><MapPin className="w-3 h-3 shrink-0" />{member.phone}</div>}
                            </div>

                            {/* Footer */}
                            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between text-[10px] text-slate-400">
                                <div className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    Joined {member.created_at ? new Date(member.created_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : 'N/A'}
                                </div>
                                <div className="flex items-center gap-1">
                                    <CheckCircle2 className="w-3 h-3 text-green-500" />
                                    {member.is_profile_completed ? 'Profile Complete' : 'Incomplete'}
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>

            {filtered.length === 0 && (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Users className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No team members found</p>
                    <p className="text-xs text-slate-500 mt-1">Try adjusting your search or filters</p>
                </div>
            )}

            {/* View Member Modal */}
            {viewMember && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">{viewMember.full_name || 'Member Details'}</h2>
                            <button onClick={() => setViewMember(null)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4 text-slate-400" /></button>
                        </div>
                        <div className="space-y-3 text-sm">
                            <p><span className="text-slate-500">Email:</span> <span className="text-slate-900 dark:text-white">{viewMember.email}</span></p>
                            <p><span className="text-slate-500">Role:</span> <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-semibold uppercase ml-1', ROLE_BADGES[viewMember.role]?.bg, ROLE_BADGES[viewMember.role]?.text)}>{viewMember.role}</span></p>
                            {viewMember.phone && <p><span className="text-slate-500">Phone:</span> <span className="text-slate-900 dark:text-white">{viewMember.phone}</span></p>}
                            {viewMember.organization && <p><span className="text-slate-500">Organization:</span> <span className="text-slate-900 dark:text-white">{viewMember.organization}</span></p>}
                            <p><span className="text-slate-500">Joined:</span> <span className="text-slate-900 dark:text-white">{viewMember.created_at ? new Date(viewMember.created_at).toLocaleDateString() : 'N/A'}</span></p>
                            <p><span className="text-slate-500">Profile:</span> <span className={viewMember.is_profile_completed ? 'text-green-600' : 'text-amber-600'}>{viewMember.is_profile_completed ? 'Completed' : 'Incomplete'}</span></p>
                        </div>
                        <a href={`mailto:${viewMember.email}`}
                            className="mt-5 w-full h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2">
                            <Mail className="w-4 h-4" /> Send Email
                        </a>
                    </div>
                </div>
            )}
        </div>
    )
}
