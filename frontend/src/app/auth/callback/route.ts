import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
    const { searchParams, origin, hash } = new URL(request.url)
    const code = searchParams.get('code')
    const next = searchParams.get('next') ?? null

    // Handle error responses from Supabase OAuth
    // Supabase sends errors as query params: ?error=...&error_code=...&error_description=...
    const error = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')
    const errorCode = searchParams.get('error_code')

    if (error) {
        // Redirect to error page with error details
        const errorParams = new URLSearchParams()
        errorParams.set('error', error)
        if (errorDescription) errorParams.set('error_description', errorDescription)
        if (errorCode) errorParams.set('error_code', errorCode)
        return NextResponse.redirect(`${origin}/auth/auth-code-error?${errorParams.toString()}`)
    }

    if (code) {
        const supabase = await createClient()
        const { data: sessionData, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)

        if (!exchangeError && sessionData.user) {
            // If an explicit redirect was provided, use it
            if (next) {
                return NextResponse.redirect(`${origin}${next}`)
            }

            // Otherwise, check profile completion to decide redirect target
            let redirectPath = '/onboarding'

            // Retry loop — the DB trigger may take a moment to create the profile row
            let attempts = 0
            const maxAttempts = 5
            while (attempts < maxAttempts) {
                const { data: profile } = await supabase
                    .from('users')
                    .select('is_profile_completed')
                    .eq('id', sessionData.user.id)
                    .maybeSingle()

                const profileRow = profile as { is_profile_completed: boolean } | null

                if (profileRow) {
                    redirectPath = profileRow.is_profile_completed ? '/dashboard' : '/onboarding'
                    break
                }

                // Profile not yet created by trigger — wait and retry
                await new Promise(resolve => setTimeout(resolve, 1000))
                attempts++
            }

            return NextResponse.redirect(`${origin}${redirectPath}`)
        }

        // Exchange failed — redirect to error page
        if (exchangeError) {
            const errorParams = new URLSearchParams()
            errorParams.set('error', 'exchange_error')
            errorParams.set('error_description', exchangeError.message)
            return NextResponse.redirect(`${origin}/auth/auth-code-error?${errorParams.toString()}`)
        }
    }

    // No code and no error — redirect to login
    return NextResponse.redirect(`${origin}/login`)
}
