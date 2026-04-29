'use client'

import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    ShieldCheck, Camera, MapPin,
    CheckCircle2, AlertCircle, XCircle,
    Loader2, ClipboardList, Info, Zap,
    ChevronLeft, ChevronRight, Clock, Mail, User, ImageIcon
} from 'lucide-react'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 6

export function VerificationHub() {
    const queryClient = useQueryClient()
    const [selectedRequest, setSelectedRequest] = useState<any>(null)
    const [status, setStatus] = useState<'trusted' | 'dubious' | 'false_alarm'>('trusted')
    const [notes, setNotes] = useState('')
    const [view, setView] = useState<'verify' | 'assignments'>('verify')
    const [page, setPage] = useState(1)

    // Photo upload state
    const [photoUrl, setPhotoUrl] = useState<string | null>(null)
    const [photoPreview, setPhotoPreview] = useState<string | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // 1. Fetch unverified resource requests via new triage endpoint (with pagination)
    const { data: triageData, isLoading: rLoad } = useQuery({
        queryKey: ['triage-requests', page],
        queryFn: () => api.getTriageRequests({ page, page_size: PAGE_SIZE }),
    })
    const requests = triageData?.requests || []
    const totalPages = triageData?.total_pages || 1
    const totalRequests = triageData?.total || 0

    // 2. Fetch volunteer's active assignments
    const { data: assignments, isLoading: aLoad } = useQuery({
        queryKey: ['my-assignments'],
        queryFn: async () => {
            const res = await api.getActiveMissions()
            return res || []
        }
    })

    // 3. Fetch impact score
    const { data: impact } = useQuery({
        queryKey: ['my-impact'],
        queryFn: () => api.getUserImpact()
    })

    const verifyMutation = useMutation({
        mutationFn: (data: any) => api.verifyRequest(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['triage-requests'] })
            queryClient.invalidateQueries({ queryKey: ['operational-pulse'] })
            queryClient.invalidateQueries({ queryKey: ['my-impact'] })
            setSelectedRequest(null)
            setNotes('')
            setStatus('trusted')
            setPhotoUrl(null)
            setPhotoPreview(null)
        }
    })

    const completeMutation = useMutation({
        mutationFn: (id: string) => api.completeAssignment(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['my-assignments'] })
            queryClient.invalidateQueries({ queryKey: ['my-impact'] })
        }
    })

    const handleVerify = () => {
        if (!selectedRequest) return
        verifyMutation.mutate({
            request_id: selectedRequest.id,
            field_notes: notes,
            verification_status: status,
            latitude_at_verification: selectedRequest.latitude,
            longitude_at_verification: selectedRequest.longitude,
            photo_url: photoUrl || undefined
        })
    }

    const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        // Create a data URL from the file for preview and submission
        const reader = new FileReader()
        reader.onloadend = () => {
            const dataUrl = reader.result as string
            setPhotoPreview(dataUrl)
            setPhotoUrl(dataUrl)
        }
        reader.readAsDataURL(file)
    }

    const isLoading = rLoad || aLoad

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
                        <ShieldCheck className="w-6 h-6 text-emerald-500" />
                        Volunteer Operations
                    </h2>
                    <div className="flex items-center gap-3 mt-1">
                        <p className="text-sm text-slate-500">Coordination Hub for field triage and NGO missions</p>
                        {impact && (impact.total_impact_points || 0) > 0 && (
                            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 text-[10px] font-black uppercase">
                                <Zap className="w-3 h-3 fill-current" />
                                {impact.total_impact_points} Points
                            </div>
                        )}
                    </div>
                </div>

                <div className="flex bg-slate-100 dark:bg-white/5 p-1 rounded-2xl self-start">
                    <button
                        onClick={() => setView('verify')}
                        className={cn(
                            "px-4 py-2 rounded-xl text-xs font-bold transition-all",
                            view === 'verify' ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700"
                        )}
                    >
                        Nearby Triage
                    </button>
                    <button
                        onClick={() => setView('assignments')}
                        className={cn(
                            "px-4 py-2 rounded-xl text-xs font-bold transition-all",
                            view === 'assignments' ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm" : "text-slate-500 hover:text-slate-700"
                        )}
                    >
                        My Missions
                    </button>
                </div>
            </div>

            {/* Single-column layout */}
            <div className="grid grid-cols-1 gap-4">
                {view === 'verify' ? (
                    <>
                        {isLoading ? (
                            <div className="flex items-center justify-center py-16">
                                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                            </div>
                        ) : requests.length === 0 ? (
                            <div className="col-span-full py-12 text-center border-2 border-dashed border-slate-100 dark:border-white/5 rounded-[32px]">
                                <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-white/5 flex items-center justify-center mx-auto mb-3">
                                    <CheckCircle2 className="w-6 h-6 text-slate-300" />
                                </div>
                                <p className="text-slate-400 text-sm font-medium">No unverified requests at this time.</p>
                            </div>
                        ) : (
                            requests.map((req: any) => (
                                <div
                                    key={req.id}
                                    className="p-5 rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:border-emerald-500/30 transition-all group"
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="flex gap-4 flex-1 min-w-0">
                                            <div className="w-10 h-10 rounded-[12px] bg-slate-100 dark:bg-white/5 flex items-center justify-center shrink-0">
                                                <ClipboardList className="w-5 h-5 text-slate-500" />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <h4 className="font-bold text-slate-900 dark:text-white leading-tight">
                                                    {req.resource_type} Request
                                                    <span className="ml-2 text-xs font-semibold text-slate-400">
                                                        × {req.quantity || '?'}
                                                    </span>
                                                </h4>
                                                <p className="text-xs text-slate-500 mt-0.5 truncate max-w-[400px]">
                                                    {req.description || 'No description provided'}
                                                </p>

                                                {/* Victim details row */}
                                                <div className="flex items-center gap-4 mt-2 flex-wrap text-[11px] text-slate-400">
                                                    {req.victim_name && (
                                                        <span className="flex items-center gap-1">
                                                            <User className="w-3 h-3" /> {req.victim_name}
                                                        </span>
                                                    )}
                                                    {req.victim_email && (
                                                        <span className="flex items-center gap-1">
                                                            <Mail className="w-3 h-3" /> {req.victim_email}
                                                        </span>
                                                    )}
                                                    {req.created_at && (
                                                        <span className="flex items-center gap-1">
                                                            <Clock className="w-3 h-3" /> {new Date(req.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                    )}
                                                    <span className="flex items-center gap-1">
                                                        <MapPin className="w-3 h-3" /> {req.location_name || req.address_text || 'Nearby Zone'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => setSelectedRequest(req)}
                                            className="px-3 py-1.5 rounded-xl bg-emerald-500 text-white text-[10px] font-black uppercase tracking-wider hover:bg-emerald-600 transition-colors shadow-lg shadow-emerald-500/20 shrink-0 ml-4"
                                        >
                                            Verify
                                        </button>
                                    </div>
                                    <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-tighter">
                                        <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {req.location_name || 'Nearby Zone'}</span>
                                        <span className="text-amber-500">Unverified</span>
                                    </div>
                                </div>
                            ))
                        )}

                        {/* Pagination controls */}
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between pt-2">
                                <p className="text-xs text-slate-400">
                                    {totalRequests} total request{totalRequests !== 1 ? 's' : ''}
                                </p>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setPage(p => Math.max(1, p - 1))}
                                        disabled={page <= 1}
                                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                                    >
                                        <ChevronLeft className="w-3 h-3" /> Prev
                                    </button>
                                    <span className="text-xs font-bold text-slate-500">
                                        {page} / {totalPages}
                                    </span>
                                    <button
                                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                        disabled={page >= totalPages}
                                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                                    >
                                        Next <ChevronRight className="w-3 h-3" />
                                    </button>
                                </div>
                            </div>
                        )}
                    </>
                ) : (
                    <>
                        {assignments?.map((mission: any) => (
                            <div
                                key={mission.id}
                                className="p-5 rounded-3xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:border-blue-500/30 transition-all group"
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex gap-4">
                                        <div className="w-10 h-10 rounded-[12px] bg-blue-500/10 flex items-center justify-center shrink-0 text-blue-500">
                                            <ShieldCheck className="w-5 h-5" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-slate-900 dark:text-white leading-tight">
                                                {mission.title}
                                            </h4>
                                            <p className="text-xs text-slate-500 mt-0.5">{mission.status}</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => completeMutation.mutate(mission.id)}
                                        disabled={completeMutation.isPending}
                                        className="px-3 py-1.5 rounded-xl bg-blue-500 text-white text-[10px] font-black uppercase tracking-wider hover:bg-blue-600 transition-colors shadow-lg shadow-blue-500/20"
                                    >
                                        {completeMutation.isPending ? '...' : 'Complete'}
                                    </button>
                                </div>
                                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/5">
                                    <p className="text-[10px] text-slate-500 italic">"NGO Mission active in this sector."</p>
                                </div>
                            </div>
                        ))}

                        {assignments?.length === 0 && (
                            <div className="col-span-full py-12 text-center border-2 border-dashed border-slate-100 dark:border-white/5 rounded-[32px]">
                                <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-white/5 flex items-center justify-center mx-auto mb-3">
                                    <CheckCircle2 className="w-6 h-6 text-slate-300" />
                                </div>
                                <p className="text-slate-400 text-sm font-medium">All tasks in this view are completed.</p>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* Verification Modal */}
            {selectedRequest && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md">
                    <div className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-[32px] overflow-hidden shadow-2xl border border-white/10 animate-in fade-in slide-in-from-bottom-4 duration-300">
                        <div className="bg-emerald-500 p-8 text-white relative">
                            <button
                                onClick={() => { setSelectedRequest(null); setPhotoUrl(null); setPhotoPreview(null) }}
                                className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
                            >
                                <XCircle className="w-5 h-5" />
                            </button>
                            <ShieldCheck className="w-12 h-12 mb-4 opacity-50" />
                            <h3 className="text-2xl font-black leading-tight">Post-Arrival Triage</h3>
                            <p className="text-emerald-50 text-sm mt-1 opacity-90">Confirming {selectedRequest.resource_type} need at location.</p>

                            {/* Victim details in modal header */}
                            <div className="mt-3 flex items-center gap-4 text-emerald-100 text-xs flex-wrap">
                                {selectedRequest.victim_name && (
                                    <span className="flex items-center gap-1"><User className="w-3 h-3" /> {selectedRequest.victim_name}</span>
                                )}
                                {selectedRequest.victim_email && (
                                    <span className="flex items-center gap-1"><Mail className="w-3 h-3" /> {selectedRequest.victim_email}</span>
                                )}
                                {selectedRequest.location_name && (
                                    <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {selectedRequest.location_name}</span>
                                )}
                            </div>
                        </div>

                        <div className="p-8 space-y-6">
                            <div className="space-y-3">
                                <label className="text-xs font-black text-slate-500 uppercase tracking-widest px-1">Ground Truth Status</label>
                                <div className="grid grid-cols-3 gap-2">
                                    {(['trusted', 'dubious', 'false_alarm'] as const).map(s => (
                                        <button
                                            key={s}
                                            onClick={() => setStatus(s)}
                                            className={cn(
                                                "py-3 rounded-2xl text-[10px] font-black uppercase transition-all flex flex-col items-center gap-1",
                                                status === s
                                                    ? "bg-emerald-500 text-white shadow-xl shadow-emerald-500/20 scale-105"
                                                    : "bg-slate-50 dark:bg-white/5 text-slate-500 hover:bg-slate-100"
                                            )}
                                        >
                                            {s === 'trusted' ? <CheckCircle2 className="w-4 h-4" /> : s === 'dubious' ? <Info className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                                            {s.replace('_', ' ')}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-xs font-black text-slate-500 uppercase tracking-widest px-1">Field Observations</label>
                                <textarea
                                    className="w-full px-5 py-4 rounded-2xl border-2 border-slate-100 dark:border-white/5 bg-white dark:bg-white/5 outline-none focus:border-emerald-500/50 min-h-[120px] shadow-inner text-sm leading-relaxed"
                                    placeholder="Describe current situation, number of affected people, or any specific details needed by the NGO..."
                                    value={notes}
                                    onChange={e => setNotes(e.target.value)}
                                />
                            </div>

                            {/* Photo preview */}
                            {photoPreview && (
                                <div className="relative">
                                    <img
                                        src={photoPreview}
                                        alt="Verification photo"
                                        className="w-full h-40 object-cover rounded-2xl border-2 border-emerald-200 dark:border-emerald-500/30"
                                    />
                                    <button
                                        onClick={() => { setPhotoUrl(null); setPhotoPreview(null) }}
                                        className="absolute top-2 right-2 p-1.5 rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors"
                                    >
                                        <XCircle className="w-4 h-4" />
                                    </button>
                                    <div className="absolute bottom-2 left-2 px-2 py-1 rounded-lg bg-black/50 text-white text-[10px] font-semibold flex items-center gap-1">
                                        <ImageIcon className="w-3 h-3" /> Photo attached
                                    </div>
                                </div>
                            )}

                            {/* Hidden file input for photo upload */}
                            <input
                                type="file"
                                ref={fileInputRef}
                                accept="image/*"
                                capture="environment"
                                className="hidden"
                                onChange={handlePhotoSelect}
                            />

                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="flex-1 py-4 flex items-center justify-center gap-2 rounded-2xl bg-slate-100 dark:bg-white/5 text-slate-500 text-sm font-bold hover:bg-slate-200 transition-all"
                                >
                                    <Camera className="w-4 h-4" />
                                    {photoPreview ? 'Change Photo' : 'Post Photo'}
                                </button>
                                <button
                                    onClick={handleVerify}
                                    disabled={verifyMutation.isPending}
                                    className="flex-[2] py-4 rounded-2xl bg-emerald-500 text-white text-sm font-black shadow-lg shadow-emerald-500/30 hover:bg-emerald-600 active:scale-95 transition-all flex items-center justify-center gap-2"
                                >
                                    {verifyMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                                    Finalize Verification
                                </button>
                            </div>

                            {verifyMutation.isError && (
                                <p className="text-xs text-red-500 text-center">
                                    {(verifyMutation.error as any)?.message || 'Verification failed. Please try again.'}
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
