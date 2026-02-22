'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useMemo } from 'react'
import dynamic from 'next/dynamic'
import {
    Loader2, MapPin, AlertTriangle, Activity, RefreshCw
} from 'lucide-react'

// Dynamically import the map component (Leaflet requires window/document)
const DisasterMap = dynamic(
    () => import('@/components/ngo/DisasterMap'),
    {
        ssr: false,
        loading: () => (
            <div className="flex items-center justify-center h-[500px] rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02]">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        ),
    }
) as React.ComponentType<{ disasters: any[] }>

const SEVERITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-amber-500',
    low: 'bg-green-500',
}

export default function NGOLiveMapPage() {
    const { data: disasters, isLoading, refetch } = useQuery({
        queryKey: ['ngo-live-map-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 100 }),
        refetchInterval: 15000,
    })

    const { data: resources } = useQuery({
        queryKey: ['ngo-live-map-resources'],
        queryFn: () => api.getResources({}),
        refetchInterval: 30000,
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const withCoords = useMemo(
        () => disasterList.filter((d: any) => d.latitude != null && d.longitude != null),
        [disasterList]
    )
    const criticalCount = disasterList.filter((d: any) => d.severity === 'critical').length

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Live Map</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Real-time view of active disaster zones and deployed resources.
                    </p>
                </div>
                <button onClick={() => refetch()} className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                    { label: 'Active Disasters', value: disasterList.length, icon: AlertTriangle, color: 'from-red-500 to-orange-600' },
                    { label: 'Critical', value: criticalCount, icon: Activity, color: 'from-orange-500 to-red-600' },
                    { label: 'On Map', value: withCoords.length, icon: MapPin, color: 'from-blue-500 to-cyan-600' },
                    { label: 'Resources Deployed', value: resourceList.filter((r: any) => r.status === 'allocated').length, icon: Activity, color: 'from-emerald-500 to-teal-600' },
                ].map((s) => {
                    const Icon = s.icon
                    return (
                        <div key={s.label} className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                            <div className={cn('w-9 h-9 rounded-lg bg-gradient-to-br flex items-center justify-center mb-3', s.color)}>
                                <Icon className="w-4 h-4 text-white" />
                            </div>
                            <p className="text-xl font-bold text-slate-900 dark:text-white">{s.value}</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
                        </div>
                    )
                })}
            </div>

            {/* Map + Sidebar */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Map */}
                <div className="lg:col-span-2">
                    <DisasterMap disasters={withCoords} />
                </div>

                {/* Active Disaster List */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">All Active ({disasterList.length})</h2>
                    </div>
                    {disasterList.length > 0 ? (
                        <div className="divide-y divide-slate-100 dark:divide-white/5 max-h-[500px] overflow-y-auto">
                            {disasterList.map((d: any) => (
                                <div key={d.id} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                    <div className={cn('w-2 h-2 rounded-full shrink-0', SEVERITY_COLORS[d.severity] || 'bg-slate-400')} />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{d.title || 'Untitled'}</p>
                                        <p className="text-xs text-slate-400 capitalize mt-0.5">
                                            {d.type} &bull; {d.severity}
                                            {d.latitude != null && <span className="ml-1 text-blue-400">&bull; mapped</span>}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="p-10 text-center text-sm text-slate-400">No active disasters</div>
                    )}
                </div>
            </div>
        </div>
    )
}
