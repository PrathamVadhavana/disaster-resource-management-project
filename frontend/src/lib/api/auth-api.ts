import { createClient } from '@/lib/supabase/client'

// Define types directly to avoid Supabase type issues
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

const supabase = createClient()

export const authApi = {
  // Get current session and profile
  async getCurrentSession(): Promise<AuthResponse> {
    try {
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()
      
      if (sessionError) {
        throw sessionError
      }

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
        session,
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
        const role = (metadata.role as 'admin' | 'ngo' | 'victim' | 'donor' | 'volunteer') || 'victim'

        const insertData = {
          id: currentUser.id,
          email: currentUser.email!,
          role: role,
          full_name: (metadata.full_name as string) || null,
          updated_at: new Date().toISOString(),
          is_profile_completed: false
        }

        // Use raw SQL to avoid type issues
        const { error: insertError } = await (supabase.from('users') as any).insert([insertData])

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

      return profileData
    } catch (error) {
      console.error('Error loading profile:', error)
      return null
    }
  },

  // Sign in with profile completion check
  async signIn(email: string, password: string): Promise<{ error: any | null; shouldRedirectToOnboarding: boolean }> {
    try {
      const { data: authData, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (error) {
        return { error, shouldRedirectToOnboarding: false }
      }

      if (authData.user) {
        // Check profile completion to decide redirect target
        const { data: profileRow } = await supabase
          .from('users')
          .select('is_profile_completed')
          .eq('id', authData.user.id)
          .maybeSingle()

        const profileResult = profileRow as { is_profile_completed: boolean } | null
        const shouldRedirectToOnboarding = !profileResult?.is_profile_completed
        
        return { error: null, shouldRedirectToOnboarding }
      }

      return { error: null, shouldRedirectToOnboarding: false }
    } catch (err: any) {
      return { error: err, shouldRedirectToOnboarding: false }
    }
  },

  // Sign up
  async signUp(email: string, password: string, fullName?: string): Promise<{ error: any | null }> {
    try {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName,
          },
        },
      })

      return { error }
    } catch (err: any) {
      return { error: err }
    }
  },

  // Sign out
  async signOut(): Promise<void> {
    try {
      await supabase.auth.signOut()
    } catch (err) {
      console.error('Error signing out:', err)
    }
  },

  // Update profile
  async updateProfile(userId: string, updates: Partial<UserProfile>): Promise<void> {
    try {
      const { error } = await (supabase.from('users') as any).update(updates).eq('id', userId)

      if (error) {
        throw error
      }
    } catch (err) {
      console.error('Error updating profile:', err)
      throw err
    }
  },

  // Listen for auth changes
  onAuthStateChange(callback: (event: string, session: any | null) => void) {
    return supabase.auth.onAuthStateChange(callback)
  }
}