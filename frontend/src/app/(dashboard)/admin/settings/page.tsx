'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    Settings, Globe, Bell, Shield, Database,
    Save, CheckCircle2, Loader2, ToggleLeft, ToggleRight,
    Lock, AlertTriangle
} from 'lucide-react'

interface PlatformSettings {
    platform_name: string
    support_email: string
    auto_sitrep: boolean
    sitrep_interval: number
    auto_allocate: boolean
    ingestion_enabled: boolean
    ingestion_interval: number
    email_notifications: boolean
    sms_alerts: boolean
    maintenance_mode: boolean
    api_rate_limit: number
    max_upload_mb: number
    session_timeout: number
    data_retention_days: number
}

const DEFAULT_SETTINGS: PlatformSettings = {
    platform_name: 'DisasterRM',
    support_email: 'admin@disasterrm.org',
    auto_sitrep: true,
    sitrep_interval: 6,
    auto_allocate: true,
    ingestion_enabled: true,
    ingestion_interval: 5,
    email_notifications: true,
    sms_alerts: false,
    maintenance_mode: false,
    api_rate_limit: 100,
    max_upload_mb: 10,
    session_timeout: 60,
    data_retention_days: 365,
}

export default function AdminSettingsPage() {
    const queryClient = useQueryClient()
    const [saved, setSaved] = useState(false)
    const [settings, setSettings] = useState<PlatformSettings>(DEFAULT_SETTINGS)
    const [purging, setPurging] = useState(false)

    // Fetch settings from backend API
    const { data: serverSettings, isLoading } = useQuery<PlatformSettings>({
        queryKey: ['admin-settings'],
        queryFn: () => api.getSettings(),
    })

    // Sync server settings to local state when loaded
    useEffect(() => {
        if (serverSettings) {
            setSettings({
                ...DEFAULT_SETTINGS,
                ...serverSettings,
            })
        }
    }, [serverSettings])

    // Save mutation
    const saveMutation = useMutation({
        mutationFn: (data: Partial<PlatformSettings>) => api.updateSettings(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
            setSaved(true)
            setTimeout(() => setSaved(false), 3000)
        },
    })

    const toggleSetting = (key: keyof PlatformSettings) => {
        setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
    }

    const handleSave = async () => {
        // Save to backend
        saveMutation.mutate(settings)
        // If ingestion toggle changed, call backend
        if (settings.ingestion_enabled) {
            await api.startOrchestrator().catch(() => {})
        } else {
            await api.stopOrchestrator().catch(() => {})
        }
    }

    const handlePurgeCache = async () => {
        setPurging(true)
        try {
            // Clear browser caches + localStorage cache entries
            if ('caches' in window) {
                const keys = await caches.keys()
                await Promise.all(keys.map(k => caches.delete(k)))
            }
            // Clear react-query cache
            localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        } catch { /* ignore */ }
        setPurging(false)
    }

    const handleResetSettings = () => {
        setSettings(DEFAULT_SETTINGS)
        saveMutation.mutate(DEFAULT_SETTINGS)
    }

    const Toggle = ({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) => (
        <button onClick={onToggle} className="relative">
            {enabled ? (
                <ToggleRight className="w-9 h-9 text-purple-600" />
            ) : (
                <ToggleLeft className="w-9 h-9 text-slate-300 dark:text-slate-600" />
            )}
        </button>
    )

    const toggleSettings = [
        { key: 'auto_sitrep' as const, label: 'Auto-generate Situation Reports', desc: 'AI coordinator generates SitReps automatically' },
        { key: 'auto_allocate' as const, label: 'Automatic Resource Allocation', desc: 'LP solver runs allocation automatically for new requests' },
        { key: 'ingestion_enabled' as const, label: 'Data Ingestion Pipeline', desc: 'Fetch data from USGS, GDACS, NASA, weather sources' },
        { key: 'email_notifications' as const, label: 'Email Notifications', desc: 'Send email alerts for critical events' },
        { key: 'sms_alerts' as const, label: 'SMS Alerts', desc: 'Send SMS for disaster alerts (carrier charges may apply)' },
        { key: 'maintenance_mode' as const, label: 'Maintenance Mode', desc: 'Put platform in maintenance mode (users see maintenance page)' },
    ]

    return (
        <div className="space-y-6 max-w-2xl">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Platform Settings</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Configure system-wide settings and preferences
                    </p>
                </div>
                <button onClick={handleSave} disabled={saveMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors shadow-lg shadow-purple-600/20">
                    {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                    {saveMutation.isPending ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
                </button>
            </div>

            {/* General */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Globe className="w-4 h-4 text-purple-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">General</h3>
                </div>
                <div className="space-y-4">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Platform Name</label>
                        <input value={settings.platform_name} onChange={(e) => setSettings({ ...settings, platform_name: e.target.value })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Support Email</label>
                        <input type="email" value={settings.support_email} onChange={(e) => setSettings({ ...settings, support_email: e.target.value })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                </div>
            </div>

            {/* Feature Toggles */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Settings className="w-4 h-4 text-purple-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Feature Toggles</h3>
                </div>
                <div className="space-y-4">
                    {toggleSettings.map((ts) => (
                        <div key={ts.key} className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-white/5 last:border-0">
                            <div>
                                <p className="text-sm font-medium text-slate-900 dark:text-white">{ts.label}</p>
                                <p className="text-xs text-slate-400">{ts.desc}</p>
                            </div>
                            <Toggle enabled={settings[ts.key] as boolean} onToggle={() => toggleSetting(ts.key)} />
                        </div>
                    ))}
                </div>
            </div>

            {/* Data & Security */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Lock className="w-4 h-4 text-purple-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Data &amp; Security</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">API Rate Limit (req/min)</label>
                        <input type="number" value={settings.api_rate_limit} onChange={(e) => setSettings({ ...settings, api_rate_limit: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Session Timeout (min)</label>
                        <input type="number" value={settings.session_timeout} onChange={(e) => setSettings({ ...settings, session_timeout: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Max Upload Size (MB)</label>
                        <input type="number" value={settings.max_upload_mb} onChange={(e) => setSettings({ ...settings, max_upload_mb: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Data Retention (days)</label>
                        <input type="number" value={settings.data_retention_days} onChange={(e) => setSettings({ ...settings, data_retention_days: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                </div>
            </div>

            {/* Data Ingestion */}
            <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Database className="w-4 h-4 text-purple-500" />
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Data Ingestion</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">Ingestion Interval (min)</label>
                        <input type="number" value={settings.ingestion_interval} onChange={(e) => setSettings({ ...settings, ingestion_interval: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 block">SitRep Interval (hours)</label>
                        <input type="number" value={settings.sitrep_interval} onChange={(e) => setSettings({ ...settings, sitrep_interval: parseInt(e.target.value) || 0 })}
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-purple-500 focus:outline-none" />
                    </div>
                </div>
            </div>

            {/* Danger Zone */}
            <div className="rounded-2xl border-2 border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 p-6">
                <h3 className="text-sm font-bold text-red-700 dark:text-red-400 mb-2">Danger Zone</h3>
                <p className="text-xs text-red-600/70 dark:text-red-400/70 mb-4">These actions may affect system stability. Proceed with caution.</p>
                <div className="flex gap-3">
                    <button onClick={handlePurgeCache} disabled={purging}
                        className="px-4 py-2 rounded-xl border border-red-300 dark:border-red-500/30 text-red-700 dark:text-red-400 text-sm font-medium hover:bg-red-100 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50">
                        {purging ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : null}
                        Purge Cache
                    </button>
                    <button onClick={handleResetSettings}
                        className="px-4 py-2 rounded-xl border border-red-300 dark:border-red-500/30 text-red-700 dark:text-red-400 text-sm font-medium hover:bg-red-100 dark:hover:bg-red-500/10 transition-colors">
                        Reset Settings
                    </button>
                </div>
            </div>
        </div>
    )
}
