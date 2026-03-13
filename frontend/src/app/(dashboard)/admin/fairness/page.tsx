'use client'

import { Suspense, useState, useEffect } from 'react'
import { FairnessSlider } from '@/components/admin/FairnessSlider'
import { useSearchParams, useRouter } from 'next/navigation'
import { Scale, Loader2, RefreshCw, Globe, MapPin } from 'lucide-react'
import { api } from '@/lib/api'

function FairnessContent() {
    const params = useSearchParams()
    const router = useRouter()
    const [disasterId, setDisasterId] = useState<string | undefined>(params.get('disaster_id') ?? undefined)
    const [disasterOptions, setDisasterOptions] = useState<Array<{id: string, label: string, value: string, type: string, status: string, severity: string, created_at: string}>>([])
    const [loadingOptions, setLoadingOptions] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Load disaster options on mount
    useEffect(() => {
        const loadDisasterOptions = async () => {
            setLoadingOptions(true)
            setError(null)
            try {
                const options = await api.getDisasterDropdownOptions()
                setDisasterOptions(options)
            } catch (err) {
                console.error('Failed to load disaster options:', err)
                setError('Failed to load disaster options')
            } finally {
                setLoadingOptions(false)
            }
        }
        loadDisasterOptions()
    }, [])

    // Update URL when disaster selection changes
    const handleDisasterChange = (value: string) => {
        setDisasterId(value || undefined)
        const newParams = new URLSearchParams(params.toString())
        if (value) {
            newParams.set('disaster_id', value)
        } else {
            newParams.delete('disaster_id')
        }
        router.push(`/admin/fairness?${newParams.toString()}`)
    }

    return (
        <div className="space-y-6">
            <div>
                <div className="flex items-center gap-3 mb-1">
                    <div className="p-2 rounded-xl bg-indigo-100 dark:bg-indigo-950/30">
                        <Scale className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Fairness-Constrained Allocation</h1>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400 ml-12">
                    Explore the Pareto frontier between allocation efficiency and equity. Adjust the slider to preview trade-offs, then apply your chosen plan.
                </p>
            </div>

            {/* Disaster Selector */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-white/5 p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Globe className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Incident Selection</h3>
                    </div>
                    <button
                        onClick={() => {
                            // Refresh options
                            const loadDisasterOptions = async () => {
                                setLoadingOptions(true)
                                setError(null)
                                try {
                                    const options = await api.getDisasterDropdownOptions()
                                    setDisasterOptions(options)
                                } catch (err) {
                                    console.error('Failed to refresh disaster options:', err)
                                    setError('Failed to refresh disaster options')
                                } finally {
                                    setLoadingOptions(false)
                                }
                            }
                            loadDisasterOptions()
                        }}
                        disabled={loadingOptions}
                        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-white/10 rounded-lg transition-colors"
                    >
                        <RefreshCw className={`w-3 h-3 ${loadingOptions ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>

                {error && (
                    <div className="mb-4 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 rounded-lg">
                        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2">
                        <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-2">
                            Select Incident
                        </label>
                        <div className="relative">
                            <MapPin className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <select
                                value={disasterId || ''}
                                onChange={(e) => handleDisasterChange(e.target.value)}
                                className="w-full pl-10 pr-4 py-2.5 border border-slate-200 dark:border-white/10 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            >
                                <option value="">All Incidents</option>
                                {disasterOptions.map((option) => (
                                    <option key={option.id} value={option.id}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>
                    
                    <div>
                        <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-2">
                            Current Selection
                        </label>
                        <div className="p-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-white/10 rounded-lg">
                            {disasterId ? (
                                disasterOptions.find(d => d.id === disasterId) ? (
                                    <div className="space-y-1">
                                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                                            {disasterOptions.find(d => d.id === disasterId)?.label}
                                        </p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400">
                                            Created: {new Date(disasterOptions.find(d => d.id === disasterId)?.created_at || '').toLocaleDateString()}
                                        </p>
                                    </div>
                                ) : (
                                    <p className="text-sm text-slate-500 dark:text-slate-400">Loading...</p>
                                )
                            ) : (
                                <p className="text-sm text-slate-500 dark:text-slate-400">No incident selected - showing all data</p>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            <FairnessSlider disasterId={disasterId} />
        </div>
    )
}

export default function FairnessPage() {
    return (
        <Suspense fallback={<div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-indigo-500" /></div>}>
            <FairnessContent />
        </Suspense>
    )
}
