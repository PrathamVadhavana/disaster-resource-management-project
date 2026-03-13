'use client'

import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
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
    const [menuPos, setMenuPos] = useState<{ top: number; left: number; openUp: boolean } | null>(null)
    const menuRef = useRef<HTMLDivElement>(null)
    const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
    const [changingRole, setChangingRole] = useState<string | null>(null)
    const [roleReason, setRoleReason] = useState('')
    const [verifyingUser, setVerifyingUser] = useState<string | null>(null)
    const [verificationNotes, setVerificationNotes] = useState('')
    const [verifyError, setVerifyError] = useState<string | null>(null)
    const [verifySuccess, setVerifySuccess] = useState<string | null>(null)
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
    const [reviewingRequest, setReviewingRequest] = useState<string | null>(null)

    const toggleMenu = useCallback((userId: string) => {
        if (openMenu === userId) {
            setOpenMenu(null)
            setMenuPos(null)
            return
        }
        const btn = buttonRefs.current[userId]
        if (btn) {
            const rect = btn.getBoundingClientRect()
            const spaceBelow = window.innerHeight - rect.bottom
            const openUp = spaceBelow < 220
            setMenuPos({
                top: openUp ? rect.top : rect.bottom + 4,
                left: rect.right - 176, // 176px = w-44
                openUp,
            })
        }
        setOpenMenu(userId)
    }, [openMenu])

    // Close menu on click outside
    useEffect(() => {
        if (!openMenu) return
        const handleClick = (e: MouseEvent) => {
            const target = e.target as Node
            if (menuRef.current?.contains(target)) return
            const btn = buttonRefs.current[openMenu]
            if (btn?.contains(target)) return
            setOpenMenu(null)
            setMenuPos(null)
        }
        const handleScroll = () => { setOpenMenu(null); setMenuPos(null) }
        document.addEventListener('mousedown', handleClick)
        window.addEventListener('scroll', handleScroll, true)
        return () => {
            document.removeEventListener('mousedown', handleClick)
            window.removeEventListener('scroll', handleScroll, true)
        }
    }, [openMenu])

    const { data: users, isLoading } = useQuery({
        queryKey: ['admin-users'],
        queryFn: () => api.getUsers(),
        refetchInterval: 30000,
    })

    const changeRoleMutation = useMutation({
        mutationFn: ({ userId, role, reason }: { userId: string; role: string; reason?: string }) => api.updateUserRole(userId, role, reason),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
            setChangingRole(null)
            setRoleReason('')
            setOpenMenu(null)
        },
    })

    const verifyMutation = useMutation({
        mutationFn: ({ userId, status, notes }: { userId: string; status: 'verified' | 'rejected' | 'pending'; notes?: string }) =>
            api.confirmUserVerification(userId, status, notes),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
            setVerifyingUser(null)
            setVerificationNotes('')
            setVerifyError(null)
            setOpenMenu(null)
            setVerifySuccess(`User ${variables.status === 'verified' ? 'verified' : 'rejected'} successfully`)
            setTimeout(() => setVerifySuccess(null), 4000)
        },
        onError: (error: any) => {
            console.error('Verification failed:', error)
            setVerifyError(error?.message || 'Failed to update verification status. Please try again.')
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

    const reviewRoleRequestMutation = useMutation({
        mutationFn: ({ userId, requestedRole, requestId, action }: { userId: string; requestedRole: string; requestId?: string; action: 'approve' | 'reject' }) =>
            api.reviewRoleSwitchRequest(userId, {
                action,
                requested_role: requestedRole,
                request_id: requestId,
                reason: action === 'approve' ? 'Approved from admin panel' : 'Rejected from admin panel',
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] })
        },
        onSettled: () => {
            setReviewingRequest(null)
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

    const pendingRoleRequests = useMemo(() => {
        const rows: Array<{
            userId: string
            fullName: string
            email: string
            currentRole: string
            requestedRole: string
            requestedAt: string
            requestId?: string
        }> = []

        userList.forEach((user: any) => {
            const requests = user?.metadata?.pending_role_switch_requests
            if (!Array.isArray(requests)) return
            requests.forEach((req: any) => {
                if (req?.status !== 'pending') return
                rows.push({
                    userId: user.id,
                    fullName: user.full_name || 'No Name',
                    email: user.email || '—',
                    currentRole: req.current_role || user.role,
                    requestedRole: req.requested_role || '—',
                    requestedAt: req.requested_at || '',
                    requestId: req.request_id,
                })
            })
        })

        return rows.sort((a, b) => {
            const aTs = a.requestedAt ? new Date(a.requestedAt).getTime() : 0
            const bTs = b.requestedAt ? new Date(b.requestedAt).getTime() : 0
            return bTs - aTs
        })
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
            <div className="grid grid-cols-6 gap-3">
                <button onClick={() => setRoleFilter('all')}
                    className={cn(
                        'rounded-xl border p-3 text-center transition-all',
                        roleFilter === 'all' ? 'border-purple-500 bg-purple-50 dark:bg-purple-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                    )}>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">{roleCounts.all || 0}</p>
                    <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-500 dark:text-slate-400">Total Users</p>
                </button>
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

            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Pending Role Requests</h2>
                    <span className="text-xs text-slate-500">{pendingRoleRequests.length} pending</span>
                </div>
                {pendingRoleRequests.length === 0 ? (
                    <div className="px-4 py-6 text-sm text-slate-400">No pending role switch requests.</div>
                ) : (
                    <div className="divide-y divide-slate-100 dark:divide-white/5">
                        {pendingRoleRequests.map((req) => {
                            const rowKey = req.requestId || `${req.userId}-${req.requestedRole}-${req.requestedAt}`
                            const busy = reviewingRequest === rowKey && reviewRoleRequestMutation.isPending
                            return (
                                <div key={rowKey} className="px-4 py-3 flex items-center justify-between gap-4">
                                    <div>
                                        <p className="text-sm font-medium text-slate-900 dark:text-white">{req.fullName}</p>
                                        <p className="text-xs text-slate-500">{req.email}</p>
                                        <p className="text-xs text-slate-400 mt-1">
                                            {req.currentRole} → {req.requestedRole}
                                            {req.requestedAt ? ` • ${new Date(req.requestedAt).toLocaleString()}` : ''}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => {
                                                setReviewingRequest(rowKey)
                                                reviewRoleRequestMutation.mutate({
                                                    userId: req.userId,
                                                    requestedRole: req.requestedRole,
                                                    requestId: req.requestId,
                                                    action: 'approve',
                                                })
                                            }}
                                            disabled={busy}
                                            className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50"
                                        >
                                            {busy ? '...' : 'Approve'}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setReviewingRequest(rowKey)
                                                reviewRoleRequestMutation.mutate({
                                                    userId: req.userId,
                                                    requestedRole: req.requestedRole,
                                                    requestId: req.requestId,
                                                    action: 'reject',
                                                })
                                            }}
                                            disabled={busy}
                                            className="px-3 py-1.5 rounded-lg border border-red-200 dark:border-red-500/30 text-red-600 text-xs font-semibold hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-50"
                                        >
                                            {busy ? '...' : 'Reject'}
                                        </button>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>

            {/* Users Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-100 dark:border-white/5 text-left text-xs uppercase text-slate-400 tracking-wider">
                            <th className="px-4 py-3 font-semibold">User</th>
                            <th className="px-4 py-3 font-semibold">Role</th>
                            <th className="px-4 py-3 font-semibold">Verification</th>
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
                                        <div className="flex flex-col gap-1">
                                            <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-semibold uppercase w-fit', roleBadge.bg, roleBadge.text)}>
                                                {user.role}
                                            </span>
                                            {user.metadata?.role_history?.length > 0 && (
                                                <span className="text-[10px] text-slate-400 italic">Role updated</span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        {['ngo', 'donor', 'volunteer'].includes(user.role) ? (
                                            <div className="flex items-center gap-2">
                                                {(user.verification_status === 'verified' || user.metadata?.verification_status === 'verified') ? (
                                                    <span className="flex items-center gap-1 text-emerald-600 font-medium">
                                                        <CheckCircle2 className="w-3 h-3" /> Verified
                                                    </span>
                                                ) : (user.verification_status === 'rejected' || user.metadata?.verification_status === 'rejected') ? (
                                                    <span className="flex items-center gap-1 text-red-600 font-medium">
                                                        <XCircle className="w-3 h-3" /> Rejected
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center gap-1 text-amber-600 font-medium">
                                                        <Loader2 className="w-3 h-3 animate-spin" /> Pending
                                                    </span>
                                                )}
                                            </div>
                                        ) : (
                                            <span className="text-slate-400 text-xs">—</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-sm">
                                        {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                                    </td>
                                    <td className="px-4 py-3">
                                        <button
                                            ref={(el) => { buttonRefs.current[user.id] = el }}
                                            onClick={() => toggleMenu(user.id)}
                                            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"
                                        >
                                            <MoreHorizontal className="w-4 h-4 text-slate-400" />
                                        </button>
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

            {/* Context Menu Portal */}
            {openMenu && menuPos && typeof document !== 'undefined' && (() => {
                const user = userList.find((u: any) => u.id === openMenu)
                if (!user) return null
                return createPortal(
                    <div
                        ref={menuRef}
                        className="fixed z-[9999] w-44 py-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl text-xs"
                        style={{
                            top: menuPos.openUp ? undefined : menuPos.top,
                            bottom: menuPos.openUp ? window.innerHeight - menuPos.top + 4 : undefined,
                            left: menuPos.left,
                        }}
                    >
                        <a href={`mailto:${user.email}`} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                            <Mail className="w-3 h-3" /> Send Email
                        </a>
                        {['ngo', 'donor', 'volunteer'].includes(user.role) && (
                            <button onClick={() => { setVerifyingUser(user.id); setOpenMenu(null); setMenuPos(null); setVerifyError(null); }} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                                <CheckCircle2 className="w-3 h-3" /> Verify User
                            </button>
                        )}
                        <button onClick={() => { setChangingRole(user.id); setOpenMenu(null); setMenuPos(null); }} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2">
                            <Shield className="w-3 h-3" /> Change Role
                        </button>
                        <button onClick={() => { setConfirmDelete(user.id); setOpenMenu(null); setMenuPos(null); }} className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-white/5 flex items-center gap-2 text-red-600 border-t border-slate-100 dark:border-slate-700 mt-1">
                            <Ban className="w-3 h-3" /> Delete
                        </button>
                    </div>,
                    document.body
                )
            })()}

            {/* Change Role Modal */}
            {changingRole && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-sm p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Change User Role</h2>

                        <div className="mb-4">
                            <label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Reason for change</label>
                            <textarea
                                value={roleReason}
                                onChange={(e) => setRoleReason(e.target.value)}
                                placeholder="Why are you changing this role?"
                                className="w-full p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 outline-none h-20"
                            />
                        </div>

                        <div className="space-y-2">
                            {ALL_ROLES.map((role) => (
                                <button key={role} onClick={() => changeRoleMutation.mutate({ userId: changingRole, role, reason: roleReason })}
                                    disabled={changeRoleMutation.isPending}
                                    className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-purple-50 dark:hover:bg-purple-500/10 transition-colors">
                                    <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-semibold uppercase', ROLE_BADGES[role]?.bg, ROLE_BADGES[role]?.text)}>
                                        {role}
                                    </span>
                                </button>
                            ))}
                        </div>
                        <button onClick={() => { setChangingRole(null); setRoleReason(''); }} className="w-full mt-4 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium hover:bg-slate-50 dark:hover:bg-white/5">
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Verification Modal */}
            {verifyingUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-sm p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-2">User Verification</h2>
                        <p className="text-sm text-slate-500 mb-4">Set verification status and add internal notes for this organization/volunteer.</p>

                        {verifyError && (
                            <div className="mb-4 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400 text-sm">
                                {verifyError}
                            </div>
                        )}

                        <div className="mb-4">
                            <label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Internal Notes</label>
                            <textarea
                                value={verificationNotes}
                                onChange={(e) => setVerificationNotes(e.target.value)}
                                placeholder="e.g. ID verified, registration document checked..."
                                className="w-full p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 outline-none h-24"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <button onClick={() => { setVerifyError(null); verifyMutation.mutate({ userId: verifyingUser, status: 'verified', notes: verificationNotes }); }}
                                disabled={verifyMutation.isPending}
                                className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-600 text-white font-bold hover:bg-emerald-700 disabled:opacity-50 transition-all">
                                {verifyMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                                {verifyMutation.isPending ? 'Verifying...' : 'Verify'}
                            </button>
                            <button onClick={() => { setVerifyError(null); verifyMutation.mutate({ userId: verifyingUser, status: 'rejected', notes: verificationNotes }); }}
                                disabled={verifyMutation.isPending}
                                className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-red-600 text-white font-bold hover:bg-red-700 disabled:opacity-50 transition-all">
                                {verifyMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                                {verifyMutation.isPending ? 'Rejecting...' : 'Reject'}
                            </button>
                        </div>
                        <button onClick={() => { setVerifyingUser(null); setVerificationNotes(''); setVerifyError(null); }} className="w-full mt-4 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium hover:bg-slate-50 dark:hover:bg-white/5">
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Success Banner */}
            {verifySuccess && (
                <div className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl bg-emerald-600 text-white font-medium shadow-lg flex items-center gap-2 animate-in fade-in slide-in-from-bottom-4">
                    <CheckCircle2 className="w-4 h-4" />
                    {verifySuccess}
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
