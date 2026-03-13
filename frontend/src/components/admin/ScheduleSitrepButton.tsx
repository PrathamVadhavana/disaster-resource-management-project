import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Loader2, Clock, CheckCircle2, AlertTriangle } from 'lucide-react'

export default function ScheduleSitrepButton() {
    const qc = useQueryClient()
    const [open, setOpen] = useState(false)
    const [selectedInterval, setSelectedInterval] = useState<string>('6')
    const [message, setMessage] = useState<{ type: 'success' | 'error' | null, text: string }>({ type: null, text: '' })

    // Fetch current schedule
    const { data: schedule, isLoading: scheduleLoading } = useQuery({
        queryKey: ['sitrep-schedule'],
        queryFn: () => api.getSitrepSchedule(),
        enabled: open,
    })

    // Update schedule mutation
    const scheduleMutation = useMutation({
        mutationFn: (intervalHours: number) => api.scheduleSitrep({ interval_hours: intervalHours }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['sitrep-schedule'] })
            setMessage({ type: 'success', text: 'SitRep schedule updated successfully' })
            setTimeout(() => setMessage({ type: null, text: '' }), 3000)
            setOpen(false)
        },
        onError: (error: any) => {
            setMessage({ type: 'error', text: `Failed to update schedule: ${error.message || 'Unknown error'}` })
            setTimeout(() => setMessage({ type: null, text: '' }), 5000)
        },
    })

    // Set initial value when schedule data loads
    useEffect(() => {
        if (schedule && schedule.interval_hours) {
            setSelectedInterval(String(schedule.interval_hours))
        }
    }, [schedule])

    const handleSave = () => {
        const interval = parseInt(selectedInterval, 10)
        if (isNaN(interval) || interval < 1 || interval > 24) {
            setMessage({ type: 'error', text: 'Please select a valid interval (1-24 hours)' })
            setTimeout(() => setMessage({ type: null, text: '' }), 3000)
            return
        }
        scheduleMutation.mutate(interval)
    }

    const intervals = [
        { value: '6', label: 'Every 6 hours' },
        { value: '12', label: 'Every 12 hours' },
        { value: '24', label: 'Daily (24 hours)' },
    ]

    if (!open) {
        return (
            <Button
                onClick={() => setOpen(true)}
                variant="outline"
                className="flex items-center gap-2 border-purple-200 dark:border-purple-500/20 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10"
            >
                <Clock className="w-4 h-4" />
                Schedule
            </Button>
        )
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
                            <Clock className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                                Schedule SitRep Generation
                            </h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                Configure automated report generation
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={() => setOpen(false)}
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
                    >
                        <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {message.text && (
                    <div className={`mb-4 p-3 rounded-xl border ${
                        message.type === 'success' 
                            ? 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20' 
                            : 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20'
                    }`}>
                        <p className={`text-xs font-medium ${
                            message.type === 'success' 
                                ? 'text-green-600 dark:text-green-400' 
                                : 'text-red-600 dark:text-red-400'
                        }`}>
                            {message.text}
                        </p>
                    </div>
                )}

                <div className="space-y-4 py-2">
                    <div className="space-y-2">
                        <Label htmlFor="interval">Generation Interval</Label>
                        <select
                            id="interval"
                            value={selectedInterval}
                            onChange={(e) => setSelectedInterval(e.target.value)}
                            className="flex h-10 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:ring-offset-slate-950 dark:placeholder:text-slate-400 dark:focus-visible:ring-blue-500"
                        >
                            {intervals.map((interval) => (
                                <option key={interval.value} value={interval.value}>
                                    {interval.label}
                                </option>
                            ))}
                        </select>
                    </div>

                    {schedule && (
                        <div className="flex items-center gap-2 p-3 bg-purple-50/50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 rounded-lg">
                            <CheckCircle2 className="w-4 h-4 text-purple-500 flex-shrink-0" />
                            <div className="text-xs text-slate-600 dark:text-slate-300">
                                <div className="font-medium">Current Schedule</div>
                                <div>
                                    Daily at {schedule.utc_hour || schedule.interval_hours}:00 UTC
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex items-center gap-2 p-3 bg-amber-50/50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg">
                        <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                        <div className="text-xs text-slate-600 dark:text-slate-300">
                            <div className="font-medium">Note</div>
                            <div>
                                Changes take effect on next system restart or when the cron task is recreated.
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex gap-3 pt-2">
                    <Button
                        onClick={handleSave}
                        disabled={scheduleMutation.isPending}
                        className="flex-1 bg-purple-600 hover:bg-purple-700 text-white"
                    >
                        {scheduleMutation.isPending ? (
                            <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            'Save Schedule'
                        )}
                    </Button>
                    <Button 
                        type="button" 
                        variant="outline" 
                        onClick={() => setOpen(false)}
                        disabled={scheduleMutation.isPending}
                    >
                        Cancel
                    </Button>
                </div>
            </div>
        </div>
    )
}
