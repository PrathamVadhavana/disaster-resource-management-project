'use client'

import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import {
    Receipt, Download, Loader2, FileText, Calendar,
    Search, CheckCircle2, X, Building2, FileDown
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface DonationRecord {
    id: string
    disaster_id: string
    disaster_title: string
    disaster_type: string
    amount: number
    currency: string
    status: string
    payment_ref: string | null
    notes: string | null
    created_at: string
    updated_at: string
}

export default function TaxReceiptsPage() {
    const { profile } = useAuth()
    const [search, setSearch] = useState('')
    const [yearFilter, setYearFilter] = useState<string>('all')
    const [receiptModal, setReceiptModal] = useState<boolean>(false)
    const [receiptData, setReceiptData] = useState<any>(null)
    const [loadingReceipt, setLoadingReceipt] = useState<boolean>(false)
    const [downloadingPdf, setDownloadingPdf] = useState<string | null>(null)

    // Fetch only completed donations (these are eligible for tax receipts)
    const { data: donationsResp, isLoading } = useQuery<any>({
        queryKey: ['donor-donations'],
        queryFn: () => api.getDonations(),
    })
    const donations: DonationRecord[] = Array.isArray(donationsResp) ? donationsResp : (donationsResp?.donations || [])

    const completedDonations = useMemo(() => {
        return donations.filter(d => d.status === 'completed')
    }, [donations])

    // Get unique years for filtering
    const availableYears = useMemo(() => {
        const years = new Set(completedDonations.map(d => new Date(d.created_at).getFullYear().toString()))
        return Array.from(years).sort((a, b) => b.localeCompare(a))
    }, [completedDonations])

    const filtered = useMemo(() => {
        return completedDonations.filter(d => {
            const matchSearch = !search ||
                (d.disaster_title || '').toLowerCase().includes(search.toLowerCase()) ||
                d.id.toLowerCase().includes(search.toLowerCase())
            const matchYear = yearFilter === 'all' || new Date(d.created_at).getFullYear().toString() === yearFilter
            return matchSearch && matchYear
        })
    }, [completedDonations, search, yearFilter])

    const totalByYear = useMemo(() => {
        const totals: Record<string, number> = {}
        for (const d of completedDonations) {
            const year = new Date(d.created_at).getFullYear().toString()
            totals[year] = (totals[year] || 0) + (d.amount || 0)
        }
        return totals
    }, [completedDonations])

    const currentYearTotal = yearFilter === 'all'
        ? completedDonations.reduce((sum, d) => sum + (d.amount || 0), 0)
        : (totalByYear[yearFilter] || 0)

    const fetchReceipt = async (id: string) => {
        setLoadingReceipt(true)
        setReceiptModal(true)
        try {
            const data = await api.getDonationReceipt(id)
            setReceiptData({ ...data, _donation_id: id })
        } catch (error) {
            console.error('Failed to fetch receipt:', error)
            setReceiptModal(false)
        } finally {
            setLoadingReceipt(false)
        }
    }

    const downloadReceipt = (receipt: any) => {
        const content = [
            '═══════════════════════════════════════════',
            '           TAX DONATION RECEIPT            ',
            '═══════════════════════════════════════════',
            '',
            `Receipt ID:     ${receipt.receipt_id}`,
            `Date:           ${new Date(receipt.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`,
            `Donor:          ${profile?.full_name || 'Donor'}`,
            '',
            '───────────────────────────────────────────',
            '  DONATION DETAILS',
            '───────────────────────────────────────────',
            '',
            `Amount:         $${receipt.amount?.toLocaleString()} ${receipt.currency || 'USD'}`,
            `Cause:          ${receipt.cause}`,
            `Allocated To:   ${receipt.allocated_to}`,
            `Payment Ref:    ${receipt.payment_reference || 'N/A'}`,
            `Status:         ${receipt.status}`,
            '',
            '───────────────────────────────────────────',
            '',
            'This receipt is issued for tax deduction purposes.',
            'Please consult your tax advisor for eligibility.',
            '',
            `"${receipt.message}"`,
            '',
            '═══════════════════════════════════════════',
            '  HopeInChaos — Disaster Management System ',
            '═══════════════════════════════════════════',
        ].join('\n')

        const blob = new Blob([content], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `tax-receipt-${receipt.receipt_id}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    const downloadAllReceipts = () => {
        const year = yearFilter === 'all' ? 'all-years' : yearFilter
        const rows = filtered.map(d => [
            `REC-${d.id.slice(0, 8).toUpperCase()}`,
            new Date(d.created_at).toLocaleDateString(),
            d.disaster_title,
            `$${d.amount?.toLocaleString()}`,
            d.currency || 'USD',
            d.payment_ref || 'N/A'
        ])
        const csv = [
            ['Receipt ID', 'Date', 'Cause', 'Amount', 'Currency', 'Payment Ref'].join(','),
            ...rows.map(r => r.map(v => `"${v}"`).join(','))
        ].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `tax-receipts-${year}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    const downloadPdfCertificate = async (donationId: string) => {
        setDownloadingPdf(donationId)
        try {
            const blob = await api.getTaxCertificatePdf(donationId)
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `tax-certificate-REC-${donationId.slice(0, 8).toUpperCase()}.pdf`
            a.click()
            URL.revokeObjectURL(url)
        } catch (error) {
            console.error('Failed to download PDF certificate:', error)
        } finally {
            setDownloadingPdf(null)
        }
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Tax Receipts</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Download receipts for your completed donations for tax purposes
                    </p>
                </div>
                {filtered.length > 0 && (
                    <button
                        onClick={downloadAllReceipts}
                        className="h-9 px-4 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 flex items-center gap-2 transition-colors"
                    >
                        <Download className="w-4 h-4" /> Export All
                    </button>
                )}
            </div>

            {/* Summary Card */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-500/5 dark:to-teal-500/5 p-6">
                <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                        <Receipt className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <div>
                        <p className="text-sm text-emerald-700 dark:text-emerald-400 font-medium">
                            {yearFilter === 'all' ? 'Total' : yearFilter} Tax-Deductible Donations
                        </p>
                        <p className="text-3xl font-bold text-emerald-900 dark:text-white">
                            ${currentYearTotal.toLocaleString()}
                        </p>
                        <p className="text-xs text-emerald-600/60 dark:text-emerald-400/60 mt-0.5">
                            {filtered.length} receipt{filtered.length !== 1 ? 's' : ''} available
                        </p>
                    </div>
                </div>
            </div>

            {/* Year Totals */}
            {availableYears.length > 1 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {availableYears.map(year => (
                        <button key={year} onClick={() => setYearFilter(year === yearFilter ? 'all' : year)}
                            className={cn(
                                'rounded-xl border p-4 text-left transition-all',
                                yearFilter === year
                                    ? 'border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10'
                                    : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:border-slate-300 dark:hover:border-white/20'
                            )}
                        >
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{year}</p>
                            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">${(totalByYear[year] || 0).toLocaleString()}</p>
                        </button>
                    ))}
                </div>
            )}

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by cause or receipt ID..."
                    className="w-full h-10 pl-10 pr-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
            </div>

            {/* Receipt List */}
            {filtered.length === 0 ? (
                <div className="text-center py-20">
                    <Receipt className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <p className="text-lg font-semibold text-slate-700 dark:text-white">No tax receipts available</p>
                    <p className="text-sm text-slate-500 mt-1">
                        Receipts are generated for completed donations only.
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {filtered.map(d => (
                        <div key={d.id} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-5 hover:shadow-md transition-all">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                                        <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-semibold text-slate-900 dark:text-white">{d.disaster_title}</p>
                                        <div className="flex items-center gap-3 mt-0.5">
                                            <span className="text-xs text-slate-400 flex items-center gap-1">
                                                <Calendar className="w-3 h-3" />
                                                {new Date(d.created_at).toLocaleDateString()}
                                            </span>
                                            <span className="text-xs text-slate-400">
                                                Ref: REC-{d.id.slice(0, 8).toUpperCase()}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className="text-right">
                                        <p className="text-lg font-bold text-slate-900 dark:text-white">${d.amount?.toLocaleString()}</p>
                                        <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                                            <CheckCircle2 className="w-3 h-3" /> Completed
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => fetchReceipt(d.id)}
                                        className="px-4 py-2 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-sm font-semibold hover:bg-emerald-100 dark:hover:bg-emerald-500/20 flex items-center gap-2 transition-colors"
                                    >
                                        <Download className="w-4 h-4" /> Receipt
                                    </button>
                                    <button
                                        onClick={() => downloadPdfCertificate(d.id)}
                                        disabled={downloadingPdf === d.id}
                                        className="px-4 py-2 rounded-xl bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 text-sm font-semibold hover:bg-blue-100 dark:hover:bg-blue-500/20 flex items-center gap-2 transition-colors disabled:opacity-50"
                                    >
                                        {downloadingPdf === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />} PDF
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
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
                                <Loader2 className="w-8 h-8 animate-spin text-emerald-500 mb-4" />
                                <p className="text-sm text-slate-500">Generating tax receipt...</p>
                            </div>
                        ) : (
                            <div className="w-full">
                                <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <Receipt className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <h3 className="text-xl font-bold text-slate-900 dark:text-white text-center mb-1">Tax Donation Receipt</h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400 text-center mb-8">Ref: {receiptData.receipt_id}</p>

                                <div className="space-y-4 border-t border-b border-slate-100 dark:border-white/5 py-6 mb-6">
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Date</span>
                                        <span className="font-medium text-slate-900 dark:text-white">{new Date(receiptData.date).toLocaleDateString()}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Donor</span>
                                        <span className="font-medium text-slate-900 dark:text-white">{profile?.full_name || 'Donor'}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Amount</span>
                                        <span className="font-bold text-lg text-emerald-700 dark:text-emerald-400">${receiptData.amount?.toLocaleString()}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Cause</span>
                                        <span className="font-medium text-slate-900 dark:text-white text-right max-w-[200px] truncate">{receiptData.cause}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Allocation</span>
                                        <span className="font-medium text-slate-900 dark:text-white text-right max-w-[200px] truncate">{receiptData.allocated_to}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Payment Ref</span>
                                        <span className="font-medium text-slate-900 dark:text-white">{receiptData.payment_reference || 'N/A'}</span>
                                    </div>
                                </div>

                                <p className="text-xs text-center text-slate-400 dark:text-slate-500 italic px-4 mb-2">
                                    This receipt is issued for tax deduction purposes.
                                </p>
                                <p className="text-sm text-center text-slate-600 dark:text-slate-300 italic px-4">
                                    &quot;{receiptData.message}&quot;
                                </p>

                                <div className="mt-8 flex justify-center gap-3">
                                    <button
                                        onClick={() => downloadReceipt(receiptData)}
                                        className="h-10 px-6 rounded-xl bg-emerald-600 text-white font-semibold text-sm hover:bg-emerald-700 flex items-center gap-2 transition-all"
                                    >
                                        <Download className="w-4 h-4" /> Download TXT
                                    </button>
                                    <button
                                        onClick={() => receiptData._donation_id && downloadPdfCertificate(receiptData._donation_id)}
                                        disabled={!!downloadingPdf || !receiptData._donation_id}
                                        className="h-10 px-6 rounded-xl bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700 flex items-center gap-2 transition-all disabled:opacity-50"
                                    >
                                        {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />} Download PDF
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
