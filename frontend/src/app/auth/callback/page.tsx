'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getSupabaseClient } from '@/lib/supabase/client'

function getRoleDashboard(role: string): string {
    switch (role) {
        case 'victim': return '/victim'
        case 'ngo': return '/ngo'
        case 'donor': return '/donor'
        case 'volunteer': return '/volunteer'
        case 'admin': return '/admin'
        default: return '/onboarding'
    }
}

export default function AuthCallbackPage() {
    const router = useRouter()
    const [error, setError] = useState<string | null>(null)
    const handled = useRef(false)

    useEffect(() => {
        const supabase = getSupabaseClient()

        const processSession = async () => {
            if (handled.current) return
            handled.current = true

            try {
                // Wait briefly for Supabase to detect the hash fragment
                // The client auto-detects #access_token when detectSessionInUrl is true
                const { data: { session }, error: sessionError } = await supabase.auth.getSession()

                if (sessionError) {
                    console.error('Auth callback error:', sessionError)
                    setError(sessionError.message)
                    return
                }

                if (!session) {
                    // No session yet — maybe the hash hasn't been consumed.
                    // Give it a moment and retry once.
                    await new Promise(r => setTimeout(r, 500))
                    const retry = await supabase.auth.getSession()
                    if (retry.data.session) {
                        await handleSession(retry.data.session)
                        return
                    }
                    router.replace('/login?error=no_session')
                    return
                }

                await handleSession(session)
            } catch (err) {
                console.error('Auth callback error:', err)
                setError(err instanceof Error ? err.message : 'Authentication failed')
            }
        }

        const handleSession = async (session: { access_token: string; user: any }) => {
            const token = session.access_token
            const userMeta = session.user.user_metadata || {}
            const appMeta = session.user.app_metadata || {}
            const metaRole = appMeta.role || userMeta.role || null

            // Set auth cookies immediately
            document.cookie = `sb-token=${token}; path=/; max-age=3600; SameSite=Lax`
            if (metaRole) {
                document.cookie = `sb-role=${metaRole}; path=/; max-age=3600; SameSite=Lax`
            }

            const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            }

            // 1. Try fetching existing profile
            let profile: any = null
            try {
                const res = await fetch(`${API_BASE}/api/auth/me`, { headers })
                if (res.ok) {
                    profile = await res.json()
                }
            } catch {
                // Profile doesn't exist yet — that's fine
            }

            // 2. If no profile, create one via upsert
            if (!profile || !profile.role) {
                try {
                    const upsertRes = await fetch(`${API_BASE}/api/auth/me/upsert`, {
                        method: 'POST',
                        headers,
                        body: JSON.stringify({
                            id: session.user.id,
                            email: session.user.email,
                            full_name: userMeta.full_name || userMeta.name || '',
                            role: metaRole || 'victim',
                            updated_at: new Date().toISOString(),
                        }),
                    })
                    if (upsertRes.ok) {
                        profile = await upsertRes.json()
                    }
                } catch (e) {
                    console.warn('Profile upsert failed:', e)
                }
            }

            // 3. Also try to register with backend to set app_metadata
            //    (non-fatal — may fail for existing users, that's OK)
            try {
                await fetch(`${API_BASE}/api/auth/register`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        email: session.user.email,
                        password: '',
                        full_name: userMeta.full_name || userMeta.name || '',
                        role: metaRole || profile?.role || 'victim',
                    }),
                })
            } catch {
                // Expected to fail for existing users
            }

            // 4. Set final cookies from profile data
            const finalRole = profile?.role || metaRole
            if (finalRole) {
                document.cookie = `sb-role=${finalRole}; path=/; max-age=3600; SameSite=Lax`
            }
            if (profile?.is_profile_completed) {
                document.cookie = `profile-completed=true; path=/; max-age=86400; SameSite=Lax`
            }

            // 5. Redirect based on role and profile completion
            if (finalRole && profile?.is_profile_completed) {
                router.replace(getRoleDashboard(finalRole))
            } else {
                router.replace('/onboarding')
            }
        }

        // Listen for auth state change (fires when hash fragment is consumed)
        const { data: { subscription } } = supabase.auth.onAuthStateChange(
            async (event, session) => {
                if (session && !handled.current) {
                    await processSession()
                }
            },
        )

        // Also try immediately in case session is already available
        processSession()

        // Safety timeout
        const timeout = setTimeout(() => {
            if (!handled.current) {
                handled.current = true
                router.replace('/login?error=auth_timeout')
            }
        }, 10000)

        return () => {
            subscription.unsubscribe()
            clearTimeout(timeout)
        }
    }, [router])

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-slate-950">
                <div className="text-center">
                    <p className="text-red-400 mb-4">Authentication error: {error}</p>
                    <a href="/login" className="text-blue-400 underline">Back to login</a>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-950">
            <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto" />
                <p className="mt-4 text-slate-400">Completing sign in...</p>
            </div>
        </div>
    )
}
