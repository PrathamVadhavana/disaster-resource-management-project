'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getVictimProfile, updateVictimProfile, type VictimProfile } from '@/lib/api/victim'
import { cn } from '@/lib/utils'
import { Loader2, MapPin, Save, CheckCircle2 } from 'lucide-react'

const STATUS_OPTIONS = [
    { value: 'safe', label: 'Safe', emoji: '✅', color: 'border-emerald-300 bg-emerald-50 text-emerald-700', darkColor: 'dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400' },
    { value: 'needs_help', label: 'Needs Help', emoji: '🆘', color: 'border-amber-300 bg-amber-50 text-amber-700', darkColor: 'dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400' },
    { value: 'critical', label: 'Critical', emoji: '🚨', color: 'border-red-300 bg-red-50 text-red-700', darkColor: 'dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400' },
    { value: 'evacuated', label: 'Evacuated', emoji: '🏃', color: 'border-blue-300 bg-blue-50 text-blue-700', darkColor: 'dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-400' },
]

const NEEDS_OPTIONS = ['Food', 'Water', 'Medical', 'Shelter', 'Clothing', 'Financial Aid', 'Evacuation', 'Volunteers']

export function ProfileSection() {
    const queryClient = useQueryClient()
    const [saved, setSaved] = useState(false)

    const { data: profile, isLoading } = useQuery<VictimProfile>({
        queryKey: ['victim-profile'],
        queryFn: getVictimProfile,
    })

    const [fullName, setFullName] = useState('')
    const [phone, setPhone] = useState('')
    const [status, setStatus] = useState('safe')
    const [needs, setNeeds] = useState<string[]>([])
    const [medical, setMedical] = useState('')
    const [locationLat, setLocationLat] = useState<number | null>(null)
    const [locationLong, setLocationLong] = useState<number | null>(null)
    const [locating, setLocating] = useState(false)

    useEffect(() => {
        if (profile) {
            setFullName(profile.full_name || '')
            setPhone(profile.phone || '')
            setStatus(profile.current_status || 'safe')
            setNeeds(profile.needs || [])
            setMedical(profile.medical_needs || '')
            setLocationLat(profile.location_lat ?? null)
            setLocationLong(profile.location_long ?? null)
        }
    }, [profile])

    const updateMut = useMutation({
        mutationFn: updateVictimProfile,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['victim-profile'] })
            setSaved(true)
            setTimeout(() => setSaved(false), 3000)
        },
    })

    const detectLocation = () => {
        if (!navigator.geolocation) return
        setLocating(true)
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                setLocationLat(pos.coords.latitude)
                setLocationLong(pos.coords.longitude)
                setLocating(false)
            },
            () => setLocating(false),
            { enableHighAccuracy: true }
        )
    }

    const toggleNeed = (need: string) => {
        setNeeds((prev) => prev.includes(need) ? prev.filter((n) => n !== need) : [...prev, need])
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        updateMut.mutate({
            full_name: fullName,
            phone,
            current_status: status,
            needs,
            medical_needs: medical,
            location_lat: locationLat ?? undefined,
            location_long: locationLong ?? undefined,
        })
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Profile</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your personal information and status</p>
            </div>

            {/* Success */}
            {saved && (
                <div className="flex items-center gap-2 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-sm">
                    <CheckCircle2 className="w-4 h-4" />
                    Profile updated successfully
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Basic Info */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Basic Information</h2>
                    </div>
                    <div className="p-5 space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Full Name</label>
                                <input
                                    type="text"
                                    value={fullName}
                                    onChange={(e) => setFullName(e.target.value)}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Phone</label>
                                <input
                                    type="tel"
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value)}
                                    placeholder="+91 ..."
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Email</label>
                            <input
                                type="email"
                                value={profile?.email || ''}
                                disabled
                                className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-500 text-sm cursor-not-allowed"
                            />
                        </div>
                    </div>
                </div>

                {/* Status */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Current Status</h2>
                    </div>
                    <div className="p-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {STATUS_OPTIONS.map((opt) => (
                            <button
                                key={opt.value}
                                type="button"
                                onClick={() => setStatus(opt.value)}
                                className={cn(
                                    'flex flex-col items-center gap-2 p-4 rounded-xl border-2 text-sm font-semibold transition-all',
                                    status === opt.value
                                        ? cn(opt.color, opt.darkColor, 'ring-2 ring-offset-1 ring-offset-white dark:ring-offset-slate-950')
                                        : 'border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-white/20'
                                )}
                            >
                                <span className="text-2xl">{opt.emoji}</span>
                                <span>{opt.label}</span>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Immediate Needs */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Immediate Needs</h2>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Select all that apply</p>
                    </div>
                    <div className="p-5 flex flex-wrap gap-2">
                        {NEEDS_OPTIONS.map((need) => (
                            <button
                                key={need}
                                type="button"
                                onClick={() => toggleNeed(need)}
                                className={cn(
                                    'px-4 py-2 rounded-xl border text-sm font-medium transition-all',
                                    needs.includes(need)
                                        ? 'border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                                        : 'border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-white/20'
                                )}
                            >
                                {need}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Medical */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Medical Requirements</h2>
                    </div>
                    <div className="p-5">
                        <textarea
                            value={medical}
                            onChange={(e) => setMedical(e.target.value)}
                            rows={3}
                            placeholder="Any medical conditions, allergies, or medication needs…"
                            className="w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 resize-none"
                        />
                    </div>
                </div>

                {/* Location */}
                <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 dark:border-white/5">
                        <h2 className="font-semibold text-slate-900 dark:text-white">Location</h2>
                    </div>
                    <div className="p-5">
                        <button
                            type="button"
                            onClick={detectLocation}
                            disabled={locating}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 text-sm font-medium hover:bg-slate-200 dark:hover:bg-white/10 transition-colors disabled:opacity-50"
                        >
                            {locating ? <Loader2 className="w-4 h-4 animate-spin" /> : <MapPin className="w-4 h-4" />}
                            {locationLat ? 'Update Location' : 'Detect My Location'}
                        </button>
                        {locationLat && locationLong && (
                            <p className="text-xs text-slate-400 mt-2">
                                📍 {locationLat.toFixed(4)}, {locationLong.toFixed(4)}
                            </p>
                        )}
                    </div>
                </div>

                {/* Error */}
                {updateMut.error && (
                    <div className="p-4 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400 text-sm">
                        {updateMut.error.message}
                    </div>
                )}

                {/* Submit */}
                <button
                    type="submit"
                    disabled={updateMut.isPending}
                    className="w-full py-3.5 rounded-xl bg-gradient-to-r from-red-500 to-orange-600 text-white font-semibold text-sm shadow-lg shadow-red-500/20 hover:shadow-red-500/30 hover:brightness-110 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {updateMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    Save Profile
                </button>
            </form>
        </div>
    )
}
