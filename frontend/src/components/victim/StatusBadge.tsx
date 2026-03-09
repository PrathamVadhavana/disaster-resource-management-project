'use client'

import { cn } from '@/lib/utils'

// ─── Status Badge ───────────────────────────────────────
const statusConfig: Record<string, { label: string; light: string; dark: string }> = {
    pending: { label: 'Pending', light: 'bg-amber-50 text-amber-700 border-amber-200', dark: 'dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20' },
    approved: { label: 'Approved', light: 'bg-blue-50 text-blue-700 border-blue-200', dark: 'dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20' },
    under_review: { label: 'Under Review', light: 'bg-amber-50 text-amber-700 border-amber-200', dark: 'dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20' },
    availability_submitted: { label: 'Resources Ready', light: 'bg-cyan-50 text-cyan-700 border-cyan-200', dark: 'dark:bg-cyan-500/10 dark:text-cyan-400 dark:border-cyan-500/20' },
    assigned: { label: 'Assigned', light: 'bg-purple-50 text-purple-700 border-purple-200', dark: 'dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20' },
    in_progress: { label: 'In Progress', light: 'bg-cyan-50 text-cyan-700 border-cyan-200', dark: 'dark:bg-cyan-500/10 dark:text-cyan-400 dark:border-cyan-500/20' },
    delivered: { label: 'Delivered', light: 'bg-teal-50 text-teal-700 border-teal-200', dark: 'dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/20' },
    completed: { label: 'Completed', light: 'bg-emerald-50 text-emerald-700 border-emerald-200', dark: 'dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20' },
    closed: { label: 'Closed', light: 'bg-gray-50 text-gray-600 border-gray-200', dark: 'dark:bg-gray-500/10 dark:text-gray-400 dark:border-gray-500/20' },
    rejected: { label: 'Rejected', light: 'bg-red-50 text-red-700 border-red-200', dark: 'dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20' },
}

export function StatusBadge({ status }: { status: string }) {
    const cfg = statusConfig[status] || statusConfig.pending
    return (
        <span className={cn('inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border', cfg.light, cfg.dark)}>
            {cfg.label}
        </span>
    )
}

// ─── Priority Badge ─────────────────────────────────────
const priorityConfig: Record<string, { label: string; light: string; dark: string; dot: string }> = {
    critical: { label: 'Critical', light: 'bg-red-50 text-red-700', dark: 'dark:bg-red-500/10 dark:text-red-400', dot: 'bg-red-500' },
    high: { label: 'High', light: 'bg-orange-50 text-orange-700', dark: 'dark:bg-orange-500/10 dark:text-orange-400', dot: 'bg-orange-500' },
    medium: { label: 'Medium', light: 'bg-yellow-50 text-yellow-700', dark: 'dark:bg-yellow-500/10 dark:text-yellow-400', dot: 'bg-yellow-500' },
    low: { label: 'Low', light: 'bg-slate-100 text-slate-600', dark: 'dark:bg-slate-500/10 dark:text-slate-400', dot: 'bg-slate-400' },
}

export function PriorityBadge({ priority }: { priority: string }) {
    const cfg = priorityConfig[priority] || priorityConfig.medium
    return (
        <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold', cfg.light, cfg.dark)}>
            <span className={cn('w-1.5 h-1.5 rounded-full', cfg.dot)} />
            {cfg.label}
        </span>
    )
}

// ─── Resource Type Icon ─────────────────────────────────
const typeEmoji: Record<string, string> = {
    'Food': '🍞',
    'Water': '💧',
    'Medical': '🏥',
    'Shelter': '🏠',
    'Clothing': '👕',
    'Financial Aid': '💰',
    'Evacuation': '🚁',
    'Volunteers': '🙋',
    'Custom': '📦',
    'Multiple': '📋',
}

export function ResourceTypeIcon({ type, size = 'md' }: { type: string; size?: 'sm' | 'md' | 'lg' }) {
    const emoji = typeEmoji[type] || '📦'
    const sizeClass = { sm: 'w-8 h-8 text-base', md: 'w-10 h-10 text-lg', lg: 'w-12 h-12 text-xl' }
    return (
        <div className={cn(sizeClass[size], 'rounded-xl bg-slate-100 dark:bg-white/5 flex items-center justify-center')}>
            {emoji}
        </div>
    )
}
