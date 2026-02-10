'use server';

import { createClient } from '@/lib/supabase/server';

/**
 * Check if the current user's profile is complete.
 * Used by client components to determine redirect target.
 */
export async function checkProfileStatus() {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) return null;

    const { data: profile } = await supabase
        .from('users')
        .select('is_profile_completed, role')
        .eq('id', user.id)
        .single();

    return profile as { is_profile_completed: boolean; role: string } | null;
}
