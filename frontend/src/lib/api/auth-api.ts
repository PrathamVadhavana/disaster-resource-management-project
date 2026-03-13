import { getSupabaseClient } from '@/lib/supabase/client'
import { db } from '@/lib/db'

// Define types directly
export interface UserProfile {
  id: string
  created_at: string
  updated_at: string
  email: string
  role: 'admin' | 'ngo' | 'victim' | 'donor' | 'volunteer'
  full_name: string | null
  phone: string | null
  organization: string | null
  metadata: any | null
  is_profile_completed: boolean
}

export interface AuthResponse {
  user: any | null
  profile: UserProfile | null
  session: any | null
  error: any | null
}

const _unused = null // DB queries now route through backend API

export const authApi = {
  // Get current session and profile
  async getCurrentSession(): Promise<AuthResponse> {
    try {
      const sb = getSupabaseClient()
      const { data: { session } } = await sb.auth.getSession()

      if (!session?.user) {
        return {
          user: null,
          profile: null,
          session: null,
          error: null
        }
      }

      const profile = await this.loadProfile(session.user)

      return {
        user: session.user,
        profile,
        session: { access_token: session.access_token },
        error: null
      }
    } catch (err: any) {
      return {
        user: null,
        profile: null,
        session: null,
        error: err
      }
    }
  },

  // Load user profile with retry logic
  async loadProfile(currentUser: any): Promise<UserProfile | null> {
    try {
      let profileData: UserProfile | null = null
      let attempts = 0
      const maxAttempts = 5

      while (!profileData && attempts < maxAttempts) {
        try {
          const data = await db.getProfile()
          if (data) {
            profileData = data as UserProfile
          }
        } catch {
          // Profile not yet created — wait and retry
        }

        if (!profileData) {
          await new Promise(resolve => setTimeout(resolve, 1000))
          attempts++
        }
      }

      // If still no profile after retries, create one as fallback
      if (!profileData) {
        console.warn('Profile missing after retries, creating fallback...')
        const appMeta = currentUser.app_metadata || {}
        const userMeta = currentUser.user_metadata || {}
        const role = (appMeta.role || userMeta.role || 'victim') as 'admin' | 'ngo' | 'victim' | 'donor' | 'volunteer'

        const insertData = {
          id: currentUser.id,
          email: currentUser.email!,
          role: role,
          full_name: userMeta.full_name || null,
          updated_at: new Date().toISOString(),
          is_profile_completed: false
        }

        try {
          await db.upsertProfile(insertData)
          profileData = await db.getProfile() as UserProfile | null
        } catch (err) {
          console.error('Failed to auto-create profile:', err)
        }
      }

      return profileData
    } catch (error) {
      console.error('Error loading profile:', error)
      return null
    }
  },

  // Sign in via Supabase
  async signIn(email: string, password: string): Promise<{ error: any | null; shouldRedirectToOnboarding: boolean }> {
    try {
      const sb = getSupabaseClient()
      const { data, error } = await sb.auth.signInWithPassword({ email, password })
      if (error) throw error

      if (data.user) {
        try {
          const profile = await db.getProfile() as { is_profile_completed: boolean } | null
          const shouldRedirectToOnboarding = !profile?.is_profile_completed
          return { error: null, shouldRedirectToOnboarding }
        } catch {
          return { error: null, shouldRedirectToOnboarding: true }
        }
      }

      return { error: null, shouldRedirectToOnboarding: false }
    } catch (err: any) {
      return { error: err, shouldRedirectToOnboarding: false }
    }
  },

  // Sign up via Supabase
  async signUp(email: string, password: string, fullName?: string): Promise<{ error: any | null }> {
    try {
      const sb = getSupabaseClient()
      const { error } = await sb.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : undefined,
          data: { full_name: fullName || '' },
        },
      })
      if (error) throw error
      return { error: null }
    } catch (err: any) {
      return { error: err }
    }
  },

  // Sign out
  async signOut(): Promise<void> {
    try {
      const sb = getSupabaseClient()
      await sb.auth.signOut()
      // Clear cookies
      document.cookie = 'sb-token=; path=/; max-age=0'
      document.cookie = 'sb-role=; path=/; max-age=0'
    } catch (err) {
      console.error('Error signing out:', err)
    }
  },

  // Update profile via backend API
  async updateProfile(userId: string, updates: Partial<UserProfile>): Promise<void> {
    try {
      await db.updateProfile(updates)
    } catch (err) {
      console.error('Error updating profile:', err)
      throw err
    }
  },

  // Listen for auth changes — Supabase version
  onAuthStateChange(callback: (event: string, session: any | null) => void) {
    const sb = getSupabaseClient()
    const { data: { subscription } } = sb.auth.onAuthStateChange((event, session) => {
      if (session) {
        callback('SIGNED_IN', { access_token: session.access_token, user: session.user })
      } else {
        callback('SIGNED_OUT', null)
      }
    })
    return { data: { subscription: { unsubscribe: () => subscription.unsubscribe() } } }
  }
}