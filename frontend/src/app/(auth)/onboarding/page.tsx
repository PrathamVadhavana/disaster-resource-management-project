'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';
import { UserRole } from '@/types/supabase';
import { Loader2 } from 'lucide-react';
import { VictimForm } from '@/components/auth/onboarding/VictimForm';
import { NGOForm } from '@/components/auth/onboarding/NGOForm';

// Placeholder for other forms
const PlaceholderForm = ({ role, userId, onComplete }: any) => (
    <div className="text-center p-8 bg-white dark:bg-slate-900 rounded-xl">
        <h2 className="text-xl font-bold mb-4">You are joining as {role}</h2>
        <p className="mb-4">Standard profile creation...</p>
        <button
            onClick={onComplete}
            className="bg-blue-600 text-white px-4 py-2 rounded"
        >
            Complete Setup
        </button>
    </div>
);

export default function OnboardingPage() {
    const [user, setUser] = useState<any>(null);
    const [role, setRole] = useState<UserRole | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        let mounted = true;
        const init = async () => {
            try {
                const { data: { user }, error: authError } = await supabase.auth.getUser();
                if (authError || !user) {
                    if (mounted) router.push('/login');
                    return;
                }

                // Retry loop for profile fetch
                let profile: any = null;
                let attempts = 0;
                while (!profile && attempts < 5) {
                    const { data, error } = await supabase
                        .from('users')
                        .select('role, is_profile_completed')
                        .eq('id', user.id)
                        .single();

                    if (!error && data) {
                        profile = data;
                    } else {
                        await new Promise(r => setTimeout(r, 1000));
                        attempts++;
                    }
                }

                if (!mounted) return;

                if (profile?.is_profile_completed) {
                    // Double check if we are already safely redirected? 
                    // No, router.push is better.
                    router.push('/dashboard');
                    return;
                }

                setUser(user);
                // Default to victim if missing (e.g. fresh Google Auth user who hasn't been processed by trigger yet)
                setRole((profile?.role as UserRole) || 'victim');
            } catch (err) {
                console.error("Onboarding init error:", err);
            } finally {
                if (mounted) setLoading(false);
            }
        };
        init();
        return () => { mounted = false; };
    }, [router, supabase]);

    const handleSimpleComplete = async () => {
        if (!user) return;
        setLoading(true);
        // Cast needed: Supabase SDK resolves Update type to 'never' due to generic chain issue
        await (supabase.from('users') as any).update({ is_profile_completed: true }).eq('id', user.id);
        router.push('/dashboard');
    };

    if (loading) return (
        <div className="h-screen flex flex-col items-center justify-center gap-4">
            <Loader2 className="animate-spin w-8 h-8 text-blue-600" />
            <p className="text-slate-500 text-sm">Setting up your profile...</p>
        </div>
    );

    if (!role) return (
        <div className="h-screen flex flex-col items-center justify-center gap-4">
            <p className="text-red-500">Error: Unable to load profile.</p>
            <button
                onClick={() => supabase.auth.signOut().then(() => router.push('/login'))}
                className="text-sm underline text-slate-500 hover:text-slate-700"
            >
                Sign Out & Retry
            </button>
        </div>
    );

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-12 px-4">
            <div className="max-w-3xl mx-auto space-y-8">
                <div className="text-center">
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Complete Your Profile</h1>
                    <p className="text-slate-500">Please provide a few more details to help us coordinate effectively.</p>
                </div>

                {role === 'victim' && <VictimForm userId={user.id} />}
                {role === 'ngo' && <NGOForm userId={user.id} />}

                {/* Fallback for Donor/Volunteer until specific forms are built */}
                {['donor', 'volunteer', 'admin'].includes(role) && (
                    <PlaceholderForm role={role} userId={user.id} onComplete={handleSimpleComplete} />
                )}
            </div>
        </div>
    );
}
