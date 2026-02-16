'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { User, Session, AuthError } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/client'
import { Database } from '@/types/supabase'

/** Map a user's role to their dashboard path */
function getRoleDashboardPath(role?: string | null): string {
  switch (role) {
    case 'victim': return '/victim'
    case 'admin': return '/admin'
    // future: case 'donor': return '/donor'
    // future: case 'ngo': return '/ngo'
    default: return '/dashboard'
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
  const router = useRouter()

  const supabase = createClient()

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
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
      setSession(session)
      setUser(session?.user ?? null)
      if (session?.user) {
        await loadProfile(session.user)
      } else {
        setProfile(null)
        setLoading(false)
      }
    })

    return () => subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadProfile = async (currentUser: User) => {
    try {
      // Retry loop — the DB trigger may take a moment to create the profile row
      let profileData: UserProfile | null = null
      let attempts = 0
      const maxAttempts = 5

      while (!profileData && attempts < maxAttempts) {
        const { data, error } = await supabase
          .from('users')
          .select('*')
          .eq('id', currentUser.id)
          .maybeSingle()

        if (error) {
          console.error('Error fetching profile:', error)
          break
        }

        if (data) {
          profileData = data as UserProfile
        } else {
          // Profile not yet created by trigger — wait and retry
          await new Promise(resolve => setTimeout(resolve, 1000))
          attempts++
        }
      }

      // If still no profile after retries, create one as fallback
      if (!profileData) {
        console.warn('Profile missing after retries, creating fallback...')
        const metadata = currentUser.user_metadata || {}
        const role = (metadata.role as UserRole) || 'victim'

        const insertData: UserProfileInsert = {
          id: currentUser.id,
          email: currentUser.email!,
          role: role,
          full_name: (metadata.full_name as string) || null,
          updated_at: new Date().toISOString(),
        }

        // Cast needed: Supabase SDK resolves Insert type to 'never' due to generic chain issue
        const { error: insertError } = await (supabase.from('users') as any)
          .upsert(insertData)

        if (insertError) {
          console.error('Failed to auto-create profile:', insertError)
        } else {
          const { data: retryData } = await supabase
            .from('users')
            .select('*')
            .eq('id', currentUser.id)
            .maybeSingle()
          profileData = retryData as UserProfile | null
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
      router.refresh()
    }
    return { error }
  }

  const signUp = async (email: string, password: string, fullName?: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
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