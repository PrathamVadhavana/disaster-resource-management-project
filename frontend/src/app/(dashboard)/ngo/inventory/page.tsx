'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
    Loader2, Package, Plus, Search, Filter,
    CheckCircle2, AlertTriangle, Archive, RefreshCw, X
} from 'lucide-react'

const STATUS_OPTIONS = ['all', 'available', 'allocated', 'depleted', 'in_transit'] as const

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
    available: { label: 'Available', color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 ring-emerald-500/20' },
    allocated: { label: 'Allocated', color: 'text-blue-600 bg-blue-50 dark:bg-blue-500/10 ring-blue-500/20' },
    depleted: { label: 'Depleted', color: 'text-red-600 bg-red-50 dark:bg-red-500/10 ring-red-500/20' },
    in_transit: { label: 'In Transit', color: 'text-amber-600 bg-amber-50 dark:bg-amber-500/10 ring-amber-500/20' },
}

export default function NGOInventoryPage() {
    const [statusFilter, setStatusFilter] = useState<string>('all')
    const [search, setSearch] = useState('')
    const [showAddForm, setShowAddForm] = useState(false)
    const queryClient = useQueryClient()

    const { data: resources, isLoading } = useQuery({
        queryKey: ['ngo-inventory', statusFilter],
        queryFn: () => api.getResources(statusFilter !== 'all' ? { status: statusFilter } : {}),
        refetchInterval: 30000,
    })

    const addMutation = useMutation({
        mutationFn: (data: any) => api.createResource(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ngo-inventory'] })
            setShowAddForm(false)
        },
    })

    const resourceList = Array.isArray(resources) ? resources : []

    const filtered = search
        ? resourceList.filter((r: any) =>
            (r.name || r.type || r.resource_type || '').toLowerCase().includes(search.toLowerCase())
        )
        : resourceList

    const availableCount = resourceList.filter((r: any) => r.status === 'available').length
    const allocatedCount = resourceList.filter((r: any) => r.status === 'allocated').length
    const depletedCount = resourceList.filter((r: any) => r.status === 'depleted').length

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Inventory</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Track and manage your organization&apos;s resources.
                    </p>
                </div>
                <button
                    onClick={() => setShowAddForm(true)}
                    className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/20"
                >
                    <Plus className="w-4 h-4" /> Add Resource
                </button>
            </div>

            {/* Summary */}
            <div className="grid grid-cols-3 gap-4">
                {[
                    { label: 'Available', count: availableCount, icon: CheckCircle2, color: 'from-emerald-500 to-teal-600' },
                    { label: 'Allocated', count: allocatedCount, icon: Package, color: 'from-blue-500 to-cyan-600' },
                    { label: 'Depleted', count: depletedCount, icon: AlertTriangle, color: 'from-red-500 to-orange-600' },
                ].map((s) => {
                    const Icon = s.icon
                    return (
                        <div key={s.label} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                            <div className={cn('w-9 h-9 rounded-lg bg-gradient-to-br flex items-center justify-center mb-3', s.color)}>
                                <Icon className="w-4 h-4 text-white" />
                            </div>
                            <p className="text-xl font-bold text-slate-900 dark:text-white">{s.count}</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
                        </div>
                    )
                })}
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search resources..."
                        className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                    />
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1">
                    {STATUS_OPTIONS.map((s) => (
                        <button
                            key={s}
                            onClick={() => setStatusFilter(s)}
                            className={cn(
                                'px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all border',
                                statusFilter === s
                                    ? 'bg-blue-600 text-white border-blue-600'
                                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5'
                            )}
                        >
                            {s === 'all' ? 'All' : s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </button>
                    ))}
                </div>
            </div>

            {/* Resource Table */}
            {filtered.length === 0 ? (
                <div className="text-center py-16 px-4">
                    <Archive className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 dark:text-slate-400 font-medium">No resources found</p>
                    <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                        {search ? 'Try adjusting your search.' : 'Add resources to get started.'}
                    </p>
                </div>
            ) : (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-slate-100 dark:border-white/5">
                                    <th className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-5 py-3">Resource</th>
                                    <th className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-5 py-3">Type</th>
                                    <th className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-5 py-3">Quantity</th>
                                    <th className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-5 py-3">Status</th>
                                    <th className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-5 py-3">Priority</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                                {filtered.map((r: any) => {
                                    const st = STATUS_CONFIG[r.status] || { label: r.status || 'Unknown', color: 'text-slate-500 bg-slate-50 dark:bg-slate-800 ring-slate-500/20' }
                                    return (
                                        <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                            <td className="px-5 py-3.5">
                                                <p className="text-sm font-medium text-slate-900 dark:text-white">{r.name || r.resource_type || 'Unnamed'}</p>
                                                {r.description && <p className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{r.description}</p>}
                                            </td>
                                            <td className="px-5 py-3.5 text-sm text-slate-600 dark:text-slate-400 capitalize">{r.type || r.resource_type || '—'}</td>
                                            <td className="px-5 py-3.5 text-sm font-semibold text-slate-900 dark:text-white">{r.quantity ?? '—'}</td>
                                            <td className="px-5 py-3.5">
                                                <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-semibold ring-1 ring-inset', st.color)}>
                                                    {st.label}
                                                </span>
                                            </td>
                                            <td className="px-5 py-3.5 text-sm text-slate-600 dark:text-slate-400 capitalize">{r.priority || '—'}</td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Add Resource Modal */}
            {showAddForm && <AddResourceModal onClose={() => setShowAddForm(false)} onSubmit={(data) => addMutation.mutate(data)} isLoading={addMutation.isPending} />}
        </div>
    )
}

function AddResourceModal({ onClose, onSubmit, isLoading }: { onClose: () => void; onSubmit: (data: any) => void; isLoading: boolean }) {
    const [form, setForm] = useState({ name: '', resource_type: 'food', quantity: '', description: '', priority: 'medium' })

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        onSubmit({ ...form, quantity: parseInt(form.quantity) || 1 })
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-5">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">Add Resource</h2>
                    <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4 text-slate-400" /></button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Name</label>
                        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Type</label>
                            <select value={form.resource_type} onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                                <option value="food">Food</option>
                                <option value="water">Water</option>
                                <option value="medical">Medical</option>
                                <option value="shelter">Shelter</option>
                                <option value="clothing">Clothing</option>
                                <option value="equipment">Equipment</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Quantity</label>
                            <input type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} required
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Priority</label>
                        <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                            <option value="critical">Critical</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Description (optional)</label>
                        <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2}
                            className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none" />
                    </div>
                    <button type="submit" disabled={isLoading}
                        className="w-full h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
                        {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                        {isLoading ? 'Adding...' : 'Add Resource'}
                    </button>
                </form>
            </div>
        </div>
    )
}
