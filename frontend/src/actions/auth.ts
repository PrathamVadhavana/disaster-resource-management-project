'use server';

import { cookies } from 'next/headers';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Check if the current user's profile is complete.
 * Used by client components to determine redirect target.
 *
 * Reads the Supabase token from cookies and calls the backend API.
 */
export async function checkProfileStatus() {
    const cookieStore = await cookies();
    const token = cookieStore.get('sb-token')?.value;

    if (!token) return null;

    try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
            cache: 'no-store',
        });

        if (!res.ok) return null;

        const profile = await res.json();
        return profile as { is_profile_completed: boolean; role: string } | null;
    } catch {
        return null;
    }
}
