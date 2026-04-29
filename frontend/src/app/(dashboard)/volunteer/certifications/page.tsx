'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Award, Plus, Trash2, Loader2, Calendar, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { format } from 'date-fns'

export default function VolunteerCertificationsPage() {
    const queryClient = useQueryClient()
    const [isAdding, setIsAdding] = useState(false)
    const [newCert, setNewCert] = useState({ name: '', issuer: '', date_obtained: '', expiry_date: '' })

    const { data: certs, isLoading } = useQuery({
        queryKey: ['certifications'],
        queryFn: () => api.getCertifications()
    })

    const addMut = useMutation({
        mutationFn: () => api.createCertification({
            ...newCert,
            date_obtained: newCert.date_obtained || null,
            expiry_date: newCert.expiry_date || null,
        }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['certifications'] })
            setIsAdding(false)
            setNewCert({ name: '', issuer: '', date_obtained: '', expiry_date: '' })
        }
    })

    const delMut = useMutation({
        mutationFn: (id: string) => api.deleteCertification(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['certifications'] })
    })

    // Must be before any early return to satisfy Rules of Hooks
    const [certPage, setCertPage] = useState(1)

    if (isLoading) {
        return <div className="flex h-64 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
    }

    const certList = Array.isArray(certs) ? certs : []
    const CERTS_PER_PAGE = 6
    const certTotalPages = Math.max(1, Math.ceil(certList.length / CERTS_PER_PAGE))
    const pagedCerts = certList.slice((certPage - 1) * CERTS_PER_PAGE, certPage * CERTS_PER_PAGE)

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Certifications</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your active licenses and credentials for field assignments.</p>
                </div>
                <button
                    onClick={() => setIsAdding(!isAdding)}
                    className="h-10 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold flex items-center gap-2 transition-transform active:scale-95"
                >
                    <Plus className="w-4 h-4" /> Add Certificate
                </button>
            </div>

            {isAdding && (
                <div className="p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 shadow-lg mb-6">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Add New Certification</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                        <input
                            type="text"
                            placeholder="Certificate Name (e.g., FEMA Search & Rescue)"
                            value={newCert.name}
                            onChange={(e) => setNewCert({ ...newCert, name: e.target.value })}
                            className="h-10 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                        />
                        <input
                            type="text"
                            placeholder="Issuer (e.g., Red Cross)"
                            value={newCert.issuer}
                            onChange={(e) => setNewCert({ ...newCert, issuer: e.target.value })}
                            className="h-10 px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                        />
                        <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-500">Date Obtained</label>
                            <input
                                type="date"
                                value={newCert.date_obtained}
                                onChange={(e) => setNewCert({ ...newCert, date_obtained: e.target.value })}
                                className="h-10 w-full px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-500">Expiry Date (Optional)</label>
                            <input
                                type="date"
                                value={newCert.expiry_date}
                                onChange={(e) => setNewCert({ ...newCert, expiry_date: e.target.value })}
                                className="h-10 w-full px-3 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-950 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                            />
                        </div>
                    </div>
                    <div className="flex gap-3 justify-end">
                        <button
                            onClick={() => setIsAdding(false)}
                            className="px-4 py-2 rounded-xl text-sm font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={() => addMut.mutate()}
                            disabled={!newCert.name || !newCert.issuer || addMut.isPending}
                            className="px-4 py-2 rounded-xl text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-2 disabled:opacity-50"
                        >
                            {addMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Certificate'}
                        </button>
                    </div>
                    {addMut.isError && (
                        <p className="text-xs text-red-500 mt-2">
                            {(addMut.error as any)?.message || 'Failed to create certification. Please try again.'}
                        </p>
                    )}
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {certList.length === 0 ? (
                    <div className="col-span-full py-16 flex flex-col items-center justify-center border-2 border-dashed border-slate-200 dark:border-white/10 rounded-2xl">
                        <Award className="w-12 h-12 text-slate-300 dark:text-slate-600 mb-3" />
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white">No Certifications Yet</h3>
                        <p className="text-sm text-slate-500 mt-1">Add your credentials to unlock higher-tier deployments.</p>
                    </div>
                ) : (
                    pagedCerts.map((cert: any) => (
                        <div key={cert.id} className="relative group p-5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 shadow-sm hover:shadow-lg transition-all overflow-hidden flex flex-col">
                            <div className="absolute -right-4 -top-4 w-24 h-24 bg-blue-500/10 rounded-full blur-2xl pointer-events-none group-hover:bg-blue-500/20 transition-all opacity-0 group-hover:opacity-100"></div>

                            <div className="flex items-start justify-between mb-4">
                                <div className="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                                    <Award className="w-6 h-6" />
                                </div>
                                <span className={cn(
                                    "px-2 py-0.5 rounded text-[10px] font-bold uppercase",
                                    cert.status === 'active' ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400" :
                                        cert.status === 'expired' ? "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400" :
                                            "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
                                )}>
                                    {cert.status === 'active' ? 'Active' : cert.status === 'expired' ? 'Expired' : cert.status || 'Pending'}
                                </span>
                            </div>

                            <h3 className="font-bold text-slate-900 dark:text-white mb-1">{cert.name}</h3>
                            <p className="text-sm font-medium text-blue-600 dark:text-blue-400 mb-4">{cert.issuer}</p>

                            <div className="mt-auto space-y-2 pt-4 border-t border-slate-100 dark:border-white/5">
                                {cert.date_obtained && (
                                    <div className="flex items-center text-xs text-slate-500">
                                        <Calendar className="w-3.5 h-3.5 mr-2" />
                                        Obtained: <strong className="ml-1 text-slate-700 dark:text-slate-300">{format(new Date(cert.date_obtained), 'MMM yyyy')}</strong>
                                    </div>
                                )}
                                {cert.expiry_date && (
                                    <div className="flex items-center text-xs text-slate-500">
                                        <Calendar className="w-3.5 h-3.5 mr-2" />
                                        Expires: <strong className="ml-1 text-slate-700 dark:text-slate-300">{format(new Date(cert.expiry_date), 'MMM yyyy')}</strong>
                                    </div>
                                )}
                            </div>

                            <button
                                onClick={() => {
                                    if (confirm('Delete this certification?')) delMut.mutate(cert.id)
                                }}
                                disabled={delMut.isPending}
                                className="absolute top-4 right-4 p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))
                )}
            </div>

            {/* Pagination */}
            {certTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-slate-400">{certList.length} certification{certList.length !== 1 ? 's' : ''}</p>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setCertPage(p => Math.max(1, p - 1))}
                            disabled={certPage <= 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft className="w-3 h-3" /> Prev
                        </button>
                        <span className="text-xs font-bold text-slate-500">{certPage} / {certTotalPages}</span>
                        <button
                            onClick={() => setCertPage(p => Math.min(certTotalPages, p + 1))}
                            disabled={certPage >= certTotalPages}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 text-xs font-semibold text-slate-600 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                        >
                            Next <ChevronRight className="w-3 h-3" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
