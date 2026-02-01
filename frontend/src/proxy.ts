import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function proxy(request: NextRequest) {
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
        // Optional: Redirect authenticated users away from auth pages
        if (user && (path.startsWith('/login') || path.startsWith('/signup'))) {
            return NextResponse.redirect(new URL('/dashboard', request.url))
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

    // If user has a role but tries to go to onboarding, redirect to dashboard
    if (role && path === '/onboarding') {
        return NextResponse.redirect(new URL('/dashboard', request.url))
    }

    // 3. Admin Route Protection
    if (path.startsWith('/admin') && role !== 'admin') {
        return NextResponse.redirect(new URL('/dashboard', request.url))
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
