'use client'

import dynamic from 'next/dynamic'
import IngestionStatusPanel from '@/components/dashboard/IngestionStatusPanel'

// Leaflet must be loaded client-side only (no SSR)
const LiveImpactMap = dynamic(
  () => import('@/components/dashboard/LiveImpactMap'),
  { ssr: false, loading: () => <div className="h-[700px] animate-pulse bg-slate-100 dark:bg-slate-800 rounded-2xl" /> }
)

export default function LiveMapPage() {
  return (
    <div className="space-y-6 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Live Impact Map</h1>
        <p className="text-sm text-slate-500 mt-1">
          Real-time disaster events from GDACS, USGS, NASA FIRMS, social media, and weather feeds.
          Map updates automatically via WebSocket.
        </p>
      </div>

      {/* Map */}
      <LiveImpactMap />

      {/* Ingestion status */}
      <IngestionStatusPanel />
    </div>
  )
}
