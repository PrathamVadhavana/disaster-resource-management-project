'use client';
import { motion } from 'framer-motion';

const STATS = [
    "🚨 Flood Alert in District 9 - 500+ evacuated",
    "📦 2,000 Food Packets Distributed in Zone A",
    "🏥 Medical Team deployed to Sector 4",
    "💰 $50k raised for Emergency Shelters",
    "🤝 150 New Volunteers registered today",
];

export default function Ticker() {
    return (
        <div className="w-full bg-[#1e293b] border-y border-slate-700 overflow-hidden py-3">
            <div className="flex whitespace-nowrap">
                <motion.div
                    className="flex gap-16"
                    animate={{ x: "-100%" }}
                    transition={{
                        repeat: Infinity,
                        ease: "linear",
                        duration: 20,
                    }}
                >
                    {[...STATS, ...STATS, ...STATS].map((stat, i) => (
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
