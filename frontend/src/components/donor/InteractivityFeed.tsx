'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Heart, Sparkles, Building2, User,
    Zap, ArrowRight, Check, PackageSearch,
    ShieldCheck, Loader2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState } from 'react'

export function DonorInteractivityFeed() {
    const queryClient = useQueryClient()
    const [selectedNeed, setSelectedNeed] = useState<any>(null)
    const [pledgeQty, setPledgeQty] = useState(1)
    const [view, setView] = useState<'ngo' | 'direct'>('ngo')

    const { data: ngoNeeds, isLoading: nLoad } = useQuery({
        queryKey: ['active-needs'],
        queryFn: () => api.getActiveNeeds(),
    })

    const { data: directNeeds, isLoading: dLoad } = useQuery({
        queryKey: ['direct-victim-needs'],
        queryFn: async () => {
            const res = await api.getVictimRequests({ page_size: 50 })
            return res.requests?.filter((r: any) => r.is_verified && !r.adopted_by) || []
        }
    })

    const pledgeMutation = useMutation({
        mutationFn: (data: any) => api.pledgeToSourcing(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['active-needs'] })
            queryClient.invalidateQueries({ queryKey: ['operational-pulse'] })
            setSelectedNeed(null)
            setPledgeQty(1)
        }
    })

    const adoptMutation = useMutation({
        mutationFn: (requestId: string) => api.adoptRequest(requestId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['direct-victim-needs'] })
            queryClient.invalidateQueries({ queryKey: ['operational-pulse'] })
            setSelectedNeed(null)
        }
    })

    const handlePledge = () => {
        if (!selectedNeed) return
        if (view === 'ngo') {
            pledgeMutation.mutate({
                sourcing_request_id: selectedNeed.id,
                quantity_pledged: pledgeQty
            })
        } else {
            adoptMutation.mutate(selectedNeed.id)
        }
    }

    const needs = view === 'ngo' ? ngoNeeds : directNeeds
    const isLoading = nLoad || dLoad

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-amber-500" />
                        Community Needs Feed
                    </h2>
                    <p className="text-sm text-slate-500 mt-1">Directly fuel NGO missions and community projects</p>
                </div>

                <div className="flex bg-slate-100 dark:bg-white/5 p-1 rounded-2xl self-start">
                    <button
                        onClick={() => setView('ngo')}
                        className={cn(
                            "px-4 py-2 rounded-xl text-xs font-bold transition-all",
                            view === 'ngo' ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700"
                        )}
                    >
                        NGO Needs
                    </button>
                    <button
                        onClick={() => setView('direct')}
                        className={cn(
                            "px-4 py-2 rounded-xl text-xs font-bold transition-all",
                            view === 'direct' ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700"
                        )}
                    >
                        Direct Support
                    </button>
                </div>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center p-12">
                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {needs?.map((need: any) => (
                        <div
                            key={need.id}
                            className={cn(
                                "relative overflow-hidden p-6 rounded-3xl border transition-all cursor-pointer group",
                                selectedNeed?.id === need.id
                                    ? "border-amber-500 bg-amber-500/5 ring-4 ring-amber-500/10"
                                    : "border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:border-amber-500/50 hover:shadow-xl hover:shadow-amber-500/5"
                            )}
                            onClick={() => setSelectedNeed(need)}
                        >
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-white/5 flex items-center justify-center">
                                        {view === 'ngo' ? <Building2 className="w-5 h-5 text-amber-500" /> : <User className="w-5 h-5 text-blue-500" />}
                                    </div>
                                    <div>
                                        <h4 className="font-bold text-slate-900 dark:text-white truncate max-w-[150px]">
                                            {view === 'ngo' ? 'NGO Supply Run' : 'Direct Victim Need'}
                                        </h4>
                                        <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{need.resource_type}</p>
                                    </div>
                                </div>
                                {need.urgency === 'critical' || need.priority === 'critical' ? (
                                    <div className="px-2 py-1 rounded-lg bg-red-500/10 text-red-500 text-[10px] font-black uppercase animate-pulse">
                                        Urgent
                                    </div>
                                ) : null}
                            </div>

                            <div className="mt-4">
                                <div className="flex items-end gap-1 mb-1">
                                    <span className="text-2xl font-black text-slate-900 dark:text-white">{need.quantity_needed || need.quantity}</span>
                                    <span className="text-xs text-slate-500 font-medium mb-1.5 uppercase tracking-tighter">Units Needed</span>
                                </div>
                                <p className="text-xs text-slate-500 line-clamp-2 italic leading-relaxed">
                                    "{need.description || (view === 'ngo' ? 'Stocking up for relief efforts in the affected zone...' : 'Verified request from someone in need.')}"
                                </p>
                            </div>

                            <div className="mt-4 pt-4 border-t border-slate-100 dark:border-white/5 flex items-center justify-between">
                                <div className={cn(
                                    "flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-tighter",
                                    view === 'ngo' ? "text-emerald-500" : "text-blue-500"
                                )}>
                                    <ShieldCheck className="w-3.5 h-3.5" />
                                    {view === 'ngo' ? 'NGO Verified' : 'Field Verified'}
                                </div>
                                <button className="flex items-center gap-1 text-xs font-bold text-amber-500 group-hover:translate-x-1 transition-transform">
                                    {view === 'ngo' ? 'Pledge Aid' : 'Adopt Request'} <ArrowRight className="w-3 h-3" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {selectedNeed && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                    <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-[32px] p-8 shadow-2xl border border-white/10 animate-in fade-in zoom-in duration-200">
                        <div className="text-center space-y-2">
                            <div className="w-16 h-16 rounded-[24px] bg-amber-500/10 text-amber-500 flex items-center justify-center mx-auto mb-4">
                                <Heart className="w-8 h-8 fill-current" />
                            </div>
                            <h3 className="text-2xl font-black text-slate-900 dark:text-white leading-tight">Support NGO Relief</h3>
                            <p className="text-sm text-slate-500">You are pledging {needToName(selectedNeed.resource_type)} to an active mission.</p>
                        </div>

                        <div className="mt-8 space-y-6">
                            <div className="space-y-3">
                                <div className="flex items-center justify-between px-2">
                                    <label className="text-xs font-bold text-slate-500 uppercase">Quantity to Pledge</label>
                                    <span className="text-lg font-black text-amber-500">{pledgeQty} Units</span>
                                </div>
                                <input
                                    type="range"
                                    min="1"
                                    max={selectedNeed.quantity_needed || selectedNeed.quantity || 1}
                                    step="1"
                                    className="w-full h-2 bg-slate-100 dark:bg-white/10 rounded-full appearance-none accent-amber-500 cursor-pointer"
                                    value={pledgeQty}
                                    onChange={e => setPledgeQty(parseInt(e.target.value))}
                                />
                                <div className="flex justify-between text-[10px] font-bold text-slate-400 px-1 uppercase tracking-widest">
                                    <span>1 unit</span>
                                    <span>Max {selectedNeed.quantity_needed || selectedNeed.quantity || 1}</span>
                                </div>
                            </div>

                            <div className="flex gap-3">
                                <button
                                    onClick={() => setSelectedNeed(null)}
                                    className="flex-1 py-4 rounded-2xl bg-slate-100 dark:bg-white/5 text-sm font-bold text-slate-500 hover:text-slate-700 transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handlePledge}
                                    disabled={pledgeMutation.isPending}
                                    className="flex-[2] py-4 rounded-2xl bg-amber-500 text-white text-sm font-black shadow-lg shadow-amber-500/30 hover:bg-amber-600 active:scale-95 transition-all flex items-center justify-center gap-2"
                                >
                                    {pledgeMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                                    Confirm Pledge
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

function needToName(type: string) {
    return type.toLowerCase().includes('aid') ? type : `essential ${type.toLowerCase()}`;
}
