'use client'

import { cn } from '@/lib/utils'
import { AlertTriangle, Heart, Baby, Droplets, Shield, Flame, Clock } from 'lucide-react'

export interface UrgencySignal {
    keyword: string
    label: string
    severity_boost: number
}

// Severity boost → color mapping
const SEVERITY_COLORS: Record<number, { bg: string; text: string; border: string; darkBg: string; darkText: string; darkBorder: string }> = {
    3: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200', darkBg: 'dark:bg-red-500/15', darkText: 'dark:text-red-400', darkBorder: 'dark:border-red-500/30' },
    2: { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-200', darkBg: 'dark:bg-orange-500/15', darkText: 'dark:text-orange-400', darkBorder: 'dark:border-orange-500/30' },
    1: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-200', darkBg: 'dark:bg-yellow-500/15', darkText: 'dark:text-yellow-400', darkBorder: 'dark:border-yellow-500/30' },
    0: { bg: 'bg-slate-100', text: 'text-slate-600', border: 'border-slate-200', darkBg: 'dark:bg-slate-500/15', darkText: 'dark:text-slate-400', darkBorder: 'dark:border-slate-500/30' },
}

// Label → icon mapping
const LABEL_ICONS: Record<string, typeof AlertTriangle> = {
    unconscious: AlertTriangle,
    trapped: Shield,
    severe_bleeding: Heart,
    drowning: Droplets,
    crush_injury: AlertTriangle,
    immobile: Shield,
    infant: Baby,
    elderly: Heart,
    pregnant: Heart,
    disabled: Shield,
    prolonged_deprivation: Clock,
    dehydration_starvation: Droplets,
    no_water: Droplets,
    no_food: Flame,
    no_shelter: Shield,
    no_medicine: Heart,
    injury: AlertTriangle,
    infection: AlertTriangle,
    chronic_medical: Heart,
    respiratory: AlertTriangle,
    cardiac_symptom: Heart,
    seizure: AlertTriangle,
    large_group: Shield,
    children_present: Baby,
}

function getColorClasses(boost: number) {
    return SEVERITY_COLORS[Math.min(boost, 3)] || SEVERITY_COLORS[0]
}

function getIcon(label: string) {
    return LABEL_ICONS[label] || AlertTriangle
}

function formatLabel(label: string): string {
    return label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function UrgencyTag({ signal }: { signal: UrgencySignal }) {
    const colors = getColorClasses(signal.severity_boost)
    const Icon = getIcon(signal.label)

    return (
        <span
            className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-medium',
                colors.bg, colors.text, colors.border,
                colors.darkBg, colors.darkText, colors.darkBorder,
            )}
            title={`Urgency signal: ${signal.keyword} (severity +${signal.severity_boost})`}
        >
            <Icon className="w-3 h-3" />
            {formatLabel(signal.label)}
        </span>
    )
}

export function UrgencyTags({ signals, max = 3 }: { signals: UrgencySignal[]; max?: number }) {
    if (!signals || signals.length === 0) return null

    const displayed = signals.slice(0, max)
    const remaining = signals.length - max

    return (
        <div className="flex flex-wrap gap-1">
            {displayed.map((signal, i) => (
                <UrgencyTag key={`${signal.label}-${i}`} signal={signal} />
            ))}
            {remaining > 0 && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-[11px] text-slate-500 dark:text-slate-400">
                    +{remaining} more
                </span>
            )}
        </div>
    )
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
    const pct = Math.round(confidence * 100)
    const color =
        pct >= 80
            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10'
            : pct >= 50
              ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10'
              : 'text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-500/10'

    return (
        <span
            className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium', color)}
            title={`AI confidence: ${pct}%`}
        >
            AI {pct}%
        </span>
    )
}
