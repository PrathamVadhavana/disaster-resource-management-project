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
        const unsub = subscribeToTable('resources', () => {
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
                <div className="group relative overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.02] backdrop-blur-md p-4 transition-all hover:shadow-lg hover:-translate-y-1">
                    <div className="absolute top-0 right-0 p-2 opacity-50 group-hover:opacity-100 transition-opacity">
                        <div className="w-12 h-12 rounded-full bg-blue-500/10 blur-xl" />
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center shadow-inner">
                            <Boxes className="w-5 h-5 text-blue-500" />
                        </div>
                    </div>
                    <p className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">{summary.total_quantity || 0}</p>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1">Total Stock</p>
                </div>

                <div className="group relative overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.02] backdrop-blur-md p-4 transition-all hover:shadow-lg hover:-translate-y-1">
                    <div className="absolute top-0 right-0 p-2 opacity-50 group-hover:opacity-100 transition-opacity">
                        <div className="w-12 h-12 rounded-full bg-orange-500/10 blur-xl" />
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-orange-50 dark:bg-orange-500/10 flex items-center justify-center shadow-inner">
                            <ShoppingBag className="w-5 h-5 text-orange-500" />
                        </div>
                    </div>
                    <p className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">{summary.reserved_quantity || 0}</p>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1">Reserved</p>
                </div>

                <div className="group relative overflow-hidden rounded-2xl border border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/30 dark:bg-emerald-500/5 backdrop-blur-md p-4 transition-all hover:shadow-lg hover:-translate-y-1">
                    <div className="absolute top-0 right-0 p-2 opacity-50 group-hover:opacity-100 transition-opacity">
                        <div className="w-12 h-12 rounded-full bg-emerald-500/10 blur-xl" />
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center shadow-inner">
                            <Archive className="w-5 h-5 text-emerald-500" />
                        </div>
                    </div>
                    <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400 tracking-tight">{summary.available_quantity || 0}</p>
                    <p className="text-[10px] font-bold text-emerald-600/70 dark:text-emerald-400/50 uppercase tracking-widest mt-1">Available</p>
                </div>

                <div className={cn(
                    'group relative overflow-hidden rounded-2xl border p-4 transition-all hover:shadow-lg hover:-translate-y-1 backdrop-blur-md',
                    (summary.low_stock_count || 0) > 0
                        ? 'border-red-200 dark:border-red-500/20 bg-red-50/30 dark:bg-red-500/5'
                        : 'border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.02]'
                )}>
                    <div className="absolute top-0 right-0 p-2 opacity-50 group-hover:opacity-100 transition-opacity">
                        <div className="w-12 h-12 rounded-full bg-red-500/10 blur-xl" />
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                        <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center shadow-inner',
                            (summary.low_stock_count || 0) > 0 ? 'bg-red-100 dark:bg-red-500/10' : 'bg-slate-100 dark:bg-white/5')}>
                            <TrendingDown className={cn('w-5 h-5', (summary.low_stock_count || 0) > 0 ? 'text-red-500' : 'text-slate-400')} />
                        </div>
                    </div>
                    <p className={cn('text-2xl font-black tracking-tight', (summary.low_stock_count || 0) > 0 ? 'text-red-600' : 'text-slate-900 dark:text-white')}>
                        {summary.low_stock_count || 0}
                    </p>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1">Low Stock Alerts</p>
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
                                    const isWarning = !isLow && pct < 40

                                    return (
                                        <tr key={item.resource_id || item.id} className="group hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                            <td className="px-5 py-4">
                                                <div className="flex items-center gap-3">
                                                    <div className={cn(
                                                        "w-2 h-10 rounded-full shrink-0 transition-all group-hover:h-12",
                                                        isLow ? "bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.4)]" : 
                                                        isWarning ? "bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.4)]" : 
                                                        "bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.4)]"
                                                    )} />
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{item.title || item.resource_type}</p>
                                                        <div className="flex items-center gap-2 mt-0.5">
                                                            {item.sku && <span className="text-[9px] font-mono text-slate-400 bg-slate-100 dark:bg-white/5 px-1.5 py-0.5 rounded truncate">SKU: {item.sku}</span>}
                                                            <span className="text-[9px] text-slate-400 bg-slate-100 dark:bg-white/5 px-1.5 py-0.5 rounded uppercase">Cond: {item.item_condition || 'new'}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-5 py-4">
                                                <span className="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 px-2 py-1 rounded-md bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/5">
                                                    {item.category}
                                                </span>
                                            </td>
                                            <td className="px-5 py-4 text-right">
                                                <div className="flex flex-col items-end">
                                                    <span className="text-sm font-black text-slate-900 dark:text-white">{total}</span>
                                                    <span className="text-[10px] font-medium text-slate-400 uppercase tracking-tighter">{item.unit}</span>
                                                </div>
                                            </td>
                                            <td className="px-5 py-4 text-right">
                                                <span className="text-sm font-bold text-orange-500/80 bg-orange-500/5 px-2 py-1 rounded-lg">
                                                    {item.claimed_quantity || 0}
                                                </span>
                                            </td>
                                            <td className="px-5 py-4 text-right">
                                                <span className={cn(
                                                    'text-base font-black px-2 py-1 rounded-lg',
                                                    isLow ? 'text-red-600 bg-red-500/5' : 
                                                    isWarning ? 'text-amber-600 bg-amber-500/5' :
                                                    'text-emerald-600 bg-emerald-500/5'
                                                )}>
                                                    {available}
                                                </span>
                                            </td>
                                            <td className="px-5 py-4">
                                                <div className="flex flex-col gap-1.5 min-w-[120px]">
                                                    <div className="flex items-center justify-between">
                                                        <span className={cn(
                                                            'text-[10px] font-black tracking-widest uppercase',
                                                            isLow ? 'text-red-500' : isWarning ? 'text-amber-500' : 'text-emerald-500'
                                                        )}>
                                                            {isLow ? 'Critical' : isWarning ? 'Low Stock' : 'Optimal'}
                                                        </span>
                                                        <span className="text-[10px] font-mono text-slate-400">{Math.round(pct)}%</span>
                                                    </div>
                                                    <div className="w-full h-2 bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden shadow-inner p-[1px]">
                                                        <div className={cn(
                                                            'h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_8px_rgba(0,0,0,0.1)]',
                                                            isLow ? 'bg-gradient-to-r from-red-600 to-red-400' : 
                                                            isWarning ? 'bg-gradient-to-r from-amber-600 to-amber-400' : 
                                                            'bg-gradient-to-r from-emerald-600 to-teal-400'
                                                        )}
                                                            style={{ width: `${pct}%` }} />
                                                    </div>
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
