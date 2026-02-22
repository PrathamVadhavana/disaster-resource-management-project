'use client'

import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, useMap } from 'react-leaflet'
import { Icon, LatLngBounds } from 'leaflet'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { supabase } from '@/lib/supabase'
import { useRealtimeEvents, useRealtimeAlerts, IngestedEvent } from '@/hooks/use-realtime-events'
import { api } from '@/lib/api'
import 'leaflet/dist/leaflet.css'

// ── Severity colours & icons ──────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#DC2626',
  high: '#EA580C',
  medium: '#F59E0B',
  low: '#10B981',
}

const EVENT_TYPE_EMOJI: Record<string, string> = {
  gdacs_alert: '🌍',
  earthquake: '🔴',
  fire_hotspot: '🔥',
  social_sos: '📢',
  weather_update: '🌦️',
}

function severityIcon(severity: string, size: number = 28): Icon {
  const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.medium
  return new Icon({
    iconUrl: `data:image/svg+xml,${encodeURIComponent(`
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
        <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - 2}" fill="${color}" opacity="0.85" stroke="white" stroke-width="2"/>
      </svg>
    `)}`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  })
}

// ── Auto-fit helper ───────────────────────────────────────────────────────

function FitBounds({ bounds }: { bounds: LatLngBounds | null }) {
  const map = useMap()
  useEffect(() => {
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
    }
  }, [bounds, map])
  return null
}

// ── Main Component ────────────────────────────────────────────────────────

export default function LiveImpactMap() {
  const queryClient = useQueryClient()

  // Live events from Supabase Realtime
  const { events: liveEvents, connected } = useRealtimeEvents({ maxEvents: 300 })
  const { alerts, latestCritical, dismissCritical } = useRealtimeAlerts()

  // Also fetch recent events from API for initial population
  const { data: historicalEvents = [] } = useQuery({
    queryKey: ['ingested-events-recent'],
    queryFn: async () => {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/ingestion/events?limit=200`
      )
      if (!resp.ok) return []
      const data = await resp.json()
      return (data.events || []) as IngestedEvent[]
    },
    refetchInterval: 60_000,
  })

  // Merge live + historical, deduplicated by id
  const allEvents = useMemo(() => {
    const map = new Map<string, IngestedEvent>()
    for (const e of historicalEvents) map.set(e.id, e)
    for (const e of liveEvents) map.set(e.id, e) // live overwrites
    return Array.from(map.values())
      .filter((e) => e.latitude != null && e.longitude != null)
      .sort((a, b) => new Date(b.ingested_at).getTime() - new Date(a.ingested_at).getTime())
  }, [liveEvents, historicalEvents])

  // Compute map bounds
  const bounds = useMemo(() => {
    if (allEvents.length === 0) return null
    const lats = allEvents.map((e) => e.latitude!)
    const lons = allEvents.map((e) => e.longitude!)
    return new LatLngBounds(
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)]
    )
  }, [allEvents])

  // Event type filter
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const filteredEvents = useMemo(
    () => (typeFilter === 'all' ? allEvents : allEvents.filter((e) => e.event_type === typeFilter)),
    [allEvents, typeFilter]
  )

  // Stat counts
  const stats = useMemo(() => {
    const byType: Record<string, number> = {}
    const bySeverity: Record<string, number> = {}
    for (const e of allEvents) {
      byType[e.event_type] = (byType[e.event_type] || 0) + 1
      if (e.severity) bySeverity[e.severity] = (bySeverity[e.severity] || 0) + 1
    }
    return { byType, bySeverity, total: allEvents.length }
  }, [allEvents])

  return (
    <div className="relative w-full h-[700px] rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-lg">
      {/* ── Critical Alert Banner ─────────────────────────────────────── */}
      {latestCritical && (
        <div className="absolute top-0 left-0 right-0 z-[2000] bg-red-600 text-white px-4 py-2 flex items-center justify-between animate-pulse">
          <span className="font-semibold text-sm">
            🚨 CRITICAL ALERT: {latestCritical.subject || 'New critical disaster detected'}
          </span>
          <button
            onClick={dismissCritical}
            className="text-white/80 hover:text-white text-xs underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Map ───────────────────────────────────────────────────────── */}
      <MapContainer
        center={[20, 0]}
        zoom={2}
        scrollWheelZoom
        style={{ height: '100%', width: '100%' }}
        className="z-0"
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        />
        <FitBounds bounds={bounds} />

        {filteredEvents.map((event) => (
          <Marker
            key={event.id}
            position={[event.latitude!, event.longitude!]}
            icon={severityIcon(event.severity || 'medium')}
          >
            <Popup maxWidth={320}>
              <div className="text-sm space-y-1">
                <div className="flex items-center gap-1.5 font-bold text-base">
                  <span>{EVENT_TYPE_EMOJI[event.event_type] || '📌'}</span>
                  <span>{event.title || 'Unknown Event'}</span>
                </div>
                <div className="text-slate-600 text-xs">{event.description?.slice(0, 200)}</div>
                <div className="grid grid-cols-2 gap-1 pt-1 text-xs">
                  <span className="text-slate-500">Type:</span>
                  <span className="font-medium">{event.event_type.replace(/_/g, ' ')}</span>
                  <span className="text-slate-500">Severity:</span>
                  <span
                    className="font-medium"
                    style={{ color: SEVERITY_COLORS[event.severity || 'medium'] }}
                  >
                    {event.severity?.toUpperCase()}
                  </span>
                  <span className="text-slate-500">Time:</span>
                  <span className="font-medium">
                    {new Date(event.ingested_at).toLocaleString()}
                  </span>
                  {event.processed && (
                    <>
                      <span className="text-slate-500">Status:</span>
                      <span className="text-green-600 font-medium">Processed</span>
                    </>
                  )}
                </div>
                {event.disaster_id && (
                  <a
                    href={`/dashboard/disasters/${event.disaster_id}`}
                    className="block text-blue-600 underline text-xs mt-1"
                  >
                    View Disaster Record →
                  </a>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* ── Controls overlay ──────────────────────────────────────────── */}
      <div className="absolute top-2 right-2 z-[1000] flex flex-col gap-2">
        {/* Connection indicator */}
        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur rounded-lg px-3 py-1.5 shadow text-xs flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-400'}`}
          />
          {connected ? 'Live' : 'Connecting…'}
          <span className="text-slate-400 ml-1">{stats.total} events</span>
        </div>

        {/* Type filter */}
        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur rounded-lg px-3 py-2 shadow">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-transparent text-xs outline-none w-full cursor-pointer"
          >
            <option value="all">All Types ({stats.total})</option>
            {Object.entries(stats.byType).map(([type, count]) => (
              <option key={type} value={type}>
                {EVENT_TYPE_EMOJI[type] || '📌'} {type.replace(/_/g, ' ')} ({count})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Severity legend ───────────────────────────────────────────── */}
      <div className="absolute bottom-4 right-4 z-[1000] bg-white/90 dark:bg-slate-800/90 backdrop-blur p-3 rounded-lg shadow text-xs">
        <h4 className="font-semibold mb-1.5">Severity</h4>
        <div className="space-y-1">
          {Object.entries(SEVERITY_COLORS).map(([level, color]) => (
            <div key={level} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
              <span className="capitalize">{level}</span>
              <span className="text-slate-400 ml-auto">{stats.bySeverity[level] || 0}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Recent feed ticker ────────────────────────────────────────── */}
      <div className="absolute bottom-4 left-4 z-[1000] bg-white/90 dark:bg-slate-800/90 backdrop-blur p-3 rounded-lg shadow max-w-xs max-h-48 overflow-y-auto">
        <h4 className="font-semibold text-xs mb-1.5">Live Feed</h4>
        {allEvents.slice(0, 8).map((e) => (
          <div key={e.id} className="text-[11px] py-0.5 border-b border-slate-100 dark:border-slate-700 last:border-0">
            <span className="mr-1">{EVENT_TYPE_EMOJI[e.event_type] || '📌'}</span>
            <span
              className="font-medium"
              style={{ color: SEVERITY_COLORS[e.severity || 'medium'] }}
            >
              [{e.severity?.toUpperCase()}]
            </span>{' '}
            {e.title?.slice(0, 50) || e.event_type}
          </div>
        ))}
        {allEvents.length === 0 && (
          <div className="text-[11px] text-slate-400">Waiting for events…</div>
        )}
      </div>
    </div>
  )
}
