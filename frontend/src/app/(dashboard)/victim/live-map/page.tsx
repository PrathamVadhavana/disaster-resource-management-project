'use client'

import dynamic from 'next/dynamic'
import { Loader2, Radio, MapPin } from 'lucide-react'

const GlobalDisasterMap = dynamic(() => import('@/components/map/GlobalDisasterMap'), {
    ssr: false,
    loading: () => (
        <div className="w-full h-full rounded-2xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
                <p className="text-sm text-slate-500">Loading live disaster map...</p>
            </div>
        </div>
    ),
})

export default function VictimLiveMapPage() {
    return (
        <div className="space-y-4 h-[calc(100vh-6rem)]">
            <div className="flex items-center justify-between flex-shrink-0">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <MapPin className="w-5 h-5 text-red-500" />
                        Live Disaster Map
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        See real-time disaster events happening around the world
                    </p>
                </div>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-xs font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    Live
                </span>
            </div>
            <div className="flex-1 min-h-0" style={{ height: 'calc(100% - 4rem)' }}>
                <GlobalDisasterMap />
            </div>
        </div>
    )
}
