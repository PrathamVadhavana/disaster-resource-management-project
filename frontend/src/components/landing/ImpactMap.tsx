'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Incident {
    id: string;
    title: string;
    severity: string;
}

function severityType(severity: string): 'critical' | 'warning' | 'safe' {
    if (severity === 'critical' || severity === 'high') return 'critical';
    if (severity === 'medium') return 'warning';
    return 'safe';
}

function posFromId(id: string, idx: number) {
    const hash = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const x = 12 + ((hash * 41 + idx * 19) % 70);
    const y = 12 + ((hash * 59 + idx * 29) % 65);
    return { x: `${x}%`, y: `${y}%` };
}

export default function ImpactMap() {
    const [incidents, setIncidents] = useState<Incident[]>([]);

    useEffect(() => {
        fetch(`${API}/api/admin/recent-incidents`)
            .then(r => r.ok ? r.json() : [])
            .then(setIncidents)
            .catch(() => setIncidents([]));
    }, []);

    const critCount = incidents.filter(i => severityType(i.severity) === 'critical').length;

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

            {/* Pulsing Hotspots — driven by real active incidents */}
            {incidents.length > 0 ? (
                incidents.slice(0, 5).map((inc, i) => {
                    const pos = posFromId(inc.id, i);
                    return <Hotspot key={inc.id} x={pos.x} y={pos.y} type={severityType(inc.severity)} />;
                })
            ) : (
                <Hotspot x="50%" y="50%" type="safe" />
            )}

            {/* Overlay Card */}
            <div className="absolute top-4 left-4 bg-slate-900/90 backdrop-blur p-4 rounded-xl border border-slate-700 max-w-xs z-10">
                <h3 className="text-white font-bold text-sm mb-1">Active Relief Zones</h3>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span className={`w-2 h-2 rounded-full ${critCount > 0 ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`} />
                    {critCount > 0
                        ? `${critCount} zone${critCount > 1 ? 's' : ''} — Critical Aid Required`
                        : incidents.length > 0
                            ? `${incidents.length} active zone${incidents.length > 1 ? 's' : ''} monitored`
                            : 'No active incidents'}
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
