'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { supabase } from '@/lib/supabase'
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
 * Hook: subscribe to live ingested_events via Supabase Realtime.
 */
export function useRealtimeEvents(options: UseRealtimeEventsOptions = {}) {
  const { eventType, maxEvents = 200 } = options
  const [events, setEvents] = useState<IngestedEvent[]>([])
  const [connected, setConnected] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    // Build channel with optional filter
    let channelBuilder = supabase
      .channel('ingested-events-live')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'ingested_events',
          ...(eventType ? { filter: `event_type=eq.${eventType}` } : {}),
        },
        (payload) => {
          const newEvent = payload.new as IngestedEvent
          setEvents((prev) => {
            const updated = [newEvent, ...prev]
            return updated.slice(0, maxEvents)
          })
          // Invalidate related queries so dashboards refresh
          queryClient.invalidateQueries({ queryKey: ['disasters'] })
          queryClient.invalidateQueries({ queryKey: ['predictions'] })
        }
      )

    const channel = channelBuilder.subscribe((status) => {
      setConnected(status === 'SUBSCRIBED')
    })

    return () => {
      supabase.removeChannel(channel)
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
    const channel = supabase
      .channel('alert-notifications-live')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'alert_notifications',
        },
        (payload) => {
          const alert = payload.new as AlertNotification
          setAlerts((prev) => [alert, ...prev].slice(0, 100))
          if (alert.severity === 'critical') {
            setLatestCritical(alert)
          }
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  const dismissCritical = useCallback(() => setLatestCritical(null), [])

  return { alerts, latestCritical, dismissCritical }
}
