'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    PackageSearch, Plus, Loader2, Heart,
    Truck, Layers, TrendingUp, AlertTriangle
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function ResourceSourcingManager() {
    const queryClient = useQueryClient()
    const [isCreating, setIsCreating] = useState(false)
    const [formData, setFormData] = useState({
        resource_type: 'Food',
        quantity_needed: 100,
        urgency: 'medium',
        description: '',
    })

    const { data: needs, isLoading } = useQuery({
        queryKey: ['ngo-active-needs'],
        queryFn: () => api.getActiveNeeds(),
    })

    const createMutation = useMutation({
        mutationFn: (data: any) => api.createSourcingRequest(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ngo-active-needs'] })
            queryClient.invalidateQueries({ queryKey: ['operational-pulse'] })
            setIsCreating(false)
            setFormData({ resource_type: 'Food', quantity_needed: 100, urgency: 'medium', description: '' })
        }
    })

    const handleCreate = (e: React.FormEvent) => {
        e.preventDefault()
        createMutation.mutate(formData)
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <PackageSearch className="w-5 h-5 text-amber-500" />
                    Global Resource Sourcing
                </h2>
                <button
                    onClick={() => setIsCreating(true)}
                    className="px-4 py-2 rounded-xl bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 transition-colors flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" />
                    Request Stock
                </button>
            </div>

            {isCreating && (
                <div className="p-6 rounded-2xl border-2 border-amber-500/20 bg-amber-500/5 space-y-4 shadow-sm">
                    <h3 className="font-semibold text-amber-900 dark:text-amber-300">Broadcast Inventory Need</h3>
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-slate-500 uppercase">Resource Type</label>
                                <select
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-amber-500/50"
                                    value={formData.resource_type}
                                    onChange={e => setFormData({ ...formData, resource_type: e.target.value })}
                                >
                                    <option>Food</option>
                                    <option>Water</option>
                                    <option>Medical</option>
                                    <option>Shelter</option>
                                    <option>Hygiene</option>
                                    <option>Blankets</option>
                                    <option>Power/Fuel</option>
                                </select>
                            </div>
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-slate-500 uppercase">Quantity Needed</label>
                                <input
                                    type="number"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-amber-500/50"
                                    value={formData.quantity_needed}
                                    onChange={e => setFormData({ ...formData, quantity_needed: parseInt(e.target.value) })}
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase">Urgency</label>
                            <div className="flex gap-2">
                                {['low', 'medium', 'high', 'critical'].map(u => (
                                    <button
                                        key={u}
                                        type="button"
                                        onClick={() => setFormData({ ...formData, urgency: u })}
                                        className={cn(
                                            "flex-1 py-2 rounded-xl text-xs font-bold uppercase transition-all",
                                            formData.urgency === u
                                                ? "bg-amber-500 text-white shadow-md shadow-amber-500/20"
                                                : "bg-slate-100 dark:bg-white/5 text-slate-500 hover:bg-slate-200"
                                        )}
                                    >
                                        {u}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase">Mission Context</label>
                            <textarea
                                className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-amber-500/50 min-h-[80px]"
                                placeholder="Why is this needed urgently? Which operation is this for?"
                                value={formData.description}
                                onChange={e => setFormData({ ...formData, description: e.target.value })}
                            />
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button
                                type="button"
                                onClick={() => setIsCreating(false)}
                                className="px-4 py-2 text-sm font-medium text-slate-500 hover:text-slate-700 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={createMutation.isPending}
                                className="px-6 py-2 rounded-xl bg-amber-500 text-white text-sm font-bold hover:bg-amber-600 disabled:opacity-50 transition-colors"
                            >
                                {createMutation.isPending ? 'Broadcasting...' : 'Request from Donors'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="space-y-3">
                {needs?.map((need: any) => (
                    <div key={need.id} className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] flex items-center justify-between gap-4 group hover:border-amber-500/30 transition-all">
                        <div className="flex items-center gap-4">
                            <div className={cn(
                                "w-12 h-12 rounded-xl flex items-center justify-center shrink-0",
                                need.urgency === 'critical' ? "bg-red-500/10 text-red-500" : "bg-amber-500/10 text-amber-500"
                            )}>
                                <Layers className="w-6 h-6" />
                            </div>
                            <div>
                                <h4 className="font-bold text-slate-900 dark:text-white leading-tight">
                                    {need.quantity_needed} x {need.resource_type}
                                </h4>
                                <div className="flex items-center gap-2 mt-1">
                                    <span className={cn(
                                        "text-[9px] font-black uppercase px-1.5 py-0.5 rounded border",
                                        need.urgency === 'critical' ? "border-red-500/20 text-red-500 bg-red-500/5" : "border-slate-200 dark:border-white/10 text-slate-400"
                                    )}>
                                        {need.urgency} Priority
                                    </span>
                                    <span className="text-[10px] text-slate-400 flex items-center gap-1">
                                        <TrendingUp className="w-3 h-3" />
                                        Status: {need.status.replace(/_/g, ' ')}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="flex flex-col items-end gap-1">
                            <button className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-white/5 text-[10px] font-bold text-slate-600 dark:text-slate-300 hover:bg-amber-500 hover:text-white transition-all">
                                View Pledges
                            </button>
                            <p className="text-[9px] text-slate-400">Created 2h ago</p>
                        </div>
                    </div>
                ))}
                {needs?.length === 0 && (
                    <div className="text-center py-10 border-2 border-dashed border-slate-200 dark:border-white/5 rounded-2xl">
                        <p className="text-slate-400 text-sm italic">No open sourcing requests. All missions stocked.</p>
                    </div>
                )}
            </div>
        </div>
    )
}
