'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Users, Search, Shield, MoreHorizontal,
    UserX, Mail, MapPin, Loader2,
    UserPlus, Download, Ban, CheckCircle2, XCircle
} from 'lucide-react'
import { cn } from '@/lib/utils'

type Role = 'all' | 'admin' | 'ngo' | 'donor' | 'volunteer' | 'victim'
type Status = 'all' | 'active' | 'inactive'

const ROLE_BADGES: Record<string, { bg: string; text: string }> = {
    admin: { bg: 'bg-red-100 dark:bg-red-500/10', text: 'text-red-700 dark:text-red-400' },
    ngo: { bg: 'bg-blue-100 dark:bg-blue-500/10', text: 'text-blue-700 dark:text-blue-400' },
    donor: { bg: 'bg-emerald-100 dark:bg-emerald-500/10', text: 'text-emerald-700 dark:text-emerald-400' },
    volunteer: { bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-700 dark:text-purple-400' },
    victim: { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400' },
}

const ALL_ROLES = ['admin', 'ngo', 'donor', 'volunteer', 'victim'] as const

export default function AdminUsersPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [roleFilter, setRoleFilter] = useState<Role>('all')
    const [openMenu, setOpenMenu] = useState<string | null>(null)
    const [changingRole, setChangingRole] = useState<string | null>(null)
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

    const { data: users, isLoading } = useQuery({
        queryKey: ['admin-users'],
        queryFn: () => api.getUsers(),
        refetchInterval: 30000,
    })

    const changeRoleMutation = useMutation({
        mutationFn: ({ userId, role }: { userId: string; role: string }) => api.updateUserRole(userId, role),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
            setChangingRole(null)
            setOpenMenu(null)
        },
    })

    const deleteUserMutation = useMutation({
        mutationFn: (userId: string) => api.deleteUser(userId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
            setConfirmDelete(null)
            setOpenMenu(null)
        },
    })

    const userList = Array.isArray(users) ? users : []

    const filteredUsers = useMemo(() => {
        return userList.filter((u: any) => {
            const matchSearch = !search || (u.full_name || '').toLowerCase().includes(search.toLowerCase()) || (u.email || '').toLowerCase().includes(search.toLowerCase())
            const matchRole = roleFilter === 'all' || u.role === roleFilter
            return matchSearch && matchRole
        })
    }, [search, roleFilter, userList])

    const roleCounts = useMemo(() => {
        const c: Record<string, number> = { all: userList.length }
        userList.forEach((u: any) => { c[u.role] = (c[u.role] || 0) + 1 })
        return c
    }, [userList])

    const handleExport = () => {
        const csv = ['Name,Email,Role,Created At']
        userList.forEach((u: any) => csv.push(`"${u.full_name || ''}","${u.email}","${u.role}","${u.created_at}"`))
        const blob = new Blob([csv.join('\n')], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = 'users_export.csv'; a.click()
        URL.revokeObjectURL(url)
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">User Management</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Manage {userList.length} registered users across the platform
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={handleExport} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5">
                        <Download className="w-4 h-4" /> Export
                    </button>
                </div>
            </div>

            {/* Role filter chips */}
            <div className="grid grid-cols-5 gap-3">
                {ALL_ROLES.map((role) => (
                    <button key={role} onClick={() => setRoleFilter(roleFilter === role ? 'all' : role)}
                        className={cn(
                            'rounded-xl border p-3 text-center transition-all',
                            roleFilter === role ? 'border-purple-500 bg-purple-50 dark:bg-purple-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                        )}>
                        <p className="text-xl font-bold text-slate-900 dark:text-white">{roleCounts[role] || 0}</p>
                        <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-500 dark:text-slate-400">{role}s</p>
                    </button>
                ))}
            </div>

            {/* Search */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search users by name or email..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                </div>
            </div>

            {/* Users Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-100 dark:border-white/5 text-left text-xs uppercase text-slate-400 tracking-wider">
                            <th className="px-4 py-3 font-semibold">User</th>
                            <th className="px-4 py-3 font-semibold">Role</th>
                            <th className="px-4 py-3 font-semibold">Organization</th>
                            <th className="px-4 py-3 font-semibold">Joined</th>
                            <th className="px-4 py-3 font-semibold w-12"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                        {filteredUsers.map((user: any) => {
                            const roleBadge = ROLE_BADGES[user.role] || ROLE_BADGES.victim
                            return (
                                <tr key={user.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
                                                {(user.full_name || user.email || '?').split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <p className="font-medium text-slate-900 dark:text-white">{user.full_name || 'No Name'}</p>
                                                <p className="text-xs text-slate-400">{user.email}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-semibold uppercase', roleBadge.bg, roleBadge.text)}>
                                            {user.role}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-sm">
                                        {user.organization || '—'}
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-sm">
                                        {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                                    </td>
                                    <td className="px-4 py-3 relative">
                                        <button
                                            onClick={() => setOpenMenu(openMenu === user.id ? null : user.id)}
                                            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"
                                        >
                                            <MoreHorizontal className="w-4 h-4 text-slate-400" />
                                        </button>
                                        {openMenu === user.id && (
                                            <div className="absolute right-4 top-full z-20 w-44 py-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl text-xs">
                                                <a href={`mailto:${user.email}`} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                                                    <Mail className="w-3 h-3" /> Send Email
                                                </a>
                                                <button onClick={() => setChangingRole(user.id)} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                                                    <Shield className="w-3 h-3" /> Change Role
                                                </button>
                                                <button onClick={() => setConfirmDelete(user.id)} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2 text-red-600">
                                                    <Ban className="w-3 h-3" /> Delete
                                                </button>
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
                {filteredUsers.length === 0 && (
                    <div className="py-12 text-center text-slate-400">
                        <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>No users match your filters</p>
                    </div>
                )}
            </div>

            {/* Change Role Modal */}
            {changingRole && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-sm p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Change User Role</h2>
                        <div className="space-y-2">
                            {ALL_ROLES.map((role) => (
                                <button key={role} onClick={() => changeRoleMutation.mutate({ userId: changingRole, role })}
                                    disabled={changeRoleMutation.isPending}
                                    className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-purple-50 dark:hover:bg-purple-500/10 transition-colors">
                                    <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-semibold uppercase', ROLE_BADGES[role]?.bg, ROLE_BADGES[role]?.text)}>
                                        {role}
                                    </span>
                                </button>
                            ))}
                        </div>
                        <button onClick={() => setChangingRole(null)} className="w-full mt-4 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium hover:bg-slate-50 dark:hover:bg-white/5">
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Confirm Delete Modal */}
            {confirmDelete && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-sm p-6">
                        <h2 className="text-lg font-bold text-red-600 mb-2">Delete User</h2>
                        <p className="text-sm text-slate-500 mb-4">Are you sure you want to delete this user? This action cannot be undone.</p>
                        <div className="flex gap-3">
                            <button onClick={() => setConfirmDelete(null)} className="flex-1 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium hover:bg-slate-50 dark:hover:bg-white/5">
                                Cancel
                            </button>
                            <button onClick={() => deleteUserMutation.mutate(confirmDelete)}
                                disabled={deleteUserMutation.isPending}
                                className="flex-1 px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50">
                                {deleteUserMutation.isPending ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
