'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    AlertTriangle, Search, Plus, Eye, MapPin,
    Calendar, Radio, Loader2, X, Trash2
} from 'lucide-react'
import { cn } from '@/lib/utils'

const SEVERITY_CONFIG: Record<string, { bg: string; text: string }> = {
    critical: { bg: 'bg-red-100 dark:bg-red-500/10', text: 'text-red-700 dark:text-red-400' },
    high: { bg: 'bg-orange-100 dark:bg-orange-500/10', text: 'text-orange-700 dark:text-orange-400' },
    medium: { bg: 'bg-amber-100 dark:bg-amber-500/10', text: 'text-amber-700 dark:text-amber-400' },
    low: { bg: 'bg-green-100 dark:bg-green-500/10', text: 'text-green-700 dark:text-green-400' },
}

const TYPES = ['earthquake', 'flood', 'hurricane', 'tornado', 'wildfire', 'tsunami', 'drought', 'landslide', 'volcano', 'other']

export default function AdminDisastersPage() {
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'resolved'>('all')
    const [showAdd, setShowAdd] = useState(false)
    const [viewDisaster, setViewDisaster] = useState<any>(null)
    const [newDisaster, setNewDisaster] = useState({
        title: '', type: 'earthquake', severity: 'medium', description: '', location_name: '',
    })

    const { data: disasters, isLoading } = useQuery({
        queryKey: ['admin-disasters'],
        queryFn: () => api.getDisasters(),
        refetchInterval: 15000,
    })

    const createMutation = useMutation({
        mutationFn: (data: any) => api.createDisaster(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-disasters'] })
            setShowAdd(false)
            setNewDisaster({ title: '', type: 'earthquake', severity: 'medium', description: '', location_name: '' })
        },
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteDisaster(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-disasters'] })
            setViewDisaster(null)
        },
    })

    const updateStatusMutation = useMutation({
        mutationFn: ({ id, status }: { id: string; status: string }) => api.updateDisaster(id, { status }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-disasters'] })
            setViewDisaster(null)
        },
    })

    const disasterList = Array.isArray(disasters) ? disasters : []

    const filtered = disasterList.filter((d: any) => {
        const matchSearch = !search ||
            (d.title || d.name || '').toLowerCase().includes(search.toLowerCase()) ||
            (d.location_name || d.location || '').toLowerCase().includes(search.toLowerCase()) ||
            (d.type || '').toLowerCase().includes(search.toLowerCase())
        const matchStatus = statusFilter === 'all' ||
            (statusFilter === 'active' && d.status === 'active') ||
            (statusFilter === 'resolved' && d.status !== 'active')
        return matchSearch && matchStatus
    })

    const stats = {
        total: disasterList.length,
        active: disasterList.filter((d: any) => d.status === 'active').length,
        critical: disasterList.filter((d: any) => d.severity === 'critical').length,
    }

    const handleCreate = () => {
        if (!newDisaster.title) return
        createMutation.mutate({
            title: newDisaster.title,
            type: newDisaster.type,
            severity: newDisaster.severity,
            description: newDisaster.description || null,
            status: 'active',
            start_date: new Date().toISOString(),
        })
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Disaster Management</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Monitor and manage all disaster events
                    </p>
                </div>
                <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 shadow-lg shadow-purple-600/20">
                    <Plus className="w-4 h-4" /> Add Disaster
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <p className="text-3xl font-bold text-slate-900 dark:text-white">{stats.total}</p>
                    <p className="text-xs text-slate-500 mt-1">Total Disasters</p>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <p className="text-3xl font-bold text-green-600">{stats.active}</p>
                    <p className="text-xs text-slate-500 mt-1">Active</p>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <p className="text-3xl font-bold text-red-600">{stats.critical}</p>
                    <p className="text-xs text-slate-500 mt-1">Critical</p>
                </div>
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search disasters by name, location, or type..."
                        className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                </div>
                <div className="flex gap-1 bg-slate-100 dark:bg-white/5 p-1 rounded-xl">
                    {(['all', 'active', 'resolved'] as const).map((s) => (
                        <button key={s} onClick={() => setStatusFilter(s)}
                            className={cn('px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all',
                                statusFilter === s ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-700')}>
                            {s}
                        </button>
                    ))}
                </div>
            </div>

            {/* List */}
            {isLoading ? (
                <div className="py-20 text-center">
                    <Loader2 className="w-8 h-8 animate-spin text-purple-500 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">Loading disasters...</p>
                </div>
            ) : filtered.length > 0 ? (
                <div className="space-y-3">
                    {filtered.map((d: any) => {
                        const sev = SEVERITY_CONFIG[d.severity] || SEVERITY_CONFIG.medium
                        return (
                            <div key={d.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-md transition-shadow">
                                <div className="flex items-start justify-between">
                                    <div className="flex items-start gap-4">
                                        <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center shrink-0', sev.bg)}>
                                            <AlertTriangle className={cn('w-5 h-5', sev.text)} />
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h3 className="text-sm font-bold text-slate-900 dark:text-white">{d.title || d.name || 'Unnamed'}</h3>
                                                {d.status === 'active' && (
                                                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-[10px] font-semibold">
                                                        <Radio className="w-2.5 h-2.5 animate-pulse" /> Active
                                                    </span>
                                                )}
                                                <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase', sev.bg, sev.text)}>
                                                    {d.severity || 'Unknown'}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                                                {(d.location_name || d.location) && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{d.location_name || d.location}</span>}
                                                {d.type && <span className="capitalize">{d.type}</span>}
                                                {d.created_at && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{new Date(d.created_at).toLocaleDateString()}</span>}
                                            </div>
                                            {d.description && <p className="text-xs text-slate-500 mt-2 line-clamp-2">{d.description}</p>}
                                        </div>
                                    </div>
                                    <button onClick={() => setViewDisaster(d)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                                        <Eye className="w-4 h-4 text-slate-400" />
                                    </button>
                                </div>
                            </div>
                        )
                    })}
                </div>
            ) : (
                <div className="py-20 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <AlertTriangle className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No disasters found</p>
                    <p className="text-xs text-slate-500 mt-1">{search ? 'Try a different search term' : 'No disasters recorded yet'}</p>
                </div>
            )}

            {/* Add Disaster Modal */}
            {showAdd && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Add Disaster</h2>
                            <button onClick={() => setShowAdd(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4 text-slate-400" /></button>
                        </div>
                        <div className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Title *</label>
                                <input value={newDisaster.title} onChange={(e) => setNewDisaster({ ...newDisaster, title: e.target.value })}
                                    placeholder="e.g. Turkey Earthquake 2026"
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Type</label>
                                    <select value={newDisaster.type} onChange={(e) => setNewDisaster({ ...newDisaster, type: e.target.value })}
                                        className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none">
                                        {TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Severity</label>
                                    <select value={newDisaster.severity} onChange={(e) => setNewDisaster({ ...newDisaster, severity: e.target.value })}
                                        className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none">
                                        {['low', 'medium', 'high', 'critical'].map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Description</label>
                                <textarea value={newDisaster.description} onChange={(e) => setNewDisaster({ ...newDisaster, description: e.target.value })} rows={3}
                                    placeholder="Describe the disaster situation..."
                                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none resize-none" />
                            </div>
                            <button onClick={handleCreate} disabled={!newDisaster.title || createMutation.isPending}
                                className="w-full h-10 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                                {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                                {createMutation.isPending ? 'Creating...' : 'Create Disaster'}
                            </button>
                            {createMutation.isError && (
                                <p className="text-xs text-red-500 text-center">{(createMutation.error as Error).message}</p>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* View Disaster Modal */}
            {viewDisaster && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg p-6">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">{viewDisaster.title || viewDisaster.name}</h2>
                            <button onClick={() => setViewDisaster(null)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4 text-slate-400" /></button>
                        </div>
                        <div className="space-y-3 text-sm">
                            <div className="flex gap-2">
                                <span className={cn('px-2 py-0.5 rounded-md text-xs font-semibold uppercase', (SEVERITY_CONFIG[viewDisaster.severity] || SEVERITY_CONFIG.medium).bg, (SEVERITY_CONFIG[viewDisaster.severity] || SEVERITY_CONFIG.medium).text)}>
                                    {viewDisaster.severity}
                                </span>
                                <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-xs font-medium capitalize">{viewDisaster.type}</span>
                                <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium', viewDisaster.status === 'active' ? 'bg-green-100 dark:bg-green-500/10 text-green-700' : 'bg-slate-100 dark:bg-slate-800 text-slate-600')}>
                                    {viewDisaster.status}
                                </span>
                            </div>
                            {viewDisaster.description && <p className="text-slate-600 dark:text-slate-400">{viewDisaster.description}</p>}
                            {(viewDisaster.location_name || viewDisaster.location) && (
                                <p className="flex items-center gap-1 text-slate-500"><MapPin className="w-3 h-3" />{viewDisaster.location_name || viewDisaster.location}</p>
                            )}
                            {viewDisaster.affected_population && <p className="text-slate-500">Affected: {viewDisaster.affected_population.toLocaleString()} people</p>}
                            {viewDisaster.casualties != null && <p className="text-slate-500">Casualties: {viewDisaster.casualties.toLocaleString()}</p>}
                            <p className="text-slate-400 text-xs">Created: {new Date(viewDisaster.created_at).toLocaleString()}</p>
                        </div>
                        <div className="flex gap-3 mt-6">
                            {viewDisaster.status === 'active' ? (
                                <button onClick={() => updateStatusMutation.mutate({ id: viewDisaster.id, status: 'resolved' })}
                                    disabled={updateStatusMutation.isPending}
                                    className="flex-1 px-4 py-2 rounded-xl bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50">
                                    Mark Resolved
                                </button>
                            ) : (
                                <button onClick={() => updateStatusMutation.mutate({ id: viewDisaster.id, status: 'active' })}
                                    disabled={updateStatusMutation.isPending}
                                    className="flex-1 px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                                    Reactivate
                                </button>
                            )}
                            <button onClick={() => deleteMutation.mutate(viewDisaster.id)}
                                disabled={deleteMutation.isPending}
                                className="px-4 py-2 rounded-xl border border-red-300 dark:border-red-500/30 text-red-600 text-sm font-medium hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-50 flex items-center gap-1">
                                <Trash2 className="w-3 h-3" /> Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
