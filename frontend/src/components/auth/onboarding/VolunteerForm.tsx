'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { volunteerDetailsSchema } from '@/types/auth';
import type { z } from 'zod';
import { createClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Loader2, HandHeart } from 'lucide-react';

type VolunteerFormData = z.infer<typeof volunteerDetailsSchema>;

const SKILLS = [
    'First Aid', 'Search & Rescue', 'Medical/Nursing', 'Counseling',
    'Logistics', 'Driving', 'Communication', 'Tech/IT',
    'Language Translation', 'Construction', 'Cooking', 'Child Care',
];

const CERTIFICATIONS = [
    'CPR/BLS', 'Advanced First Aid', 'HAM Radio',
    'CERT (Community Emergency Response)', 'Wilderness First Responder',
    'Heavy Equipment Operation', 'Hazmat Awareness',
];

export function VolunteerForm({ userId }: { userId: string }) {
    const router = useRouter();
    const supabase = createClient();
    const [loading, setLoading] = useState(false);

    const form = useForm<VolunteerFormData>({
        resolver: zodResolver(volunteerDetailsSchema),
        defaultValues: {
            skills: [],
            availability_status: 'available',
            certifications: [],
        },
    });

    const onSubmit = async (data: VolunteerFormData) => {
        setLoading(true);
        try {
            const { error: upsertErr } = await (supabase.from('users') as any)
                .upsert({ id: userId, email: (await supabase.auth.getUser()).data.user?.email ?? '', role: 'volunteer' }, { onConflict: 'id' });
            if (upsertErr) console.warn('users upsert warning:', upsertErr.message);

            const { error } = await (supabase.from('volunteer_details') as any).upsert({
                id: userId,
                skills: data.skills,
                availability_status: data.availability_status,
                certifications: data.certifications || [],
            }, { onConflict: 'id' });

            if (error) {
                console.error('volunteer_details insert error:', error);
                throw error;
            }

            await (supabase.from('users') as any).update({ is_profile_completed: true }).eq('id', userId);
            await supabase.auth.updateUser({ data: { role: 'volunteer' } });
            await supabase.auth.refreshSession();
            window.location.href = '/volunteer';
        } catch (error: any) {
            console.error('Volunteer onboarding error:', error);
            alert('Failed to save details: ' + (error?.message || 'Unknown error'));
            setLoading(false);
        }
    };

    return (
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-lg mx-auto bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg">
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
                    <HandHeart className="w-5 h-5 text-white" />
                </div>
                <h2 className="text-xl font-bold dark:text-white">Volunteer Profile</h2>
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Availability Status</label>
                <select {...form.register('availability_status')} className="w-full p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700">
                    <option value="available">Available — Ready to deploy</option>
                    <option value="busy">Busy — Limited availability</option>
                    <option value="on_deployment">On Deployment — Currently active</option>
                    <option value="inactive">Inactive — Not available now</option>
                </select>
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Skills (Select all that apply)</label>
                <div className="grid grid-cols-2 gap-2">
                    {SKILLS.map(skill => (
                        <label key={skill} className="flex items-center space-x-2 border p-2 rounded dark:border-slate-700">
                            <input
                                type="checkbox"
                                value={skill.toLowerCase()}
                                {...form.register('skills')}
                            />
                            <span className="text-sm dark:text-slate-300">{skill}</span>
                        </label>
                    ))}
                </div>
                {form.formState.errors.skills && (
                    <p className="text-red-500 text-xs">{form.formState.errors.skills.message}</p>
                )}
            </div>

            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300">Certifications (Optional)</label>
                <div className="grid grid-cols-2 gap-2">
                    {CERTIFICATIONS.map(cert => (
                        <label key={cert} className="flex items-center space-x-2 border p-2 rounded dark:border-slate-700">
                            <input
                                type="checkbox"
                                value={cert.toLowerCase()}
                                {...form.register('certifications')}
                            />
                            <span className="text-sm dark:text-slate-300">{cert}</span>
                        </label>
                    ))}
                </div>
            </div>

            <button disabled={loading} className="w-full bg-purple-600 hover:bg-purple-700 text-white py-2.5 rounded-lg font-bold flex justify-center items-center gap-2 transition-colors">
                {loading && <Loader2 className="animate-spin w-4 h-4" />}
                Join as Volunteer
            </button>
        </form>
    );
}
