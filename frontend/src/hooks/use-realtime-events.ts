'use client'

import { useEffect, useState, useCallback } from 'react'
import { subscribeToTable, type RealtimeEvent } from '@/lib/realtime'
import { useQueryClient } from '@tanstack/react-query'

/**
 * Ingested event from the realtime subscription.
 */
export interface IngestedEvent {
  id: string
  source_id: string
  external_id: string | null
  event_type: string
  title: string | null
  description: string | null
  severity: string | null
  latitude: number | null
  longitude: number | null
  location_name: string | null
  raw_payload: Record<string, unknown>
  ingested_at: string
  processed: boolean
  disaster_id: string | null
  prediction_ids: string[]
}

export interface AlertNotification {
  id: string
  event_id: string | null
  disaster_id: string | null
  channel: string
  recipient: string
  severity: string
  status: string
  subject: string | null
  body: string | null
  created_at: string
}

interface UseRealtimeEventsOptions {
  /** Only include events of this type (e.g. 'gdacs_alert', 'earthquake') */
  eventType?: string
  /** Max events to keep in state (oldest evicted first) */
  maxEvents?: number
}

/**
 * Hook: subscribe to live ingested_events via SSE realtime.
 */
export function useRealtimeEvents(options: UseRealtimeEventsOptions = {}) {
  const { eventType, maxEvents = 200 } = options
  const [events, setEvents] = useState<IngestedEvent[]>([])
  const [connected, setConnected] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    setConnected(true)

    const unsub = subscribeToTable('ingested_events', (evt: RealtimeEvent) => {
      if (evt.type !== 'INSERT') return
      const newEvent = evt.row as IngestedEvent
      // Optional client-side filter by event type
      if (eventType && newEvent.event_type !== eventType) return

      setEvents((prev) => {
        const updated = [newEvent, ...prev]
        return updated.slice(0, maxEvents)
      })
      // Invalidate related queries so dashboards refresh
      queryClient.invalidateQueries({ queryKey: ['disasters'] })
      queryClient.invalidateQueries({ queryKey: ['predictions'] })
    })

    return () => {
      unsub()
      setConnected(false)
    }
  }, [eventType, maxEvents, queryClient])

  const clearEvents = useCallback(() => setEvents([]), [])

  return { events, connected, clearEvents }
}

/**
 * Hook: subscribe to live alert_notifications.
 */
export function useRealtimeAlerts() {
  const [alerts, setAlerts] = useState<AlertNotification[]>([])
  const [latestCritical, setLatestCritical] = useState<AlertNotification | null>(null)

  useEffect(() => {
    const unsub = subscribeToTable('alert_notifications', (evt: RealtimeEvent) => {
      if (evt.type !== 'INSERT') return
      const alert = evt.row as AlertNotification
      setAlerts((prev) => [alert, ...prev].slice(0, 100))
      if (alert.severity === 'critical') {
        setLatestCritical(alert)
      }
    })

    return () => {
      unsub()
    }
  }, [])

  const dismissCritical = useCallback(() => setLatestCritical(null), [])

  return { alerts, latestCritical, dismissCritical }
}
