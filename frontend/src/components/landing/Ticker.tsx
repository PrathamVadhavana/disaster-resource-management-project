'use client';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const FALLBACK = [
    "� Loading live disaster feed from USGS, GDACS & ReliefWeb…",
    "🌍 Real-time disaster alerts updating every 5 minutes",
    "📡 Connecting to global monitoring networks…",
];

const TYPE_EMOJI: Record<string, string> = {
    earthquake: '🌍', flood: '🌊', cyclone: '🌀', wildfire: '🔥',
    volcano: '🌋', tsunami: '🌊', drought: '☀️', storm: '⛈️',
    landslide: '⛰️', iceberg: '🧊', default: '🚨',
};

const SEV_DOT: Record<string, string> = {
    critical: 'bg-red-500', high: 'bg-orange-500', medium: 'bg-amber-500', low: 'bg-green-500',
};

export default function Ticker() {
    const [items, setItems] = useState<string[]>(FALLBACK);

    useEffect(() => {
        const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${API}/api/global-disasters/?limit=20`)
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
                if (data?.events?.length) {
                    setItems(
                        data.events.slice(0, 15).map((e: any) => {
                            const emoji = TYPE_EMOJI[e.type] || TYPE_EMOJI.default;
                            const loc = e.location_name ? ` — ${e.location_name}` : '';
                            const mag = e.magnitude ? ` (M${e.magnitude})` : '';
                            return `${emoji} ${e.title}${mag}${loc}`;
                        })
                    );
                }
            })
            .catch(() => {/* keep fallback */});
    }, []);

    return (
        <div className="w-full bg-[#1e293b] border-y border-slate-700 overflow-hidden py-3">
            <div className="flex whitespace-nowrap">
                <motion.div
                    className="flex gap-16"
                    animate={{ x: "-100%" }}
                    transition={{
                        repeat: Infinity,
                        ease: "linear",
                        duration: Math.max(75, items.length * 7),
                    }}
                >
                    {[...items, ...items, ...items].map((stat, i) => (
                        <div key={i} className="flex items-center gap-2 text-slate-300 font-mono text-sm">
                            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                            {stat}
                        </div>
                    ))}
                </motion.div>
            </div>
        </div>
    );
}
