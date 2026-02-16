'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { victimDetailsSchema } from '@/types/auth';
import type { z } from 'zod';
import { createClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';

type VictimFormData = z.infer<typeof victimDetailsSchema>;

export function VictimForm({ userId }: { userId: string }) {
    const router = useRouter();
    const supabase = createClient();
    const [loading, setLoading] = useState(false);

    const form = useForm<VictimFormData>({
        resolver: zodResolver(victimDetailsSchema),
        defaultValues: {
            current_status: 'needs_help',
            needs: [],
            medical_needs: '',
        }
    });

    const onSubmit = async (data: VictimFormData) => {
        setLoading(true);
        try {
            // 1. Insert details (Cast to any to bypass missing type defs)
            const { error } = await (supabase.from('victim_details') as any).insert({
                id: userId,
                current_status: data.current_status,
                needs: data.needs, // Ensure this matches DB array type
                medical_needs: data.medical_needs || null
            });

            if (error) throw error;

            // 2. Mark profile as completed
            await (supabase.from('users') as any).update({ is_profile_completed: true }).eq('id', userId);

            router.push('/victim');
            router.refresh();
        } catch (error) {
            console.error(error);
            alert('Failed to save details');
        } finally {
            setLoading(false);
        }
    };

    return (
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-lg mx-auto bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg">
            <h2 className="text-xl font-bold dark:text-white">Current Situation</h2>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Status</label>
                <select {...form.register('current_status')} className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700">
                    <option value="safe">I am Safe</option>
                    <option value="needs_help">I Need Help</option>
                    <option value="critical">Critical / Emergency</option>
                    <option value="evacuated">Evacuated</option>
                </select>
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Immediate Needs (Select all that apply)</label>
                <div className="grid grid-cols-2 gap-2">
                    {['Food', 'Water', 'Medical Aid', 'Shelter', 'Evacuation'].map(need => (
                        <label key={need} className="flex items-center space-x-2 border p-2 rounded dark:border-slate-700">
                            <input
                                type="checkbox"
                                value={need.toLowerCase()}
                                {...form.register('needs')}
                            />
                            <span className="text-sm">{need}</span>
                        </label>
                    ))}
                </div>
                {form.formState.errors.needs && <p className="text-red-500 text-xs">{form.formState.errors.needs.message}</p>}
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Medical Requirements (Optional)</label>
                <textarea
                    {...form.register('medical_needs')}
                    className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                    placeholder="Diabetic insulin, Epipen, Mobility issues..."
                />
            </div>

            <button disabled={loading} className="w-full bg-blue-600 text-white py-2 rounded-lg font-bold flex justify-center items-center gap-2">
                {loading && <Loader2 className="animate-spin w-4 h-4" />}
                Complete Profile
            </button>
        </form>
    );
}
