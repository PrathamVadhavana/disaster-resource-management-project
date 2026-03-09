/**
 * Thin wrapper for the backend API.
 *
 * All database queries go through the FastAPI backend.
 * Auth tokens come from Supabase.
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function getAccessToken(): Promise<string | null> {
    try {
        const sb = getSupabaseClient()
        const { data } = await sb.auth.getSession()
        return data.session?.access_token || null
    } catch {
        return null
    }
}

async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await getAccessToken()
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> ?? {}),
    }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
    if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `API error ${res.status}`)
    }
    if (res.status === 204) return undefined as unknown as T
    return res.json()
}

/**
 * Database helper that routes queries through the backend API.
 */
export const db = {
    /** Fetch current user profile */
    getProfile: () => apiFetch('/api/auth/me'),

    /** Update current user profile */
    updateProfile: (data: Record<string, any>) =>
        apiFetch('/api/auth/me', { method: 'PUT', body: JSON.stringify(data) }),

    /** Upsert current user profile (onboarding) */
    upsertProfile: (data: Record<string, any>) =>
        apiFetch('/api/auth/me/upsert', { method: 'POST', body: JSON.stringify(data) }),

    /** Upsert role-specific details (donor_details, victim_details, etc.) */
    upsertDetails: (table: string, data: Record<string, any>) =>
        apiFetch(`/api/auth/me/details/${table}`, { method: 'POST', body: JSON.stringify(data) }),
}
