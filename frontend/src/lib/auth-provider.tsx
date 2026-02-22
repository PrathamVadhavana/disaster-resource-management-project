'use client'

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { User, Session, AuthError } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/client'
import { Database } from '@/types/supabase'

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

type UserProfile = Database['public']['Tables']['users']['Row']
type UserProfileUpdate = Database['public']['Tables']['users']['Update']
type UserProfileInsert = Database['public']['Tables']['users']['Insert']
type UserRole = Database['public']['Enums']['user_role']

interface AuthContextType {
  user: User | null
  profile: UserProfile | null
  session: Session | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: AuthError | null }>
  signUp: (email: string, password: string, fullName?: string) => Promise<{ error: AuthError | null }>
  signOut: () => Promise<void>
  updateProfile: (updates: UserProfileUpdate) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const loadingRef = useRef(true)
  const router = useRouter()

  const supabase = createClient()

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

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!mounted) return
      setSession(session)
      setUser(session?.user ?? null)
      if (session?.user) {
        loadProfile(session.user)
      } else {
        setLoading(false)
      }
    })

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (!mounted) return
      setSession(session)
      setUser(session?.user ?? null)
      if (session?.user) {
        await loadProfile(session.user)
      } else {
        setProfile(null)
        setLoading(false)
      }
    })

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

  const loadProfile = async (currentUser: User) => {
    try {
      let profileData: UserProfile | null = null

      // 1. Try fetching the profile (3-second max)
      const fetchResult = await withTimeout(
        Promise.resolve(supabase.from('users').select('*').eq('id', currentUser.id).maybeSingle()),
        3000,
      )

      if (fetchResult && !('error' in fetchResult && fetchResult.error) && fetchResult.data) {
        profileData = fetchResult.data as UserProfile
      }

      // 2. If no profile, single upsert fallback (2-second max)
      if (!profileData) {
        const metadata = currentUser.user_metadata || {}
        const role = (metadata.role as UserRole) || 'victim'
        const insertData: UserProfileInsert = {
          id: currentUser.id,
          email: currentUser.email!,
          role,
          full_name: (metadata.full_name as string) || null,
          updated_at: new Date().toISOString(),
        }

        const upsertResult = await withTimeout(
          Promise.resolve((supabase.from('users') as any).upsert(insertData)),
          2000,
        )

        if (upsertResult && !(upsertResult as any).error) {
          const refetch = await withTimeout(
            Promise.resolve(supabase.from('users').select('*').eq('id', currentUser.id).maybeSingle()),
            2000,
          )
          if (refetch && refetch.data) {
            profileData = refetch.data as UserProfile | null
          }
        }
      }

      setProfile(profileData)
    } catch (error) {
      console.error('Error loading profile:', error)
    } finally {
      setLoading(false)
    }
  }

  const signIn = async (email: string, password: string) => {
    const { data: authData, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    if (!error && authData.user) {
      // Check profile completion to decide redirect target
      try {
        const { data: profileRow } = await supabase
          .from('users')
          .select('is_profile_completed, role')
          .eq('id', authData.user.id)
          .maybeSingle()

        const profileResult = profileRow as { is_profile_completed: boolean; role?: string } | null
        if (profileResult?.is_profile_completed) {
          router.push(getRoleDashboardPath(profileResult.role))
        } else {
          router.push('/onboarding')
        }
      } catch {
        // Table may not exist — send to onboarding
        router.push('/onboarding')
      }
      router.refresh()
    }
    return { error }
  }

  const signUp = async (email: string, password: string, fullName?: string, role?: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
          ...(role && { role }),
        },
      },
    })

    // Don't manually insert into users table — the DB trigger handles profile creation
    // after the user verifies their email and completes auth.

    return { error }
  }

  const signOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  const updateProfile = async (updates: UserProfileUpdate) => {
    if (!user) return

    // Cast needed: Supabase SDK resolves Update type to 'never' due to generic chain issue
    const { error } = await (supabase.from('users') as any)
      .update(updates)
      .eq('id', user.id)

    if (!error) {
      setProfile((prev) => (prev ? { ...prev, ...(updates as UserProfile) } : null))
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        session,
        loading,
        signIn,
        signUp,
        signOut,
        updateProfile,
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