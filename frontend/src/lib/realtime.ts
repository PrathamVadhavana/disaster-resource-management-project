/**
 * SSE-based realtime helper.
 *
 * Connects to the backend SSE endpoint and dispatches events to listeners.
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface RealtimeEvent {
    table: string
    type: 'INSERT' | 'UPDATE' | 'DELETE'
    row: Record<string, any>
}

type RealtimeCallback = (event: RealtimeEvent) => void

interface Subscription {
    table: string
    callback: RealtimeCallback
}

let _eventSource: EventSource | null = null
let _subscriptions: Subscription[] = []
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
let _connecting = false

async function _getToken(): Promise<string | null> {
    try {
        const sb = getSupabaseClient()
        const { data } = await sb.auth.getSession()
        return data.session?.access_token || null
    } catch {
        return null
    }
}

function _connect() {
    if (_connecting || typeof window === 'undefined') return
    _connecting = true

    const tables = [...new Set(_subscriptions.map((s) => s.table))]
    if (tables.length === 0) {
        _connecting = false
        return
    }

    // EventSource doesn't support custom headers, so we pass the token as a query param
    // The backend should accept ?token= as an alternative to Authorization header
    _getToken().then((token) => {
        if (_eventSource) {
            _eventSource.close()
            _eventSource = null
        }

        const params = new URLSearchParams({ tables: tables.join(',') })
        if (token) params.set('token', token)

        const url = `${API_BASE}/api/realtime/events?${params.toString()}`
        const es = new EventSource(url)

        es.addEventListener('db_change', (e: MessageEvent) => {
            try {
                const event: RealtimeEvent = JSON.parse(e.data)
                for (const sub of _subscriptions) {
                    if (sub.table === event.table) {
                        sub.callback(event)
                    }
                }
            } catch (err) {
                console.error('[realtime] failed to parse event', err)
            }
        })

        es.addEventListener('error', () => {
            es.close()
            _eventSource = null
            _connecting = false
            // Reconnect after a delay
            if (_reconnectTimer) clearTimeout(_reconnectTimer)
            _reconnectTimer = setTimeout(() => _connect(), 5000)
        })

        es.addEventListener('connected', () => {
            _connecting = false
        })

        _eventSource = es
        _connecting = false
    })
}

/**
 * Subscribe to realtime changes on a table.
 * Returns an unsubscribe function.
 */
export function subscribeToTable(
    table: string,
    callback: RealtimeCallback,
): () => void {
    const sub: Subscription = { table, callback }
    _subscriptions.push(sub)

    // Reconnect to include the new table
    _connect()

    return () => {
        _subscriptions = _subscriptions.filter((s) => s !== sub)
        // If no more subscriptions for this table, reconnect without it
        const remaining = _subscriptions.map((s) => s.table)
        if (!remaining.includes(table)) {
            _connect()
        }
        // If nothing left, close
        if (_subscriptions.length === 0 && _eventSource) {
            _eventSource.close()
            _eventSource = null
        }
    }
}

/**
 * Close all realtime connections.
 */
export function closeRealtime() {
    if (_eventSource) {
        _eventSource.close()
        _eventSource = null
    }
    _subscriptions = []
    if (_reconnectTimer) {
        clearTimeout(_reconnectTimer)
        _reconnectTimer = null
    }
}
