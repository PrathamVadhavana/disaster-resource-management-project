'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import {
    Receipt, Search, Download, Filter, Calendar,
    CheckCircle2, Clock, ArrowUpRight, Loader2,
    Heart, Trash2, X, FileText
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface DonationRecord {
    id: string
    disaster_id: string
    disaster_title: string
    disaster_type: string
    amount: number
    status: 'completed' | 'pending' | 'failed' | 'refunded'
    created_at: string
}

export default function DonorDonationsPage() {
    const { profile } = useAuth()
    const queryClient = useQueryClient()
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState<string>('all')

    // Fetch donations from backend API
    const { data: donations = [], isLoading } = useQuery<DonationRecord[]>({
        queryKey: ['donor-donations'],
        queryFn: () => api.getDonations(),
    })

    // Update donation (mark completed)
    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: { amount?: number; status?: string } }) =>
            api.updateDonation(id, data),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['donor-donations'] }),
    })

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.deleteDonation(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['donor-donations'] }),
    })

    const [receiptModal, setReceiptModal] = useState<boolean>(false)
    const [receiptData, setReceiptData] = useState<any>(null)
    const [loadingReceipt, setLoadingReceipt] = useState<boolean>(false)

    const fetchReceipt = async (id: string) => {
        setLoadingReceipt(true)
        setReceiptModal(true)
        try {
            const data = await api.getDonationReceipt(id)
            setReceiptData(data)
        } catch (error) {
            console.error('Failed to fetch receipt:', error)
            setReceiptModal(false)
        } finally {
            setLoadingReceipt(false)
        }
    }

    const filtered = useMemo(() => {
        return donations.filter(d => {
            const matchSearch = !search || (d.disaster_title || '').toLowerCase().includes(search.toLowerCase())
            const matchStatus = statusFilter === 'all' || d.status === statusFilter
            return matchSearch && matchStatus
        })
    }, [donations, search, statusFilter])

    const stats = {
        total: donations.length,
        completed: donations.filter(d => d.status === 'completed').length,
        pending: donations.filter(d => d.status === 'pending').length,
        totalAmount: donations.filter(d => d.status === 'completed').reduce((sum, d) => sum + (d.amount || 0), 0),
    }

    const markCompleted = (id: string, amount: number) => {
        updateMutation.mutate({ id, data: { amount, status: 'completed' } })
    }

    const removeDonation = (id: string) => {
        deleteMutation.mutate(id)
    }

    const exportCSV = () => {
        const csv = [
            ['ID', 'Disaster', 'Type', 'Amount', 'Status', 'Date'].join(','),
            ...donations.map(d => [d.id, `"${d.disaster_title}"`, d.disaster_type, d.amount, d.status, new Date(d.created_at).toLocaleDateString()].join(','))
        ].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = 'donations.csv'; a.click()
        URL.revokeObjectURL(url)
    }

    const [amountModal, setAmountModal] = useState<string | null>(null)
    const [amountInput, setAmountInput] = useState('')

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
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Donation History</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Track your contributions to disaster relief</p>
                </div>
                <button onClick={exportCSV}
                    className="h-9 px-4 rounded-xl bg-slate-100 dark:bg-white/5 text-slate-700 dark:text-slate-300 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 flex items-center gap-2">
                    <Download className="w-4 h-4" /> Export
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Receipt className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.total}</p>
                            <p className="text-xs text-slate-500">Total Pledges</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                            <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.completed}</p>
                            <p className="text-xs text-slate-500">Completed</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center">
                            <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stats.pending}</p>
                            <p className="text-xs text-slate-500">Pending</p>
                        </div>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <ArrowUpRight className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-slate-900 dark:text-white">${stats.totalAmount.toLocaleString()}</p>
                            <p className="text-xs text-slate-500">Total Donated</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search donations..." className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                </div>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                    className="h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm">
                    <option value="all">All Status</option>
                    <option value="completed">Completed</option>
                    <option value="pending">Pending</option>
                </select>
            </div>

            {/* Donation List */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-100 dark:border-white/5">
                            <th className="text-left px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Disaster</th>
                            <th className="text-left px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Type</th>
                            <th className="text-left px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Amount</th>
                            <th className="text-left px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Status</th>
                            <th className="text-left px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Date</th>
                            <th className="text-right px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map(d => (
                            <tr key={d.id} className="border-b border-slate-50 dark:border-white/5 hover:bg-slate-50 dark:hover:bg-white/[0.02]">
                                <td className="px-5 py-3 font-medium text-slate-900 dark:text-white">{d.disaster_title}</td>
                                <td className="px-5 py-3 text-slate-500 capitalize">{d.disaster_type}</td>
                                <td className="px-5 py-3 text-slate-900 dark:text-white font-semibold">
                                    {d.amount > 0 ? `$${d.amount.toLocaleString()}` : '—'}
                                </td>
                                <td className="px-5 py-3">
                                    <span className={cn('inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase',
                                        d.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'
                                    )}>
                                        {d.status}
                                    </span>
                                </td>
                                <td className="px-5 py-3 text-slate-500">{new Date(d.created_at).toLocaleDateString()}</td>
                                <td className="px-5 py-3 text-right">
                                    <div className="flex items-center justify-end gap-2">
                                        {d.status === 'pending' && (
                                            <button onClick={() => { setAmountModal(d.id); setAmountInput('') }}
                                                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-500/20 transition-colors">
                                                Complete
                                            </button>
                                        )}
                                        {d.status === 'completed' && (
                                            <button onClick={() => fetchReceipt(d.id)}
                                                className="p-1.5 rounded-lg text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors"
                                                title="View Receipt">
                                                <FileText className="w-4 h-4" />
                                            </button>
                                        )}
                                        <button onClick={() => removeDonation(d.id)}
                                            className="p-1.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                                            title="Delete Record">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {filtered.length === 0 && (
                    <div className="py-16 text-center">
                        <Receipt className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
                        <p className="text-sm font-medium text-slate-900 dark:text-white">No donations yet</p>
                        <p className="text-xs text-slate-500 mt-1">Visit the Causes page to support disaster relief</p>
                    </div>
                )}
            </div>

            {/* Amount Modal */}
            {amountModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-sm p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Enter Amount</h2>
                            <button onClick={() => setAmountModal(null)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
                        </div>
                        <input type="number" value={amountInput} onChange={(e) => setAmountInput(e.target.value)}
                            placeholder="Enter donation amount ($)"
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm mb-4" />
                        <button onClick={() => {
                            const amt = parseFloat(amountInput) || 0
                            if (amt > 0) {
                                markCompleted(amountModal, amt)
                                setAmountModal(null)
                            }
                        }}
                            className="w-full h-10 rounded-xl bg-green-600 text-white text-sm font-medium hover:bg-green-700">
                            Confirm Donation
                        </button>
                    </div>
                </div>
            )}

            {/* Receipt Modal */}
            {receiptModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col items-center p-8 relative">
                        <button onClick={() => { setReceiptModal(false); setReceiptData(null) }} className="absolute top-4 right-4 p-2 rounded-xl bg-slate-100 dark:bg-white/5 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors">
                            <X className="w-4 h-4" />
                        </button>

                        {loadingReceipt || !receiptData ? (
                            <div className="flex flex-col items-center justify-center py-10">
                                <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-4" />
                                <p className="text-sm text-slate-500">Generating digital receipt...</p>
                            </div>
                        ) : (
                            <div className="w-full">
                                <div className="w-16 h-16 bg-blue-100 dark:bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <Receipt className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                                </div>
                                <h3 className="text-xl font-bold text-slate-900 dark:text-white text-center mb-1">Donation Receipt</h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400 text-center mb-8">Ref: {receiptData.receipt_id}</p>

                                <div className="space-y-4 border-t border-b border-slate-100 dark:border-white/5 py-6 mb-6">
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Date</span>
                                        <span className="font-medium text-slate-900 dark:text-white">{new Date(receiptData.date).toLocaleDateString()}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Amount</span>
                                        <span className="font-bold text-lg text-slate-900 dark:text-white">${receiptData.amount.toLocaleString()}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Cause</span>
                                        <span className="font-medium text-slate-900 dark:text-white text-right max-w-[200px] truncate">{receiptData.cause}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Allocation</span>
                                        <span className="font-medium text-slate-900 dark:text-white text-right max-w-[200px] truncate">{receiptData.allocated_to}</span>
                                    </div>
                                </div>

                                <p className="text-sm text-center text-slate-600 dark:text-slate-300 italic px-4">
                                    "{receiptData.message}"
                                </p>

                                <div className="mt-8 flex justify-center">
                                    <button
                                        onClick={() => {
                                            const content = `Donation Receipt\nRef: ${receiptData.receipt_id}\nDate: ${new Date(receiptData.date).toLocaleDateString()}\nAmount: $${receiptData.amount}\nCause: ${receiptData.cause}\nAllocation: ${receiptData.allocated_to}`;
                                            const blob = new Blob([content], { type: 'text/plain' });
                                            const url = URL.createObjectURL(blob);
                                            const a = document.createElement('a');
                                            a.href = url; a.download = `receipt-${receiptData.receipt_id}.txt`; a.click();
                                        }}
                                        className="h-10 px-6 rounded-xl bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700 flex items-center gap-2 transition-all">
                                        <Download className="w-4 h-4" /> Download Digital Copy
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
