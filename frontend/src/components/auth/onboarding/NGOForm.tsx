'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ngoDetailsSchema } from '@/types/auth'; // Ensure this matches schema export
import type { z } from 'zod';
import { createClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Loader2 } from 'lucide-react';

type NGOFormData = z.infer<typeof ngoDetailsSchema>;

export function NGOForm({ userId }: { userId: string }) {
    const router = useRouter();
    const supabase = createClient();
    const [loading, setLoading] = useState(false);

    const form = useForm<NGOFormData>({
        resolver: zodResolver(ngoDetailsSchema),
        defaultValues: {
            organization_name: '',
            registration_number: '',
            operating_sectors: [],
            website: '',
        }
    });

    const onSubmit = async (data: NGOFormData) => {
        setLoading(true);
        try {
            // 0. Ensure users row exists (FK parent for ngo_details)
            const { error: upsertErr } = await (supabase.from('users') as any)
                .upsert({ id: userId, email: (await supabase.auth.getUser()).data.user?.email ?? '', role: 'ngo' }, { onConflict: 'id' });
            if (upsertErr) console.warn('users upsert warning:', upsertErr.message);

            // 1. Insert NGO details
            const { error } = await (supabase.from('ngo_details') as any).upsert({
                id: userId,
                organization_name: data.organization_name,
                registration_number: data.registration_number,
                operating_sectors: data.operating_sectors,
                website: data.website || null,
                verification_status: 'pending'
            }, { onConflict: 'id' });

            if (error) {
                console.error('ngo_details insert error:', error);
                throw error;
            }

            await (supabase.from('users') as any).update({ is_profile_completed: true }).eq('id', userId);

            // Set role in user_metadata so middleware routes correctly
            await supabase.auth.updateUser({ data: { role: 'ngo' } });

            // Refresh the session so the JWT cookie contains the new role
            await supabase.auth.refreshSession();

            // Hard redirect — ensures middleware reads the fresh JWT cookie
            window.location.href = '/dashboard';
        } catch (error: any) {
            console.error('NGO onboarding submit error:', error);
            alert('Failed to save details: ' + (error?.message || 'Unknown error'));
            setLoading(false);
        }
    };

    return (
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-lg mx-auto bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg">
            <h2 className="text-xl font-bold dark:text-white">Organization Details</h2>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Organization Name</label>
                <input
                    {...form.register('organization_name')}
                    className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                />
                {form.formState.errors.organization_name && <p className="text-red-500 text-xs">{form.formState.errors.organization_name.message}</p>}
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Registration Number</label>
                <input
                    {...form.register('registration_number')}
                    className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                />
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Website (Optional)</label>
                <input
                    {...form.register('website')}
                    className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                    placeholder="https://"
                />
                {form.formState.errors.website && <p className="text-red-500 text-xs">{form.formState.errors.website.message}</p>}
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Operating Sectors</label>
                <div className="grid grid-cols-2 gap-2">
                    {['Medical', 'Search & Rescue', 'Food/Water', 'Shelter', 'Logistics'].map(sector => (
                        <label key={sector} className="flex items-center space-x-2 border p-2 rounded dark:border-slate-700">
                            <input
                                type="checkbox"
                                value={sector.toLowerCase()}
                                {...form.register('operating_sectors')}
                            />
                            <span className="text-sm">{sector}</span>
                        </label>
                    ))}
                </div>
            </div>

            <button disabled={loading} className="w-full bg-blue-600 text-white py-2 rounded-lg font-bold flex justify-center items-center gap-2">
                {loading && <Loader2 className="animate-spin w-4 h-4" />}
                Register Organization
            </button>
        </form>
    );
}
