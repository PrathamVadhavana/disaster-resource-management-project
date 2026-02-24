'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Users, Plus, Loader2, CheckCircle2,
    XCircle, MapPin, ClipboardList, AlertCircle
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function MobilizationManager() {
    const queryClient = useQueryClient()
    const [isCreating, setIsCreating] = useState(false)
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        required_volunteers: 5,
    })

    const { data: missions, isLoading } = useQuery({
        queryKey: ['ngo-mobilizations'],
        queryFn: () => api.getActiveMissions(),
    })

    const createMutation = useMutation({
        mutationFn: (data: any) => api.createMobilization(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ngo-mobilizations'] })
            queryClient.invalidateQueries({ queryKey: ['operational-pulse'] })
            setIsCreating(false)
            setFormData({ title: '', description: '', required_volunteers: 5 })
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
                    <Users className="w-5 h-5 text-indigo-500" />
                    Volunteer Mobilization
                </h2>
                <button
                    onClick={() => setIsCreating(true)}
                    className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" />
                    New Mission
                </button>
            </div>

            {isCreating && (
                <div className="p-6 rounded-2xl border-2 border-indigo-500/20 bg-indigo-500/5 space-y-4">
                    <h3 className="font-semibold text-indigo-900 dark:text-indigo-300">Create New Deployment Mission</h3>
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase">Mission Title</label>
                            <input
                                required
                                className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-indigo-500/50"
                                placeholder="e.g. Flood Relief Team - Sector 7"
                                value={formData.title}
                                onChange={e => setFormData({ ...formData, title: e.target.value })}
                            />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-slate-500 uppercase">Required Volunteers</label>
                                <input
                                    type="number"
                                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-indigo-500/50"
                                    value={formData.required_volunteers}
                                    onChange={e => setFormData({ ...formData, required_volunteers: parseInt(e.target.value) })}
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase">Description & Objectives</label>
                            <textarea
                                className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 outline-none focus:ring-2 focus:ring-indigo-500/50 min-h-[100px]"
                                placeholder="Details about the tasks, meeting point, and necessary skills..."
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
                                className="px-6 py-2 rounded-xl bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                            >
                                {createMutation.isPending ? 'Mobilizing...' : 'Launch Mission'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {missions?.map((m: any) => (
                    <div key={m.id} className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] space-y-3">
                        <div className="flex items-start justify-between">
                            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-500">
                                <MapPin className="w-5 h-5" />
                            </div>
                            <span className={cn(
                                "text-[10px] font-bold uppercase px-2 py-0.5 rounded-full",
                                m.status === 'active' ? "bg-emerald-500/10 text-emerald-500" : "bg-slate-500/10 text-slate-500"
                            )}>
                                {m.status}
                            </span>
                        </div>
                        <div>
                            <h4 className="font-bold text-slate-900 dark:text-white leading-tight">{m.title}</h4>
                            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{m.description}</p>
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-white/5">
                            <div className="flex items-center gap-1 text-[10px] text-slate-400 font-bold uppercase">
                                <Users className="w-3 h-3" />
                                Needs {m.required_volunteers} Volunteers
                            </div>
                            <button className="text-[10px] font-bold text-indigo-500 hover:underline">Manage Team</button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
