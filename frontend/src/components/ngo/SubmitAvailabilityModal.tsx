'use client'

import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
    X, Loader2, MapPin, Clock, Truck, Users, MessageSquare,
    Navigation, CheckCircle2
} from 'lucide-react'

interface Props {
    request: any
    onClose: () => void
}

export function SubmitAvailabilityModal({ request, onClose }: Props) {
    const qc = useQueryClient()
    const [form, setForm] = useState({
        available_quantity: request.quantity || 1,
        estimated_delivery_time: '',
        assigned_team: '',
        vehicle_type: '',
        ngo_latitude: 0,
        ngo_longitude: 0,
        notes: '',
    })
    const [gpsStatus, setGpsStatus] = useState<'detecting' | 'success' | 'error' | 'manual'>('detecting')
    const [gpsError, setGpsError] = useState('')
    const [submitted, setSubmitted] = useState(false)

    // Auto-detect GPS
    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    setForm(f => ({
                        ...f,
                        ngo_latitude: pos.coords.latitude,
                        ngo_longitude: pos.coords.longitude,
                    }))
                    setGpsStatus('success')
                },
                (err) => {
                    setGpsStatus('manual')
                    if (err.code === 1) {
                        setGpsError('Location permission denied. Please allow location access or enter coordinates manually.')
                    } else if (err.code === 2) {
                        setGpsError('Location unavailable. If using HTTP (not HTTPS), GPS may be blocked by the browser. Enter coordinates manually.')
                    } else {
                        setGpsError('Location detection timed out. Please enter coordinates manually.')
                    }
                },
                { enableHighAccuracy: true, timeout: 10000 }
            )
        } else {
            setGpsStatus('manual')
            setGpsError('Geolocation is not supported by this browser. Please enter coordinates manually.')
        }
    }, [])

    const mutation = useMutation({
        mutationFn: () => api.submitNgoAvailability(request.id, form),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['ngo-fulfillment'] })
            qc.invalidateQueries({ queryKey: ['ngo-enhanced-stats'] })
            setSubmitted(true)
        },
    })

    if (submitted) {
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-8 text-center">
                    <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-500/10 flex items-center justify-center mx-auto mb-4">
                        <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
                    </div>
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Availability Submitted!</h2>
                    <p className="text-sm text-slate-500 mb-6">Admin has been notified. Further edits are locked until admin reopens.</p>
                    <button onClick={onClose}
                        className="px-6 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
                        Close
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-5">
                    <div>
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white">Submit Availability</h2>
                        <p className="text-xs text-slate-500 mt-0.5">Request: {request.resource_type} — {request.victim_name || 'Victim'}</p>
                    </div>
                    <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors">
                        <X className="w-4 h-4 text-slate-400" />
                    </button>
                </div>

                {mutation.error && (
                    <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                        <p className="text-xs text-red-600 dark:text-red-400 font-medium">
                            {(mutation.error as Error).message || 'Submission failed'}
                        </p>
                    </div>
                )}

                <form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }} className="space-y-4">
                    {/* Available Quantity */}
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                            <Truck className="w-3.5 h-3.5" /> Available Quantity
                        </label>
                        <input type="number" min="1" value={form.available_quantity}
                            onChange={(e) => setForm({ ...form, available_quantity: parseInt(e.target.value) || 1 })} required
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        <p className="text-[10px] text-slate-400 mt-1">Requested: {request.quantity || 'N/A'}</p>
                    </div>

                    {/* Estimated Delivery Time */}
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                            <Clock className="w-3.5 h-3.5" /> Estimated Delivery Time
                        </label>
                        <input type="datetime-local" value={form.estimated_delivery_time}
                            onChange={(e) => setForm({ ...form, estimated_delivery_time: e.target.value })} required
                            className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        {/* Assigned Team */}
                        <div>
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                                <Users className="w-3.5 h-3.5" /> Assigned Team
                            </label>
                            <input type="text" value={form.assigned_team}
                                onChange={(e) => setForm({ ...form, assigned_team: e.target.value })}
                                placeholder="e.g. Alpha Team"
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>

                        {/* Vehicle Type */}
                        <div>
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                                <Truck className="w-3.5 h-3.5" /> Vehicle Type
                            </label>
                            <select value={form.vehicle_type}
                                onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })}
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none">
                                <option value="">Select...</option>
                                <option value="truck">Truck</option>
                                <option value="van">Van</option>
                                <option value="ambulance">Ambulance</option>
                                <option value="helicopter">Helicopter</option>
                                <option value="boat">Boat</option>
                                <option value="motorcycle">Motorcycle</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                    </div>

                    {/* GPS Coordinates */}
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                            <Navigation className="w-3.5 h-3.5" /> NGO GPS Coordinates
                            {gpsStatus === 'success' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-500/10 text-green-600 font-medium">Auto-detected</span>
                            )}
                            {gpsStatus === 'detecting' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-600 font-medium flex items-center gap-1">
                                    <Loader2 className="w-2.5 h-2.5 animate-spin" /> Detecting...
                                </span>
                            )}
                            {gpsStatus === 'manual' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/10 text-red-500 font-medium">Manual entry</span>
                            )}
                        </label>
                        {gpsError && (
                            <p className="text-[11px] text-amber-600 dark:text-amber-400 mb-2 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-3 py-2">
                                {gpsError}
                            </p>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                            <input type="number" step="any" value={form.ngo_latitude || ''}
                                onChange={(e) => setForm({ ...form, ngo_latitude: parseFloat(e.target.value) || 0 })}
                                placeholder="Latitude"
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                            <input type="number" step="any" value={form.ngo_longitude || ''}
                                onChange={(e) => setForm({ ...form, ngo_longitude: parseFloat(e.target.value) || 0 })}
                                placeholder="Longitude"
                                className="w-full h-10 px-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                        </div>
                    </div>

                    {/* Notes */}
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                            <MessageSquare className="w-3.5 h-3.5" /> Notes
                        </label>
                        <textarea value={form.notes}
                            onChange={(e) => setForm({ ...form, notes: e.target.value })}
                            rows={3} placeholder="Additional information..."
                            className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none" />
                    </div>

                    <button type="submit" disabled={mutation.isPending}
                        className="w-full h-11 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-600 text-white text-sm font-semibold hover:from-blue-700 hover:to-cyan-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2 shadow-lg shadow-blue-600/20">
                        {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                        {mutation.isPending ? 'Submitting...' : 'Submit Availability'}
                    </button>
                </form>
            </div>
        </div>
    )
}
