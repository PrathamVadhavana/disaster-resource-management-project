'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/auth-provider';
import { Loader2, AlertTriangle, Heart, HandHeart, Building2 } from 'lucide-react';
import { VictimForm } from '@/components/auth/onboarding/VictimForm';
import { NGOForm } from '@/components/auth/onboarding/NGOForm';
import { DonorForm } from '@/components/auth/onboarding/DonorForm';
import { VolunteerForm } from '@/components/auth/onboarding/VolunteerForm';

/** Map a role to its dashboard path */
function roleToDashboard(role: string): string {
    switch (role) {
        case 'victim': return '/victim';
        case 'ngo': return '/ngo';
        case 'donor': return '/donor';
        case 'volunteer': return '/volunteer';
        default: return '/victim';
    }
}

const ROLE_OPTIONS = [
    { value: 'victim', label: 'Victim', desc: 'I need help', icon: AlertTriangle, color: 'red' },
    { value: 'volunteer', label: 'Volunteer', desc: 'I want to help', icon: HandHeart, color: 'purple' },
    { value: 'ngo', label: 'NGO / Organization', desc: 'Managing relief ops', icon: Building2, color: 'blue' },
    { value: 'donor', label: 'Donor', desc: 'Providing resources', icon: Heart, color: 'emerald' },
] as const;

const COLOR_CLASSES: Record<string, string> = {
    red: 'border-red-500 bg-red-50/50 dark:bg-red-900/10 ring-1 ring-red-500',
    purple: 'border-purple-500 bg-purple-50/50 dark:bg-purple-900/10 ring-1 ring-purple-500',
    blue: 'border-blue-500 bg-blue-50/50 dark:bg-blue-900/10 ring-1 ring-blue-500',
    emerald: 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-900/10 ring-1 ring-emerald-500',
};

const ICON_COLORS: Record<string, string> = {
    red: 'from-red-500 to-orange-600',
    purple: 'from-purple-500 to-indigo-600',
    blue: 'from-blue-500 to-cyan-600',
    emerald: 'from-emerald-500 to-teal-600',
};

export default function OnboardingPage() {
    const { user: authUser, profile, loading: authLoading } = useAuth();
    const [ready, setReady] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [selectedRole, setSelectedRole] = useState<string | null>(null);
    const router = useRouter();
    const supabase = createClient();

    // Get role from user_metadata (set during signup) or profile
    const metaRole = (authUser?.user_metadata?.role as string) || (profile?.role as string) || null;

    useEffect(() => {
        if (!authLoading) {
            if (!authUser) {
                router.push('/login');
                return;
            }
            if (profile?.is_profile_completed) {
                const r = (profile.role as string) || (authUser?.user_metadata?.role as string) || 'victim';
                router.push(roleToDashboard(r));
                return;
            }
            // If role was already selected during signup, skip the role picker
            if (metaRole && metaRole !== 'admin') {
                setSelectedRole(metaRole);
            }
            setReady(true);
            return;
        }

        const timer = setTimeout(() => setReady(true), 3000);
        return () => clearTimeout(timer);
    }, [authLoading, authUser, profile, metaRole, router]);

    const handleRoleSelected = async (role: string) => {
        setSelectedRole(role);
        // Also update metadata so role persists
        await supabase.auth.updateUser({ data: { role } });
    };

    // Loading
    if (!ready && !authUser) return (
        <div className="h-screen flex flex-col items-center justify-center gap-4 bg-slate-50 dark:bg-slate-950">
            <Loader2 className="animate-spin w-8 h-8 text-blue-600" />
            <p className="text-slate-500 text-sm">Setting up your profile...</p>
        </div>
    );

    if (!authUser) return (
        <div className="h-screen flex flex-col items-center justify-center gap-4 bg-slate-50 dark:bg-slate-950">
            <p className="text-red-500">Not authenticated. Redirecting...</p>
        </div>
    );

    if (submitting) return (
        <div className="h-screen flex flex-col items-center justify-center gap-4 bg-slate-50 dark:bg-slate-950">
            <Loader2 className="animate-spin w-8 h-8 text-blue-600" />
            <p className="text-slate-500 text-sm">Saving your profile...</p>
        </div>
    );

    // Step 1: Role picker — always shown first so user can choose/confirm their role
    if (!selectedRole) return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-12 px-4">
            <div className="max-w-2xl mx-auto space-y-8">
                <div className="text-center">
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Welcome to HopeInChaos</h1>
                    <p className="text-slate-500 mt-2">How would you like to participate?</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {ROLE_OPTIONS.map((opt) => {
                        const Icon = opt.icon;
                        return (
                            <button
                                key={opt.value}
                                onClick={() => handleRoleSelected(opt.value)}
                                className="group rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 text-left hover:shadow-lg transition-all hover:border-slate-300 dark:hover:border-slate-700"
                            >
                                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${ICON_COLORS[opt.color]} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                                    <Icon className="w-6 h-6 text-white" />
                                </div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white">{opt.label}</h3>
                                <p className="text-sm text-slate-500 mt-1">{opt.desc}</p>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );

    // Step 2: Role-specific form
    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-12 px-4">
            <div className="max-w-3xl mx-auto space-y-8">
                <div className="text-center">
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Complete Your Profile</h1>
                    <p className="text-slate-500">Please provide a few more details to help us coordinate effectively.</p>
                    <button
                        onClick={() => setSelectedRole(null)}
                        className="mt-2 text-sm text-blue-500 hover:text-blue-600 underline"
                    >
                        Change role
                    </button>
                </div>

                {selectedRole === 'victim' && <VictimForm userId={authUser.id} />}
                {selectedRole === 'ngo' && <NGOForm userId={authUser.id} />}
                {selectedRole === 'donor' && <DonorForm userId={authUser.id} />}
                {selectedRole === 'volunteer' && <VolunteerForm userId={authUser.id} />}
            </div>
        </div>
    );
}
