'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useMemo } from 'react'
import dynamic from 'next/dynamic'
import {
    Loader2, MapPin, AlertTriangle, Activity, RefreshCw, Package, Box
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
) as React.ComponentType<{ disasters: any[]; resources?: any[] }>

const SEVERITY_COLORS: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-amber-500',
    low: 'bg-green-500',
}

const RESOURCE_STATUS_COLORS: Record<string, string> = {
    allocated: 'bg-blue-500',
    in_use: 'bg-purple-500',
    deployed: 'bg-emerald-500',
    available: 'bg-slate-400',
}

export default function NGOLiveMapPage() {
    const { data: disasters, isLoading, refetch } = useQuery({
        queryKey: ['ngo-live-map-disasters'],
        queryFn: () => api.getDisasters({ status: 'active', limit: 100 }),
        refetchInterval: 15000,
    })

    const { data: resources, refetch: refetchResources } = useQuery({
        queryKey: ['ngo-live-map-resources'],
        queryFn: () => api.getResources({ limit: 500 }),
        refetchInterval: 30000,
    })

    const disasterList = Array.isArray(disasters) ? disasters : []
    const resourceList = Array.isArray(resources) ? resources : []
    const withCoords = useMemo(
        () => disasterList.filter((d: any) => d.latitude != null && d.longitude != null),
        [disasterList]
    )
    const deployedResources = useMemo(
        () => resourceList.filter((r: any) =>
            r.latitude != null && r.longitude != null &&
            (r.status === 'allocated' || r.status === 'in_use' || r.status === 'deployed')
        ),
        [resourceList]
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
                <button
                    onClick={() => { refetch(); refetchResources() }}
                    className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                >
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                    { label: 'Active Disasters', value: disasterList.length, icon: AlertTriangle, color: 'from-red-500 to-orange-600' },
                    { label: 'Critical', value: criticalCount, icon: Activity, color: 'from-orange-500 to-red-600' },
                    { label: 'On Map', value: withCoords.length, icon: MapPin, color: 'from-blue-500 to-cyan-600' },
                    { label: 'Resources Deployed', value: deployedResources.length, icon: Package, color: 'from-emerald-500 to-teal-600' },
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
                <div className="lg:col-span-2 space-y-3">
                    <DisasterMap disasters={withCoords} resources={deployedResources} />

                    {/* Legend */}
                    <div className="rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-4">
                        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">Map Legend</p>
                        <div className="flex flex-wrap gap-x-6 gap-y-2">
                            <div className="flex items-center gap-4">
                                <p className="text-[10px] text-slate-400 uppercase font-semibold">Disasters:</p>
                                {Object.entries(SEVERITY_COLORS).map(([sev, cls]) => (
                                    <div key={sev} className="flex items-center gap-1.5">
                                        <span className={cn('w-3 h-3 rounded-full', cls)} />
                                        <span className="text-[11px] text-slate-500 capitalize">{sev}</span>
                                    </div>
                                ))}
                            </div>
                            <div className="flex items-center gap-4">
                                <p className="text-[10px] text-slate-400 uppercase font-semibold">Resources:</p>
                                <div className="flex items-center gap-1.5">
                                    <span className="w-3 h-3 rounded-sm bg-indigo-500" />
                                    <span className="text-[11px] text-slate-500">Deployed</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Sidebar: Active Disasters + Deployed Resources */}
                <div className="space-y-4">
                    {/* Active Disaster List */}
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-red-500" />
                            <h2 className="font-semibold text-slate-900 dark:text-white">Active Disasters ({disasterList.length})</h2>
                        </div>
                        {disasterList.length > 0 ? (
                            <div className="divide-y divide-slate-100 dark:divide-white/5 max-h-[260px] overflow-y-auto">
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

                    {/* Deployed Resources List */}
                    <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5 flex items-center gap-2">
                            <Box className="w-4 h-4 text-emerald-500" />
                            <h2 className="font-semibold text-slate-900 dark:text-white">Deployed Resources ({deployedResources.length})</h2>
                        </div>
                        {deployedResources.length > 0 ? (
                            <div className="divide-y divide-slate-100 dark:divide-white/5 max-h-[200px] overflow-y-auto">
                                {deployedResources.map((r: any) => (
                                    <div key={r.id} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                                        <div className={cn('w-2 h-2 rounded-sm shrink-0', RESOURCE_STATUS_COLORS[r.status] || 'bg-slate-400')} />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{r.name || 'Resource'}</p>
                                            <p className="text-xs text-slate-400 capitalize mt-0.5">
                                                {r.type} &bull; {r.quantity || 0} {r.unit || 'units'} &bull; {r.status}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="p-8 text-center text-sm text-slate-400">
                                <Package className="w-6 h-6 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
                                <p>No deployed resources</p>
                                <p className="text-xs text-slate-400 mt-1">Resources will appear here when allocated to disasters</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
