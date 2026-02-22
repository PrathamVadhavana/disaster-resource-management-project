'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Award, Plus, Trash2, Edit2, CheckCircle2, Clock,
    X, Save, Calendar, Loader2
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface Certification {
    id: string
    name: string
    issuer: string
    date_obtained: string
    expiry_date: string
    status: 'active' | 'expired' | 'pending'
}

const CERT_TEMPLATES = [
    'First Aid / CPR', 'Disaster Response', 'Search and Rescue',
    'Hazmat Awareness', 'Incident Command System', 'Emergency Medical Technician',
    'Wilderness First Responder', 'Community Emergency Response Team (CERT)',
    'Swift Water Rescue', 'Fire Safety',
]

export default function VolunteerCertificationsPage() {
    const queryClient = useQueryClient()
    const [showAdd, setShowAdd] = useState(false)
    const [editId, setEditId] = useState<string | null>(null)
    const [form, setForm] = useState({ name: '', issuer: '', dateObtained: '', expiryDate: '' })

    // Fetch certifications from backend API
    const { data: certs = [], isLoading } = useQuery<Certification[]>({
        queryKey: ['volunteer-certifications'],
        queryFn: () => api.getCertifications(),
    })

    const createMutation = useMutation({
        mutationFn: (data: { name: string; issuer?: string; date_obtained?: string; expiry_date?: string }) =>
            api.createCertification(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-certifications'] })
            setForm({ name: '', issuer: '', dateObtained: '', expiryDate: '' })
            setShowAdd(false)
        },
    })

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: { name?: string; issuer?: string; date_obtained?: string; expiry_date?: string } }) =>
            api.updateCertification(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-certifications'] })
            setEditId(null)
            setForm({ name: '', issuer: '', dateObtained: '', expiryDate: '' })
        },
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteCertification(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['volunteer-certifications'] })
        },
    })

    const addCert = () => {
        if (!form.name.trim()) return
        createMutation.mutate({
            name: form.name,
            issuer: form.issuer || 'Self-reported',
            date_obtained: form.dateObtained || new Date().toISOString().split('T')[0],
            expiry_date: form.expiryDate || undefined,
        })
    }

    const updateCert = () => {
        if (!editId || !form.name.trim()) return
        updateMutation.mutate({
            id: editId,
            data: {
                name: form.name,
                issuer: form.issuer || undefined,
                date_obtained: form.dateObtained || undefined,
                expiry_date: form.expiryDate || undefined,
            },
        })
    }

    const deleteCert = (id: string) => deleteMutation.mutate(id)

    const startEdit = (cert: Certification) => {
        setEditId(cert.id)
        setForm({
            name: cert.name,
            issuer: cert.issuer,
            dateObtained: cert.date_obtained || '',
            expiryDate: cert.expiry_date || '',
        })
    }

    const activeCerts = certs.filter(c => c.status === 'active')
    const expiredCerts = certs.filter(c => c.status === 'expired')

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Certifications</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your qualifications and training records</p>
                </div>
                <button onClick={() => { setShowAdd(true); setEditId(null); setForm({ name: '', issuer: '', dateObtained: '', expiryDate: '' }) }}
                    className="h-9 px-4 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 flex items-center gap-2">
                    <Plus className="w-4 h-4" /> Add Certification
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <Award className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{certs.length}</p>
                        <p className="text-xs text-slate-500">Total Certifications</p>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                        <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{activeCerts.length}</p>
                        <p className="text-xs text-slate-500">Active</p>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                        <Clock className="w-5 h-5 text-red-600 dark:text-red-400" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white">{expiredCerts.length}</p>
                        <p className="text-xs text-slate-500">Expired</p>
                    </div>
                </div>
            </div>

            {/* Certifications List */}
            {certs.length > 0 ? (
                <div className="space-y-3">
                    {certs.map(cert => (
                        <div key={cert.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 group hover:shadow-lg transition-shadow">
                            <div className="flex items-start justify-between">
                                <div className="flex items-start gap-4">
                                    <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center',
                                        cert.status === 'active' ? 'bg-green-100 dark:bg-green-500/10' : 'bg-red-100 dark:bg-red-500/10'
                                    )}>
                                        <Award className={cn('w-5 h-5', cert.status === 'active' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')} />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white">{cert.name}</h3>
                                        <p className="text-xs text-slate-500 mt-0.5">Issued by: {cert.issuer}</p>
                                        <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-400">
                                            <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> Obtained: {cert.date_obtained ? new Date(cert.date_obtained).toLocaleDateString() : 'N/A'}</span>
                                            {cert.expiry_date && <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Expires: {new Date(cert.expiry_date).toLocaleDateString()}</span>}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className={cn('px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase',
                                        cert.status === 'active' ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                                    )}>
                                        {cert.status}
                                    </span>
                                    <button onClick={() => startEdit(cert)}
                                        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Edit2 className="w-3.5 h-3.5 text-slate-400" />
                                    </button>
                                    <button onClick={() => deleteCert(cert.id)}
                                        className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="py-16 text-center rounded-2xl border border-dashed border-slate-300 dark:border-white/10">
                    <Award className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-900 dark:text-white">No certifications yet</p>
                    <p className="text-xs text-slate-500 mt-1">Add your training and qualifications to get started</p>
                </div>
            )}

            {/* Add / Edit Modal */}
            {(showAdd || editId) && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">{editId ? 'Edit' : 'Add'} Certification</h2>
                            <button onClick={() => { setShowAdd(false); setEditId(null) }}
                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
                        </div>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Certification Name*</label>
                                <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                                    placeholder="e.g. First Aid / CPR" list="cert-suggestions"
                                    className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
                                <datalist id="cert-suggestions">
                                    {CERT_TEMPLATES.map(t => <option key={t} value={t} />)}
                                </datalist>
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Issuing Organization</label>
                                <input value={form.issuer} onChange={e => setForm({ ...form, issuer: e.target.value })}
                                    placeholder="e.g. American Red Cross"
                                    className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Date Obtained</label>
                                    <input type="date" value={form.dateObtained} onChange={e => setForm({ ...form, dateObtained: e.target.value })}
                                        className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Expiry Date</label>
                                    <input type="date" value={form.expiryDate} onChange={e => setForm({ ...form, expiryDate: e.target.value })}
                                        className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm" />
                                </div>
                            </div>
                        </div>
                        {(createMutation.isError || updateMutation.isError) && (
                            <p className="text-xs text-red-500 mt-2">Failed to save. Please try again.</p>
                        )}
                        <button onClick={editId ? updateCert : addCert}
                            disabled={!form.name.trim() || createMutation.isPending || updateMutation.isPending}
                            className="mt-5 w-full h-10 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                            {(createMutation.isPending || updateMutation.isPending) ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                                <Save className="w-4 h-4" />
                            )}
                            {editId ? 'Update' : 'Add'} Certification
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
