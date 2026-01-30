'use client';

import { motion } from 'framer-motion';

export default function ImpactMap() {
    return (
        <div className="relative w-full h-[500px] bg-slate-800/50 rounded-3xl overflow-hidden border border-slate-700 backdrop-blur-sm group">
            {/* Abstract Map Background */}
            <div className="absolute inset-0 opacity-30 select-none pointer-events-none">
                <svg className="w-full h-full text-slate-600" fill="currentColor">
                    {/* Simplified dots/grid pattern as map abstraction */}
                    <pattern id="grid" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
                        <circle cx="2" cy="2" r="1" />
                    </pattern>
                    <rect width="100%" height="100%" fill="url(#grid)" />
                </svg>
            </div>

            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <p className="text-slate-500 font-mono text-lg tracking-widest uppercase opacity-0 group-hover:opacity-100 transition-opacity">
                    Live Geospatial Data Layer
                </p>
            </div>

            {/* Pulsing Hotspots */}
            <Hotspot x="20%" y="30%" type="critical" />
            <Hotspot x="50%" y="50%" type="warning" />
            <Hotspot x="70%" y="20%" type="safe" />
            <Hotspot x="40%" y="80%" type="critical" />

            {/* Overlay Card */}
            <div className="absolute top-4 left-4 bg-slate-900/90 backdrop-blur p-4 rounded-xl border border-slate-700 max-w-xs z-10">
                <h3 className="text-white font-bold text-sm mb-1">Active Relief Zones</h3>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    Critical Aid Required
                </div>
            </div>
        </div>
    );
}

function Hotspot({ x, y, type }: { x: string; y: string; type: 'critical' | 'warning' | 'safe' }) {
    const colors = {
        critical: 'bg-red-500',
        warning: 'bg-orange-500',
        safe: 'bg-emerald-500'
    }
    const color = colors[type];

    return (
        <div className="absolute" style={{ left: x, top: y }}>
            <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${color}`} />
            <span className={`relative inline-flex rounded-full h-3 w-3 ${color}`} />
        </div>
    )
}
