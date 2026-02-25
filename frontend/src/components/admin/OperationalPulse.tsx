'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'
import {
    Activity, ShieldCheck, HeartHandshake,
    UserPlus, PackageSearch, AlertCircle,
    User, Target, Zap
} from 'lucide-react'
import { cn } from '@/lib/utils'

export function OperationalPulseTimeline() {
    const { data: logs, isLoading } = useQuery({
        queryKey: ['operational-pulse'],
        queryFn: () => api.getOperationalPulse({ limit: 30 }),
        refetchInterval: 10000, // Refresh every 10s for "live" feel
    })

    if (isLoading) {
        return (
            <div className="flex flex-col gap-4">
                {[1, 2, 3].map(i => (
                    <div key={i} className="h-20 bg-slate-100 dark:bg-white/5 animate-pulse rounded-2xl" />
                ))}
            </div>
        )
    }

    const actionConfig: Record<string, { icon: any, color: string, label: string }> = {
        'VERIFIED_REQUEST': { icon: ShieldCheck, color: 'text-emerald-500 bg-emerald-500/10', label: 'Field Verification' },
        'PLEDGED_RESOURCES': { icon: HeartHandshake, color: 'text-rose-500 bg-rose-500/10', label: 'Donor Pledge' },
        'ASSIGNED_VOLUNTEER': { icon: UserPlus, color: 'text-blue-500 bg-blue-500/10', label: 'Team Mobilization' },
        'CREATED_SOURCING': { icon: PackageSearch, color: 'text-amber-500 bg-amber-500/10', label: 'Resource Sourcing' },
        'JOINED_MISSION': { icon: Zap, color: 'text-purple-500 bg-purple-500/10', label: 'Mission Deployment' },
        'CREATED_MOBILIZATION': { icon: Activity, color: 'text-indigo-500 bg-indigo-500/10', label: 'New Mission' },
    }

    return (
        <div className="space-y-4">
            {logs?.length ? (
                logs.map((log: any) => {
                    const config = actionConfig[log.action_type] || { icon: AlertCircle, color: 'text-slate-500 bg-slate-500/10', label: log.action_type }
                    const Icon = config.icon

                    return (
                        <div key={log.id} className="group relative flex gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/[0.02] hover:shadow-md transition-all">
                            <div className={cn("w-10 h-10 shrink-0 rounded-xl flex items-center justify-center", config.color)}>
                                <Icon className="w-5 h-5" />
                            </div>

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                        {config.label}
                                    </span>
                                    <span className="text-[10px] text-slate-400">
                                        {formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}
                                    </span>
                                </div>

                                <p className="text-sm font-medium text-slate-900 dark:text-white mt-0.5 leading-snug">
                                    {log.description}
                                </p>

                                <div className="flex items-center gap-4 mt-2">
                                    <div className="flex items-center gap-1">
                                        <User className="w-3 h-3 text-slate-400" />
                                        <span className="text-[10px] text-slate-500 truncate max-w-[80px]">{log.actor_id}</span>
                                    </div>
                                    {log.target_id && (
                                        <div className="flex items-center gap-1">
                                            <Target className="w-3 h-3 text-slate-400" />
                                            <span className="text-[10px] text-slate-500 truncate max-w-[80px]">{log.target_id}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )
                })
            ) : (
                <div className="text-center py-10 border-2 border-dashed border-slate-200 dark:border-white/5 rounded-2xl">
                    <p className="text-slate-400 text-sm">No operational pulse detected yet.</p>
                </div>
            )}
        </div>
    )
}
