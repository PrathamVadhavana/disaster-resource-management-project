import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
    let response = NextResponse.next({
        request: {
            headers: request.headers,
        },
    })

    // The correct pattern for @supabase/ssr middleware in Next.js 14/15
    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value))
                    response = NextResponse.next({
                        request,
                    })
                    cookiesToSet.forEach(({ name, value, options }) =>
                        response.cookies.set(name, value, options)
                    )
                },
            },
        }
    )

    // Validate the session
    const { data: { user } } = await supabase.auth.getUser()
    const path = request.nextUrl.pathname

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
        if (user && (path.startsWith('/login') || path.startsWith('/signup'))) {
            const role = user.user_metadata?.role
            // If they have a role, send to their dashboard; otherwise send to onboarding
            if (role) {
                return NextResponse.redirect(new URL(dashboardFor(role), request.url))
            }
            return NextResponse.redirect(new URL('/onboarding', request.url))
        }
        return response
    }

    // 1. Authenticated Check
    if (!user) {
        return NextResponse.redirect(new URL('/login', request.url))
    }

    // 2. Role Check & Routing
    const role = user.user_metadata?.role

    // If user has no role, force them to onboarding (unless they are already there)
    if (!role && path !== '/onboarding') {
        return NextResponse.redirect(new URL('/onboarding', request.url))
    }

    // Allow /onboarding — the page itself checks is_profile_completed via AuthProvider
    // and redirects completed users to their dashboard. We cannot check DB from edge middleware.
    if (path === '/onboarding') {
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
    // Match all request paths except for the ones starting with:
    // - _next/static (static files)
    // - _next/image (image optimization files)
    // - favicon.ico (favicon file)
    matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
