import { NextResponse, type NextRequest } from 'next/server'

/**
 * Edge-compatible middleware using auth token cookies.
 *
 * The AuthProvider sets two cookies on every auth state change:
 *   - sb-token  (the Supabase access token)
 *   - sb-role   (the user role extracted client-side)
 *
 * We intentionally do NOT verify the JWT here (Edge runtime has limited
 * crypto support). The token is verified by the FastAPI backend on every
 * API call. The middleware only decides whether to allow/redirect based
 * on cookie presence + role claim.
 */

export async function middleware(request: NextRequest) {
    let response = NextResponse.next({
        request: {
            headers: request.headers,
        },
    })

    const token = request.cookies.get('sb-token')?.value
    const role  = request.cookies.get('sb-role')?.value
    const profileCompleted = request.cookies.get('profile-completed')?.value
    const path  = request.nextUrl.pathname

    // Helper: get the correct dashboard path for a role
    function dashboardFor(r?: string): string {
        switch (r) {
            case 'victim': return '/victim'
            case 'ngo': return '/ngo'
            case 'donor': return '/donor'
            case 'volunteer': return '/volunteer'
            case 'admin': return '/admin'
            default: return '/onboarding'
        }
    }

    // Public Routes - Allow access
    if (
        path === '/' ||
        path.startsWith('/auth') ||
        path.startsWith('/login') ||
        path.startsWith('/signup') ||
        path.startsWith('/_next') ||
        path.startsWith('/api') ||
        path.includes('.')
    ) {
        // Redirect authenticated users away from auth pages
        if (token && (path.startsWith('/login') || path.startsWith('/signup'))) {
            if (role) {
                return NextResponse.redirect(new URL(dashboardFor(role), request.url))
            }
            return NextResponse.redirect(new URL('/onboarding', request.url))
        }
        return response
    }

    // 1. Authenticated Check — no token means not logged in
    if (!token) {
        return NextResponse.redirect(new URL('/login', request.url))
    }

    // 2. Role Check & Routing
    // If user has no role, force them to onboarding (unless they are already there)
    if (!role && path !== '/onboarding') {
        return NextResponse.redirect(new URL('/onboarding', request.url))
    }

    // Allow /onboarding — the page itself checks is_profile_completed via AuthProvider
    // But if user already completed their profile, redirect them to their dashboard
    if (path === '/onboarding') {
        if (role && profileCompleted === 'true') {
            return NextResponse.redirect(new URL(dashboardFor(role), request.url))
        }
        return response
    }

    // 3. Role-based route protection
    // Admin routes
    if (path.startsWith('/admin') && role !== 'admin') {
        return NextResponse.redirect(new URL(dashboardFor(role), request.url))
    }

    // Victim routes — only victims
    if (path.startsWith('/victim') && role !== 'victim') {
        return NextResponse.redirect(new URL(dashboardFor(role), request.url))
    }

    // NGO routes — only NGOs
    if (path.startsWith('/ngo') && role !== 'ngo') {
        return NextResponse.redirect(new URL(dashboardFor(role), request.url))
    }

    // Donor routes — only donors
    if (path.startsWith('/donor') && role !== 'donor') {
        return NextResponse.redirect(new URL(dashboardFor(role), request.url))
    }

    // Volunteer routes — only volunteers
    if (path.startsWith('/volunteer') && role !== 'volunteer') {
        return NextResponse.redirect(new URL(dashboardFor(role), request.url))
    }

    // Legacy /dashboard — redirect to role-specific dashboard
    if (path.startsWith('/dashboard')) {
        const target = dashboardFor(role)
        if (target !== '/onboarding' && !path.startsWith(target)) {
            return NextResponse.redirect(new URL(target, request.url))
        }
    }

    return response
}

export const config = {
    matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
