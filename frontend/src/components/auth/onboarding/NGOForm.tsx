'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ngoDetailsSchema } from '@/types/auth';
import type { z } from 'zod';
import { db } from '@/lib/db';
import { getSupabaseClient } from '@/lib/supabase/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Loader2, MapPin, LocateFixed } from 'lucide-react';

type NGOFormData = z.infer<typeof ngoDetailsSchema>;

export function NGOForm({ userId }: { userId: string }) {
    const router = useRouter();
    const [loading, setLoading] = useState(false);
    const [gpsLoading, setGpsLoading] = useState(false);
    const [gpsStatus, setGpsStatus] = useState<'idle' | 'success' | 'error'>('idle');

    const form = useForm<NGOFormData>({
        resolver: zodResolver(ngoDetailsSchema),
        defaultValues: {
            organization_name: '',
            registration_number: '',
            operating_sectors: [],
            website: '',
            phone_number: '',
            address: '',
            latitude: undefined,
            longitude: undefined,
        }
    });

    const handleUseGPS = async () => {
        if (!navigator.geolocation) {
            setGpsStatus('error');
            return;
        }
        setGpsLoading(true);
        setGpsStatus('idle');
        navigator.geolocation.getCurrentPosition(
            async (pos) => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                form.setValue('latitude', lat);
                form.setValue('longitude', lng);
                // Try reverse geocoding
                try {
                    const resp = await fetch(
                        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`,
                        { headers: { 'Accept-Language': 'en' } }
                    );
                    const data = await resp.json();
                    if (data?.display_name) {
                        form.setValue('address', data.display_name);
                    }
                } catch {
                    // GPS coords set, address stays manual
                }
                setGpsLoading(false);
                setGpsStatus('success');
            },
            () => {
                setGpsLoading(false);
                setGpsStatus('error');
            },
            { enableHighAccuracy: true, timeout: 15000 }
        );
    };

    const onSubmit = async (data: NGOFormData) => {
        setLoading(true);
        try {
            const sb = getSupabaseClient();
            const { data: { session } } = await sb.auth.getSession();
            await db.upsertProfile({ id: userId, email: session?.user?.email ?? '', role: 'ngo' });

            try {
                await db.upsertDetails('ngo_details', {
                    id: userId,
                    organization_name: data.organization_name,
                    registration_number: data.registration_number,
                    operating_sectors: data.operating_sectors,
                    website: data.website || null,
                    phone_number: data.phone_number || null,
                    address: data.address || null,
                    latitude: data.latitude || null,
                    longitude: data.longitude || null,
                    verification_status: 'pending',
                });
            } catch (detailsErr: any) {
                console.error('ngo_details save failed (non-fatal):', detailsErr);
            }

            // Also update users table with phone for easy access
            try {
                await db.updateProfile({
                    is_profile_completed: true,
                    phone: data.phone_number || null,
                    organization: data.organization_name,
                });
            } catch {
                await db.updateProfile({ is_profile_completed: true });
            }

            if (session) {
                document.cookie = `sb-token=${session.access_token}; path=/; max-age=3600; SameSite=Lax`;
                document.cookie = `sb-role=ngo; path=/; max-age=3600; SameSite=Lax`;
            }
            document.cookie = `profile-completed=true; path=/; max-age=86400; SameSite=Lax`;

            window.location.href = '/ngo';
        } catch (error: any) {
            console.error('NGO onboarding submit error:', error);
            alert('Failed to complete onboarding: ' + (error?.message || 'Unknown error'));
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
                <label className="text-sm font-medium dark:text-slate-300">Phone Number</label>
                <input
                    {...form.register('phone_number')}
                    type="tel"
                    placeholder="+91 98765 43210"
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

            {/* Address with GPS support */}
            <div className="space-y-2">
                <label className="text-sm font-medium dark:text-slate-300 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5" /> Address
                </label>
                <div className="flex gap-2">
                    <input
                        {...form.register('address')}
                        placeholder="Enter address or use GPS"
                        className="flex-1 p-2 border rounded-md dark:bg-slate-800 dark:border-slate-700"
                    />
                    <button
                        type="button"
                        onClick={handleUseGPS}
                        disabled={gpsLoading}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                    >
                        {gpsLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LocateFixed className="w-3.5 h-3.5" />}
                        Use GPS
                    </button>
                </div>
                {gpsStatus === 'success' && (
                    <p className="text-green-600 text-xs flex items-center gap-1">
                        <LocateFixed className="w-3 h-3" /> GPS location captured successfully
                    </p>
                )}
                {gpsStatus === 'error' && (
                    <p className="text-amber-600 text-xs">GPS unavailable — please type your address manually.</p>
                )}
                {form.formState.errors.address && <p className="text-red-500 text-xs">{form.formState.errors.address.message}</p>}
                {form.watch('latitude') && form.watch('longitude') && (
                    <p className="text-xs text-slate-400">
                        Coordinates: {form.watch('latitude')?.toFixed(5)}, {form.watch('longitude')?.toFixed(5)}
                    </p>
                )}
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
