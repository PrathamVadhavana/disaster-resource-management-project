/**
 * Supabase server-side client for Next.js Server Components / API Routes.
 *
 * Uses the service role key for admin operations.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

let _adminClient: SupabaseClient | null = null

export function getAdminClient(): SupabaseClient {
    if (!_adminClient) {
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || ''
        const key = process.env.SUPABASE_SERVICE_ROLE_KEY || ''
        if (!url || !key) {
            throw new Error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for admin operations')
        }
        _adminClient = createClient(url, key)
    }
    return _adminClient
}

/** Backward-compat alias */
export const getAdminAuth = getAdminClient
