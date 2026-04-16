/**
 * Supabase client-side SDK initialisation.
 *
 * Provides authentication, database, and storage through the Supabase JS client.
 */
import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient, Session, User } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

/** Singleton Supabase client — safe to call multiple times */
let _supabase: SupabaseClient | null = null
export function getSupabaseClient(): SupabaseClient {
    if (!_supabase) {
        _supabase = createBrowserClient(supabaseUrl, supabaseAnonKey)
    }
    return _supabase
}

/** Convenience re-export of types */
export type { SupabaseClient, Session, User }
