'use client';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Droplets, Pill, Home, Battery, AlertTriangle, Flame, CloudRain, Mountain, Loader2 } from 'lucide-react';

const TYPE_MAP: Record<string, { icon: typeof AlertTriangle; color: string; bg: string }> = {
    earthquake: { icon: Mountain, color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' },
    flood: { icon: CloudRain, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20' },
    wildfire: { icon: Flame, color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-50 dark:bg-orange-900/20' },
    cyclone: { icon: CloudRain, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20' },
    volcano: { icon: Mountain, color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' },
    default: { icon: AlertTriangle, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20' },
};

const URGENCY_BADGE: Record<string, { bg: string; text: string }> = {
    critical: { bg: 'bg-red-100 dark:bg-red-500/20', text: 'text-red-600 dark:text-red-400' },
    high: { bg: 'bg-orange-100 dark:bg-orange-500/20', text: 'text-orange-600 dark:text-orange-400' },
    medium: { bg: 'bg-amber-100 dark:bg-amber-500/20', text: 'text-amber-600 dark:text-amber-400' },
    low: { bg: 'bg-green-100 dark:bg-green-500/20', text: 'text-green-600 dark:text-green-400' },
};

const FALLBACK = [
    { type: 'Loading', amount: '—', location: 'Connecting to APIs…', urgency: 'Medium', icon: Loader2, color: 'text-slate-500 dark:text-slate-400', bg: 'bg-slate-50 dark:bg-slate-900/20' },
];

interface LiveEvent {
    title: string
    type: string
    severity: string
    location_name?: string
    magnitude?: number
    source: string
}

export default function UrgentNeeds() {
    const [events, setEvents] = useState<LiveEvent[] | null>(null);

    useEffect(() => {
        const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${API}/api/global-disasters/?min_severity=6&limit=10`)
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
                if (data?.events?.length) setEvents(data.events);
            })
            .catch(() => {/* keep fallback */});
    }, []);

    // Fallback to static data
    if (!events) {
        return (
            <div className="w-full overflow-hidden py-8">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-6 px-4">Live Urgent Requests</h3>
                <motion.div
                    className="flex gap-4 px-4"
                    drag="x"
                    dragConstraints={{ right: 0, left: -400 }}
                >
                    {FALLBACK.map((need, i) => (
                        <div key={i} className="min-w-[220px] bg-white dark:bg-slate-800/50 p-5 rounded-xl border border-slate-200 dark:border-slate-700 flex flex-col gap-4 group hover:border-blue-500/50 transition-colors shadow-sm cursor-grab active:cursor-grabbing">
                            <div className="flex justify-between items-start">
                                <div className={`p-2 rounded-lg ${need.bg} ${need.color}`}>
                                    <need.icon className="w-5 h-5" />
                                </div>
                                <span className="text-[10px] font-bold px-2 py-1 rounded bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-400 uppercase border border-red-200 dark:border-transparent">{need.urgency}</span>
                            </div>
                            <div>
                                <h4 className="text-slate-900 dark:text-white font-bold text-lg">{need.amount} {need.type}</h4>
                                <p className="text-slate-500 dark:text-slate-400 text-xs mt-1 font-medium">Needed at {need.location}</p>
                            </div>
                        </div>
                    ))}
                </motion.div>
            </div>
        );
    }

    return (
        <div className="w-full overflow-hidden py-8">
            <div className="flex items-center gap-3 mb-6 px-4">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">Live Global Disasters</h3>
                <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-[10px] font-bold uppercase">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> Real-time
                </span>
            </div>
            <motion.div
                className="flex gap-4 px-4"
                drag="x"
                dragConstraints={{ right: 0, left: -(events.length * 240 - 600) }}
            >
                {events.map((evt, i) => {
                    const tm = TYPE_MAP[evt.type] || TYPE_MAP.default;
                    const ub = URGENCY_BADGE[evt.severity] || URGENCY_BADGE.medium;
                    const Icon = tm.icon;
                    return (
                        <div key={i} className="min-w-[250px] bg-white dark:bg-slate-800/50 p-5 rounded-xl border border-slate-200 dark:border-slate-700 flex flex-col gap-4 group hover:border-blue-500/50 transition-colors shadow-sm cursor-grab active:cursor-grabbing">
                            <div className="flex justify-between items-start">
                                <div className={`p-2 rounded-lg ${tm.bg} ${tm.color}`}>
                                    <Icon className="w-5 h-5" />
                                </div>
                                <span className={`text-[10px] font-bold px-2 py-1 rounded uppercase border border-transparent ${ub.bg} ${ub.text}`}>
                                    {evt.severity}
                                </span>
                            </div>
                            <div>
                                <h4 className="text-slate-900 dark:text-white font-bold text-sm leading-snug line-clamp-2">{evt.title}</h4>
                                <p className="text-slate-500 dark:text-slate-400 text-xs mt-1.5 font-medium">
                                    {evt.location_name || evt.type}{evt.magnitude ? ` · M${evt.magnitude}` : ''}
                                </p>
                                <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-wider font-semibold">{evt.source}</p>
                            </div>
                        </div>
                    );
                })}
            </motion.div>
        </div>
    );
}
