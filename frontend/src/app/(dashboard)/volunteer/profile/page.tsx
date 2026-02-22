'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-provider'
import {
    User, Mail, Phone, MapPin, Shield, Save,
    Loader2, CheckCircle2, Edit2, Award, Calendar, Building
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface VolunteerProfileData {
    skills: string[]
    availability: string
    experience: string
    emergencyContact: string
    languages: string[]
    bio: string
}

const SKILL_OPTIONS = [
    'First Aid', 'CPR', 'Search & Rescue', 'Firefighting', 'Medical',
    'Logistics', 'Communication', 'Translation', 'Driving', 'Construction',
    'Mental Health Support', 'Child Care', 'Cooking', 'Water Purification',
]

const AVAILABILITY_OPTIONS = ['Full-time', 'Part-time', 'Weekends Only', 'On-call', 'Emergency Only']

export default function VolunteerProfilePage() {
    const { user, profile, updateProfile } = useAuth()
    const [editing, setEditing] = useState(false)
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)

    // Profile fields from auth
    const [fullName, setFullName] = useState('')
    const [phone, setPhone] = useState('')
    const [organization, setOrganization] = useState('')

    // Extended volunteer profile from API/metadata
    const [volProfile, setVolProfile] = useState<VolunteerProfileData>({
        skills: [], availability: 'On-call', experience: '', emergencyContact: '', languages: [], bio: '',
    })

    const { data: profileData, isLoading } = useQuery({
        queryKey: ['volunteer-profile'],
        queryFn: async () => {
            const res = await api.getVolunteerProfile()
            return res as VolunteerProfileData | null
        },
    })

    // Initialize from auth profile + API data
    useEffect(() => {
        if (profile) {
            setFullName(profile.full_name || '')
            setPhone(profile.phone || '')
            setOrganization(profile.organization || '')
        }
    }, [profile])

    useEffect(() => {
        if (profileData && typeof profileData === 'object') {
            setVolProfile({
                skills: profileData.skills ?? [],
                availability: profileData.availability ?? 'On-call',
                experience: profileData.experience ?? '',
                emergencyContact: profileData.emergencyContact ?? '',
                languages: profileData.languages ?? [],
                bio: profileData.bio ?? '',
            })
        }
    }, [profileData])

    const handleSave = async () => {
        setSaving(true)
        try {
            // Update basic profile via auth
            await updateProfile({ full_name: fullName, phone, organization })

            // Update extended profile via API
            await api.updateVolunteerProfile({
                skills: volProfile.skills,
                availability: volProfile.availability,
                experience: volProfile.experience,
                emergencyContact: volProfile.emergencyContact,
                languages: volProfile.languages,
                bio: volProfile.bio,
            })

            setSaved(true)
            setEditing(false)
            setTimeout(() => setSaved(false), 3000)
        } catch (e) {
            console.error('Failed to save profile:', e)
        } finally {
            setSaving(false)
        }
    }

    const toggleSkill = (skill: string) => {
        setVolProfile(prev => ({
            ...prev,
            skills: prev.skills.includes(skill) ? prev.skills.filter(s => s !== skill) : [...prev.skills, skill]
        }))
    }

    if (isLoading) {
        return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
    }

    return (
        <div className="space-y-6 max-w-3xl">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">My Profile</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your volunteer information</p>
                </div>
                <div className="flex items-center gap-2">
                    {saved && (
                        <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Saved
                        </span>
                    )}
                    {!editing ? (
                        <button onClick={() => setEditing(true)}
                            className="h-9 px-4 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 flex items-center gap-2">
                            <Edit2 className="w-4 h-4" /> Edit Profile
                        </button>
                    ) : (
                        <button onClick={handleSave} disabled={saving}
                            className="h-9 px-4 rounded-xl bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 flex items-center gap-2">
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                            Save Changes
                        </button>
                    )}
                </div>
            </div>

            {/* Avatar & Basic Info */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <div className="flex items-center gap-5 mb-6">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xl font-bold">
                        {fullName ? fullName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() : user?.email?.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white">{fullName || 'Your Name'}</h2>
                        <p className="text-sm text-slate-500">{user?.email}</p>
                        <span className="inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 mt-1">
                            Volunteer
                        </span>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Full Name</label>
                        <input value={fullName} onChange={e => setFullName(e.target.value)} disabled={!editing}
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Phone</label>
                        <input value={phone} onChange={e => setPhone(e.target.value)} disabled={!editing}
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Organization</label>
                        <input value={organization} onChange={e => setOrganization(e.target.value)} disabled={!editing}
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Availability</label>
                        <select value={volProfile.availability} onChange={e => setVolProfile({ ...volProfile, availability: e.target.value })} disabled={!editing}
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60">
                            {AVAILABILITY_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {/* Bio */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">About Me</h3>
                <textarea value={volProfile.bio} onChange={e => setVolProfile({ ...volProfile, bio: e.target.value })} disabled={!editing}
                    rows={3} placeholder="Tell teams about your background and motivation..."
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60 resize-none" />
            </div>

            {/* Skills */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Skills & Capabilities</h3>
                <div className="flex flex-wrap gap-2">
                    {SKILL_OPTIONS.map(skill => {
                        const active = volProfile.skills.includes(skill)
                        return (
                            <button key={skill} onClick={() => editing && toggleSkill(skill)} disabled={!editing}
                                className={cn('px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                                    active ? 'bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20' : 'bg-white dark:bg-white/[0.02] text-slate-500 border-slate-200 dark:border-white/10',
                                    editing ? 'cursor-pointer hover:shadow-sm' : 'cursor-default disabled:opacity-70'
                                )}>
                                {active && <CheckCircle2 className="w-3 h-3 inline mr-1" />}
                                {skill}
                            </button>
                        )
                    })}
                </div>
            </div>

            {/* Additional Info */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Additional Information</h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Experience</label>
                        <input value={volProfile.experience} onChange={e => setVolProfile({ ...volProfile, experience: e.target.value })} disabled={!editing}
                            placeholder="e.g. 3 years disaster relief"
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">Emergency Contact</label>
                        <input value={volProfile.emergencyContact} onChange={e => setVolProfile({ ...volProfile, emergencyContact: e.target.value })} disabled={!editing}
                            placeholder="Name & phone number"
                            className="w-full h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm disabled:opacity-60" />
                    </div>
                </div>
            </div>
        </div>
    )
}
