'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { donorDetailsSchema } from '@/types/auth';
import type { z } from 'zod';
import { db } from '@/lib/db';
import { getSupabaseClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Loader2, Heart } from 'lucide-react';

type DonorFormData = z.infer<typeof donorDetailsSchema>;

const DONOR_TYPES = [
    { value: 'individual', label: 'Individual', desc: 'Personal donation' },
    { value: 'corporate', label: 'Corporate', desc: 'Company/Business' },
    { value: 'foundation', label: 'Foundation', desc: 'Non-profit org' },
    { value: 'government', label: 'Government', desc: 'Gov agency' },
] as const;

const CAUSES = [
    'Food & Nutrition', 'Water & Sanitation', 'Medical Aid',
    'Shelter & Housing', 'Education', 'Emergency Relief',
    'Rebuilding', 'Mental Health',
];

export function DonorForm({ userId }: { userId: string }) {
    const router = useRouter();
    const [loading, setLoading] = useState(false);

    const form = useForm<DonorFormData>({
        resolver: zodResolver(donorDetailsSchema),
        defaultValues: {
            donor_type: 'individual',
            preferred_causes: [],
            tax_id: '',
        },
    });

    const onSubmit = async (data: DonorFormData) => {
        setLoading(true);
        try {
            const sb = getSupabaseClient();
            const { data: { session } } = await sb.auth.getSession();
            await db.upsertProfile({ id: userId, email: session?.user?.email ?? '', role: 'donor' });

            // Save donor details — non-blocking so a constraint/network failure
            // does not trap the user in an infinite onboarding loop.
            try {
                await db.upsertDetails('donor_details', {
                    id: userId,
                    donor_type: data.donor_type,
                    preferred_causes: data.preferred_causes,
                    tax_id: data.tax_id || null,
                });
            } catch (detailsErr: any) {
                console.error('donor_details save failed (non-fatal):', detailsErr);
            }

            // Always mark profile as completed regardless of details outcome
            await db.updateProfile({ is_profile_completed: true });

            if (session) {
                document.cookie = `sb-token=${session.access_token}; path=/; max-age=3600; SameSite=Lax`;
                document.cookie = `sb-role=donor; path=/; max-age=3600; SameSite=Lax`;
            }
            document.cookie = `profile-completed=true; path=/; max-age=86400; SameSite=Lax`;
            window.location.href = '/donor';
        } catch (error: any) {
            console.error('Donor onboarding error:', error);
            alert('Failed to complete onboarding: ' + (error?.message || 'Unknown error'));
            setLoading(false);
        }
    };

    return (
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-lg mx-auto bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg">
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
                    <Heart className="w-5 h-5 text-white" />
                </div>
                <h2 className="text-xl font-bold dark:text-white">Donor Profile</h2>
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Donor Type</label>
                <div className="grid grid-cols-2 gap-2">
                    {DONOR_TYPES.map(dt => (
                        <label
                            key={dt.value}
                            className={`cursor-pointer rounded-xl border p-3 flex flex-col gap-0.5 transition-all hover:bg-slate-50 dark:hover:bg-slate-800 ${form.watch('donor_type') === dt.value
                                    ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-900/10 ring-1 ring-emerald-500'
                                    : 'border-slate-200 dark:border-slate-700'
                                }`}
                        >
                            <input type="radio" value={dt.value} {...form.register('donor_type')} className="sr-only" />
                            <span className="text-sm font-bold dark:text-white">{dt.label}</span>
                            <span className="text-xs text-slate-500">{dt.desc}</span>
                        </label>
                    ))}
                </div>
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Preferred Causes (Select all that apply)</label>
                <div className="grid grid-cols-2 gap-2">
                    {CAUSES.map(cause => (
                        <label key={cause} className="flex items-center space-x-2 border p-2 rounded dark:border-slate-700">
                            <input
                                type="checkbox"
                                value={cause.toLowerCase()}
                                {...form.register('preferred_causes')}
                            />
                            <span className="text-sm dark:text-slate-300">{cause}</span>
                        </label>
                    ))}
                </div>
                {form.formState.errors.preferred_causes && (
                    <p className="text-red-500 text-xs">{form.formState.errors.preferred_causes.message}</p>
                )}
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Tax ID / PAN (Optional)</label>
                <input
                    {...form.register('tax_id')}
                    className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                    placeholder="For tax-deductible receipts"
                />
            </div>

            <button disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 rounded-lg font-bold flex justify-center items-center gap-2 transition-colors">
                {loading && <Loader2 className="animate-spin w-4 h-4" />}
                Complete Donor Profile
            </button>
        </form>
    );
}
