'use client';

import { motion } from 'framer-motion';
import { MapPin, Navigation, AlertTriangle } from 'lucide-react';
import Image from 'next/image';
import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Incident {
    id: string;
    title: string;
    type: string;
    severity: string;
    description: string;
    created_at: string;
    location_name: string;
    latitude: number | null;
    longitude: number | null;
}

/* Map severity to color */
function severityColor(severity: string) {
    switch (severity) {
        case 'critical': return 'bg-red-500';
        case 'high': return 'bg-orange-500';
        case 'medium': return 'bg-blue-500';
        default: return 'bg-emerald-500';
    }
}

/* Deterministic position from incident id (avoids overlap) */
function posFromId(id: string, idx: number) {
    const hash = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const x = 15 + ((hash * 37 + idx * 23) % 65);   // 15-80%
    const y = 15 + ((hash * 53 + idx * 31) % 55);    // 15-70%
    return { x: `${x}%`, y: `${y}%` };
}

export default function MapPreviewCard() {
    const [incidents, setIncidents] = useState<Incident[]>([]);

    useEffect(() => {
        fetch(`${API}/api/admin/recent-incidents`)
            .then(r => r.ok ? r.json() : [])
            .then(setIncidents)
            .catch(() => setIncidents([]));
    }, []);

    const latest = incidents[0];

    return (
        <div className="relative w-full h-[500px] rounded-3xl overflow-hidden shadow-2xl border border-slate-700 group">
            {/* Background Static Map */}
            <div className="absolute inset-0">
                <Image
                    src="https://images.unsplash.com/photo-1524661135-423995f22d0b?auto=format&fit=crop&q=80&w=1000"
                    alt="Live Relief Map"
                    fill
                    className="object-cover opacity-60 group-hover:scale-105 transition-transform duration-700"
                />
                {/* Map Overlay Gradient */}
                <div className="absolute inset-0 bg-[#0F172A]/40 mix-blend-multiply" />
            </div>

            {/* Grid Overlay */}
            <div className="absolute inset-0 opacity-20 pointer-events-none"
                style={{ backgroundImage: 'radial-gradient(circle, #3b82f6 1px, transparent 1px)', backgroundSize: '30px 30px' }}
            />

            {/* Pulsing Hotspots — driven by real active incidents */}
            {incidents.length > 0 ? (
                incidents.slice(0, 5).map((inc, i) => {
                    const pos = posFromId(inc.id, i);
                    return (
                        <Hotspot
                            key={inc.id}
                            x={pos.x}
                            y={pos.y}
                            label={inc.title}
                            color={severityColor(inc.severity)}
                            delay={i * 0.5}
                        />
                    );
                })
            ) : (
                /* No incidents — show a single "all clear" dot */
                <Hotspot x="50%" y="45%" label="No active incidents" color="bg-emerald-500" delay={0} />
            )}

            {/* Floating UI Elements */}
            <div className="absolute top-6 left-6 right-6 flex items-start justify-between">
                <div className="glass px-4 py-2 rounded-xl flex items-center gap-3">
                    <div className="relative">
                        <span className="absolute inline-flex h-3 w-3 rounded-full bg-green-400 opacity-75 animate-ping"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                    </div>
                    <div>
                        <p className="text-xs text-slate-400 uppercase tracking-wider font-bold">Live Operations</p>
                        <p className="text-white font-mono text-sm">
                            {incidents.length > 0
                                ? `${incidents.length} active incident${incidents.length > 1 ? 's' : ''}`
                                : 'All clear'}
                        </p>
                    </div>
                </div>

                <div className="glass p-2 rounded-full hover:bg-white/10 transition-colors cursor-pointer">
                    <Navigation className="w-5 h-5 text-blue-400" />
                </div>
            </div>

            <div className="absolute bottom-6 left-6 right-6">
                {latest ? (
                    <div className="glass p-4 rounded-2xl border-l-4 border-blue-500">
                        <div className="flex items-center gap-3 mb-2">
                            <MapPin className="w-4 h-4 text-blue-400" />
                            <span className="text-xs font-bold text-blue-400 uppercase">Latest Incident</span>
                        </div>
                        <p className="text-white font-medium text-sm line-clamp-2">
                            {latest.title}{latest.location_name && latest.location_name !== 'Unknown' ? ` — ${latest.location_name}` : ''}
                            {latest.description ? `. ${latest.description.slice(0, 120)}` : ''}
                        </p>
                    </div>
                ) : (
                    <div className="glass p-4 rounded-2xl border-l-4 border-emerald-500">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangle className="w-4 h-4 text-emerald-400" />
                            <span className="text-xs font-bold text-emerald-400 uppercase">Status</span>
                        </div>
                        <p className="text-white font-medium text-sm">No active incidents at this time. Monitoring continues.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

function Hotspot({ x, y, label, color, delay }: { x: string; y: string; label: string; color: string; delay: number }) {
    return (
        <motion.div
            className="absolute group/point"
            style={{ left: x, top: y }}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay, duration: 0.5 }}
        >
            <div className="relative -ml-3 -mt-3 w-6 h-6 flex items-center justify-center cursor-pointer">
                <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${color}`} />
                <span className={`relative inline-flex rounded-full h-3 w-3 ${color} border-2 border-slate-900`} />
            </div>

            {/* Tooltip */}
            <div className="absolute left-1/2 bottom-full mb-2 -translate-x-1/2 glass px-3 py-1 rounded-lg opacity-0 group-hover/point:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                <span className="text-xs font-bold text-white">{label}</span>
            </div>
        </motion.div>
    )
}
