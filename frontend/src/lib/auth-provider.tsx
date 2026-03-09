'use client'

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { getSupabaseClient, type User as SupabaseUser, type Session } from '@/lib/supabase/client'
import { db } from '@/lib/db'

/** Map a user's role to their dashboard path */
function getRoleDashboardPath(role?: string | null): string {
  switch (role) {
    case 'victim': return '/victim'
    case 'ngo': return '/ngo'
    case 'donor': return '/donor'
    case 'volunteer': return '/volunteer'
    case 'admin': return '/admin'
    default: return '/onboarding'
  }
}

// Minimal profile type — matches the public.users table
interface UserProfile {
  id: string
  email: string
  full_name: string | null
  role: string
  phone: string | null
  organization: string | null
  is_profile_completed: boolean
  metadata: any
  created_at: string
  updated_at: string
  [key: string]: any
}

interface AuthContextType {
  user: SupabaseUser | null
  profile: UserProfile | null
  idToken: string | null
  loading: boolean
  role: string | null
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>
  signUp: (email: string, password: string, fullName?: string, role?: string) => Promise<{ error: Error | null }>
  signOut: () => Promise<void>
  updateProfile: (updates: Partial<UserProfile>) => Promise<void>
  getIdToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SupabaseUser | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [idToken, setIdToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [role, setRole] = useState<string | null>(null)
  const loadingRef = useRef(true)
  const router = useRouter()

  const supabase = getSupabaseClient()

  // Keep ref in sync
  useEffect(() => { loadingRef.current = loading }, [loading])

  useEffect(() => {
    let mounted = true

    // Hard safety timeout — never block the app longer than 5 seconds
    const safetyTimer = setTimeout(() => {
      if (mounted && loadingRef.current) {
        console.warn('AuthProvider: safety timeout reached, forcing loading=false')
        setLoading(false)
      }
    }, 5000)

    // Supabase auth state listener
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (!mounted) return

        if (session?.user) {
          setUser(session.user)

          const token = session.access_token
          setIdToken(token)

          const appMeta = session.user.app_metadata || {}
          const userMeta = session.user.user_metadata || {}
          const claimRole = appMeta.role || userMeta.role || null
          setRole(claimRole)

          // Store token in cookie for middleware access
          document.cookie = `sb-token=${token}; path=/; max-age=3600; SameSite=Lax`
          if (claimRole) {
            document.cookie = `sb-role=${claimRole}; path=/; max-age=3600; SameSite=Lax`
          }

          await loadProfile(session.user, session)
        } else {
          setUser(null)
          setProfile(null)
          setIdToken(null)
          setRole(null)
          // Clear cookies
          document.cookie = 'sb-token=; path=/; max-age=0'
          document.cookie = 'sb-role=; path=/; max-age=0'
          document.cookie = 'profile-completed=; path=/; max-age=0'
          setLoading(false)
        }
      },
    )

    return () => {
      mounted = false
      clearTimeout(safetyTimer)
      subscription.unsubscribe()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** Race a promise against a timeout — returns null on timeout */
  const withTimeout = <T,>(promise: Promise<T>, ms: number): Promise<T | null> =>
    Promise.race([
      promise,
      new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
    ])

  const loadProfile = async (currentUser: SupabaseUser, session?: Session | null) => {
    try {
      let profileData: UserProfile | null = null

      // 1. Try fetching the profile from the backend API (3-second max)
      const fetchResult = await withTimeout(
        db.getProfile().catch(() => null),
        3000,
      )

      if (fetchResult) {
        profileData = fetchResult as UserProfile
      }

      // 2. If no profile, create one via upsert (2-second max)
      if (!profileData) {
        const appMeta = currentUser.app_metadata || {}
        const userMeta = currentUser.user_metadata || {}
        const claimRole = appMeta.role || userMeta.role || 'victim'
        const insertData = {
          id: currentUser.id,
          email: currentUser.email!,
          role: claimRole,
          full_name: userMeta.full_name || null,
          updated_at: new Date().toISOString(),
        }

        const upsertResult = await withTimeout(
          db.upsertProfile(insertData).catch(() => null),
          2000,
        )

        if (upsertResult) {
          const refetch = await withTimeout(
            db.getProfile().catch(() => null),
            2000,
          )
          if (refetch) {
            profileData = refetch as UserProfile | null
          }
        }
      }

      setProfile(profileData)
      if (profileData?.role) {
        setRole(profileData.role)
        // Sync sb-role cookie with backend state so middleware can route correctly
        document.cookie = `sb-role=${profileData.role}; path=/; max-age=3600; SameSite=Lax`
      }
      // Sync profile-completed cookie with backend state
      if (profileData?.is_profile_completed) {
        document.cookie = `profile-completed=true; path=/; max-age=86400; SameSite=Lax`
      }
    } catch (error) {
      console.error('Error loading profile:', error)
    } finally {
      setLoading(false)
    }
  }

  const signIn = async (email: string, password: string) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error

      const session = data.session
      const sbUser = data.user

      // Get token and role
      const token = session.access_token
      setIdToken(token)
      document.cookie = `sb-token=${token}; path=/; max-age=3600; SameSite=Lax`

      const appMeta = sbUser.app_metadata || {}
      const userMeta = sbUser.user_metadata || {}
      const claimRole = appMeta.role || userMeta.role || null
      setRole(claimRole)
      if (claimRole) {
        document.cookie = `sb-role=${claimRole}; path=/; max-age=3600; SameSite=Lax`
      }

      // Check profile completion to decide redirect target
      try {
        const profileRow = await db.getProfile().catch(() => null) as { is_profile_completed: boolean; role?: string } | null

        const dbRole = profileRow?.role || claimRole

        if (dbRole === 'admin') {
          router.push('/admin')
        } else if (profileRow?.is_profile_completed && dbRole) {
          document.cookie = `profile-completed=true; path=/; max-age=86400; SameSite=Lax`
          router.push(getRoleDashboardPath(dbRole))
        } else {
          // Check the profile-completed cookie as fallback
          const hasCompletedCookie = document.cookie.split('; ').some(c => c === 'profile-completed=true')
          if (hasCompletedCookie && dbRole) {
            router.push(getRoleDashboardPath(dbRole))
          } else if (dbRole) {
            router.push('/onboarding')
          } else {
            router.push('/onboarding')
          }
        }
      } catch {
        // Even on error, check cookie fallback before defaulting to onboarding
        const hasCompletedCookie = document.cookie.split('; ').some(c => c === 'profile-completed=true')
        if (hasCompletedCookie && claimRole) {
          router.push(getRoleDashboardPath(claimRole))
        } else {
          router.push('/onboarding')
        }
      }
      router.refresh()

      return { error: null }
    } catch (err: any) {
      return { error: err }
    }
  }

  const signUp = async (email: string, password: string, fullName?: string, role?: string) => {
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName || '',
            role: role || 'victim',
          },
        },
      })
      if (error) throw error

      const sbUser = data.user
      if (!sbUser) throw new Error('User creation failed')

      // Register with backend (creates DB profile + sets app_metadata)
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const token = data.session?.access_token || ''
      await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          email,
          password,
          full_name: fullName || '',
          role: role || 'victim',
        }),
      })

      return { error: null }
    } catch (err: any) {
      return { error: err }
    }
  }

  const signOutFn = async () => {
    // Clear local state immediately so UI updates before navigation
    setUser(null)
    setProfile(null)
    setIdToken(null)
    setRole(null)

    // Clear cookies
    document.cookie = 'sb-token=; path=/; max-age=0'
    document.cookie = 'sb-role=; path=/; max-age=0'
    document.cookie = 'profile-completed=; path=/; max-age=0'

    await supabase.auth.signOut()

    // Hard navigation to /login — router.push can race with stale cookies
    window.location.href = '/login'
  }

  const updateProfileFn = async (updates: Partial<UserProfile>) => {
    if (!user) return

    try {
      await db.updateProfile(updates)
      setProfile((prev) => (prev ? { ...prev, ...updates } : null))
    } catch (error) {
      console.error('Profile update error:', error)
    }
  }

  const getIdTokenFn = async (): Promise<string | null> => {
    if (!user) return null
    try {
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token || null
      if (token) {
        setIdToken(token)
        document.cookie = `sb-token=${token}; path=/; max-age=3600; SameSite=Lax`
      }
      return token
    } catch {
      return null
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        idToken,
        loading,
        role,
        signIn,
        signUp,
        signOut: signOutFn,
        updateProfile: updateProfileFn,
        getIdToken: getIdTokenFn,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}