'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { subscribeToTable } from '@/lib/realtime'
import {
    Loader2, Search, Package, Plus, AlertTriangle,
    RefreshCw, X, CheckCircle2, Archive, TrendingDown,
    Boxes, ShoppingBag,
} from 'lucide-react'

const CATEGORIES = ['Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Equipment', 'Hygiene', 'Other']

export default function NGOInventoryPage() {
    const qc = useQueryClient()
    const [search, setSearch] = useState('')
    const [catFilter, setCatFilter] = useState('')
    const [showAddModal, setShowAddModal] = useState(false)
    const [form, setForm] = useState({
        category: 'Food', resource_type: '', title: '', description: '',
        total_quantity: 10, unit: 'units', address_text: '',
    })

    const { data, isLoading, refetch } = useQuery({
        queryKey: ['ngo-inventory', catFilter],
        queryFn: () => api.getNgoInventory({ category: catFilter || undefined, limit: 200 }),
    })

    useEffect(() => {
        const unsub = subscribeToTable('available_resources', () => {
            qc.invalidateQueries({ queryKey: ['ngo-inventory'] })
        })
        return () => { unsub() }
    }, [qc])

    const addMutation = useMutation({
        mutationFn: () => api.addNgoInventoryItem(form),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-inventory'] })
            setShowAddModal(false)
            setForm({ category: 'Food', resource_type: '', title: '', description: '', total_quantity: 10, unit: 'units', address_text: '' })
        },
    })

    const items = data?.items || []
    const summary = data?.summary || {}

    const filtered = search
        ? items.filter((i: any) => (i.title || i.resource_type || i.category || '').toLowerCase().includes(search.toLowerCase()))
        : items

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
                <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
                <span className="text-sm text-slate-500">Loading inventory...</span>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Package className="w-6 h-6 text-emerald-500" />
                        Resource Inventory
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Manage your available resources, track reservations, and monitor stock levels.
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => refetch()} className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5">
                        <RefreshCw className="w-4 h-4" /> Refresh
                    </button>
                    <button onClick={() => setShowAddModal(true)}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white text-sm font-semibold hover:from-emerald-600 hover:to-teal-700 shadow-md transition-all">
                        <Plus className="w-4 h-4" /> Add Resource
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center">
                            <Boxes className="w-4 h-4 text-blue-500" />
                        </div>
                    </div>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">{summary.total_quantity || 0}</p>
                    <p className="text-xs text-slate-500">Total Stock</p>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-lg bg-orange-50 dark:bg-orange-500/10 flex items-center justify-center">
                            <ShoppingBag className="w-4 h-4 text-orange-500" />
                        </div>
                    </div>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">{summary.reserved_quantity || 0}</p>
                    <p className="text-xs text-slate-500">Reserved</p>
                </div>
                <div className="rounded-2xl border border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-500/5 p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                            <Archive className="w-4 h-4 text-emerald-500" />
                        </div>
                    </div>
                    <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{summary.available_quantity || 0}</p>
                    <p className="text-xs text-slate-500">Available</p>
                </div>
                <div className={cn(
                    'rounded-2xl border p-4',
                    (summary.low_stock_count || 0) > 0
                        ? 'border-red-200 dark:border-red-500/20 bg-red-50/50 dark:bg-red-500/5'
                        : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]'
                )}>
                    <div className="flex items-center gap-2 mb-2">
                        <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center',
                            (summary.low_stock_count || 0) > 0 ? 'bg-red-100 dark:bg-red-500/10' : 'bg-slate-100 dark:bg-white/5')}>
                            <TrendingDown className={cn('w-4 h-4', (summary.low_stock_count || 0) > 0 ? 'text-red-500' : 'text-slate-400')} />
                        </div>
                    </div>
                    <p className={cn('text-xl font-bold', (summary.low_stock_count || 0) > 0 ? 'text-red-600' : 'text-slate-900 dark:text-white')}>
                        {summary.low_stock_count || 0}
                    </p>
                    <p className="text-xs text-slate-500">Low Stock Alerts</p>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Search resources..."
                        className="w-full pl-10 pr-4 h-10 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
                </div>
                <div className="flex gap-2 flex-wrap">
                    <button onClick={() => setCatFilter('')}
                        className={cn('px-3 py-2 rounded-lg text-xs font-medium border transition-all',
                            !catFilter ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5')}>
                        All
                    </button>
                    {CATEGORIES.map(c => (
                        <button key={c} onClick={() => setCatFilter(c)}
                            className={cn('px-3 py-2 rounded-lg text-xs font-medium border transition-all',
                                catFilter === c ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-white/5')}>
                            {c}
                        </button>
                    ))}
                </div>
            </div>

            {/* Items Table */}
            {filtered.length === 0 ? (
                <div className="text-center py-16 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]">
                    <Package className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-500 font-medium">No resources in inventory</p>
                    <p className="text-sm text-slate-400 mt-1">Add resources to start managing your stock.</p>
                </div>
            ) : (
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="bg-slate-50 dark:bg-white/[0.02] border-b border-slate-200 dark:border-white/5">
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Resource</th>
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Category</th>
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-right">Total</th>
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-right">Reserved</th>
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider text-right">Available</th>
                                    <th className="px-5 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                                {filtered.map((item: any) => {
                                    const available = item.available_quantity || 0
                                    const total = item.total_quantity || 0
                                    const pct = total > 0 ? (available / total) * 100 : 0
                                    const isLow = item.is_low_stock
                                    return (
                                        <tr key={item.resource_id || item.id} className="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                            <td className="px-5 py-3">
                                                <div className="flex items-center gap-3">
                                                    {isLow && <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 animate-pulse" />}
                                                    <div>
                                                        <p className="text-sm font-medium text-slate-900 dark:text-white">{item.title || item.resource_type}</p>
                                                        {item.description && <p className="text-[10px] text-slate-400 line-clamp-1">{item.description}</p>}
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-5 py-3">
                                                <span className="text-xs font-medium text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-white/5">
                                                    {item.category}
                                                </span>
                                            </td>
                                            <td className="px-5 py-3 text-right">
                                                <span className="text-sm font-semibold text-slate-900 dark:text-white">{total}</span>
                                                <span className="text-[10px] text-slate-400 ml-0.5">{item.unit}</span>
                                            </td>
                                            <td className="px-5 py-3 text-right">
                                                <span className="text-sm font-medium text-orange-600">{item.claimed_quantity || 0}</span>
                                            </td>
                                            <td className="px-5 py-3 text-right">
                                                <span className={cn('text-sm font-bold', isLow ? 'text-red-600' : 'text-emerald-600')}>{available}</span>
                                            </td>
                                            <td className="px-5 py-3">
                                                <div className="flex items-center gap-2">
                                                    <div className="w-16 h-1.5 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                                        <div className={cn('h-full rounded-full transition-all', isLow ? 'bg-red-500' : 'bg-emerald-500')}
                                                            style={{ width: `${pct}%` }} />
                                                    </div>
                                                    <span className={cn('text-[10px] font-bold', isLow ? 'text-red-500' : 'text-emerald-500')}>
                                                        {isLow ? 'LOW' : 'OK'}
                                                    </span>
                                                </div>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Add Resource Modal */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Add Resource</h2>
                            <button onClick={() => setShowAddModal(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5">
                                <X className="w-4 h-4 text-slate-400" />
                            </button>
                        </div>
                        {addMutation.error && (
                            <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-600">
                                {(addMutation.error as Error).message}
                            </div>
                        )}
                        <form onSubmit={e => { e.preventDefault(); addMutation.mutate() }} className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Category</label>
                                <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                                    {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Resource Type</label>
                                <input value={form.resource_type} onChange={e => setForm({ ...form, resource_type: e.target.value })}
                                    placeholder="e.g. Rice, Blankets, First Aid Kit" required
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Title</label>
                                <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
                                    placeholder="e.g. 25kg Basmati Rice Bags" required
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Description</label>
                                <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                                    rows={2} placeholder="Optional description..."
                                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none resize-none" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Quantity</label>
                                    <input type="number" min="1" value={form.total_quantity}
                                        onChange={e => setForm({ ...form, total_quantity: parseInt(e.target.value) || 1 })} required
                                        className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
                                </div>
                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Unit</label>
                                    <select value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })}
                                        className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                                        <option value="units">Units</option>
                                        <option value="kg">Kilograms</option>
                                        <option value="liters">Liters</option>
                                        <option value="boxes">Boxes</option>
                                        <option value="packs">Packs</option>
                                        <option value="cartons">Cartons</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 block">Warehouse Address</label>
                                <input value={form.address_text} onChange={e => setForm({ ...form, address_text: e.target.value })}
                                    placeholder="e.g. Warehouse #3, Mumbai"
                                    className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none" />
                            </div>
                            <button type="submit" disabled={addMutation.isPending}
                                className="w-full h-11 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white text-sm font-semibold hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20">
                                {addMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                                {addMutation.isPending ? 'Adding...' : 'Add to Inventory'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    )
}
