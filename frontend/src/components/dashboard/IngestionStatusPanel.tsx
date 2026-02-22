'use client'

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SourceStatus {
  name: string
  type: string
  active: boolean
  last_polled: string | null
  status: string | null
  error: string | null
  interval_s: number
}

interface IngestionStatus {
  orchestrator_running: boolean
  sources: SourceStatus[]
}

const TYPE_ICON: Record<string, string> = {
  weather: '🌦️',
  disaster_alert: '🌍',
  earthquake: '🔴',
  satellite: '🛰️',
  social_media: '📢',
}

const STATUS_BADGE: Record<string, string> = {
  success: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
  polling: 'bg-blue-100 text-blue-700',
  idle: 'bg-slate-100 text-slate-600',
}

export default function IngestionStatusPanel() {
  const [pollLoading, setPollLoading] = useState<string | null>(null)

  const { data, isLoading, error, refetch } = useQuery<IngestionStatus>({
    queryKey: ['ingestion-status'],
    queryFn: async () => {
      const resp = await fetch(`${API}/api/ingestion/status`)
      if (!resp.ok) throw new Error('Failed to fetch ingestion status')
      return resp.json()
    },
    refetchInterval: 15_000,
  })

  const triggerPoll = async (source: string) => {
    setPollLoading(source)
    try {
      await fetch(`${API}/api/ingestion/poll/${source}`, { method: 'POST' })
      refetch()
    } finally {
      setPollLoading(null)
    }
  }

  const toggleOrchestrator = async (action: 'start' | 'stop') => {
    await fetch(`${API}/api/ingestion/${action}`, { method: 'POST' })
    refetch()
  }

  if (isLoading)
    return <div className="animate-pulse p-6 text-sm text-slate-500">Loading ingestion status…</div>
  if (error)
    return <div className="p-6 text-red-600 text-sm">Failed to load ingestion status</div>
  if (!data) return null

  return (
    <div className="space-y-4">
      {/* Header with orchestrator control */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Data Ingestion</h2>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`w-2 h-2 rounded-full ${
                data.orchestrator_running ? 'bg-green-500 animate-pulse' : 'bg-red-400'
              }`}
            />
            {data.orchestrator_running ? 'Running' : 'Stopped'}
          </div>
        </div>
        <button
          className={`px-3 py-1.5 rounded-md text-xs font-medium ${
            data.orchestrator_running
              ? 'bg-red-100 text-red-700 hover:bg-red-200'
              : 'bg-green-100 text-green-700 hover:bg-green-200'
          }`}
          onClick={() => toggleOrchestrator(data.orchestrator_running ? 'stop' : 'start')}
        >
          {data.orchestrator_running ? 'Stop' : 'Start'} Orchestrator
        </button>
      </div>

      {/* Sources grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.sources.map((source) => {
          const loopName = {
            openweathermap: 'weather',
            gdacs: 'gdacs',
            usgs_earthquakes: 'usgs',
            nasa_firms: 'firms',
            social_media: 'social',
          }[source.name]

          return (
            <div
              key={source.name}
              className="rounded-xl border border-slate-200 dark:border-slate-700 p-4 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{TYPE_ICON[source.type] || '📡'}</span>
                  <span className="font-semibold text-sm capitalize">{source.name.replace(/_/g, ' ')}</span>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    STATUS_BADGE[source.status || 'idle'] || STATUS_BADGE.idle
                  }`}
                >
                  {source.status || 'idle'}
                </span>
              </div>

              <div className="text-xs text-slate-500 space-y-0.5">
                <div>Interval: {source.interval_s}s</div>
                {source.last_polled && (
                  <div>Last poll: {new Date(source.last_polled).toLocaleString()}</div>
                )}
                {source.error && (
                  <div className="text-red-500 truncate" title={source.error}>
                    Error: {source.error}
                  </div>
                )}
              </div>

              {loopName && (
                <button
                  disabled={pollLoading === loopName}
                  onClick={() => triggerPoll(loopName)}
                  className="text-xs bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 px-2.5 py-1 rounded-md font-medium disabled:opacity-50"
                >
                  {pollLoading === loopName ? 'Polling…' : 'Poll Now'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
