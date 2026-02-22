'use client'

import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface Disaster {
    id: string
    title?: string
    type?: string
    severity?: string
    latitude: number
    longitude: number
    location_name?: string
    location_city?: string
    location_country?: string
    affected_population?: number
}

interface DisasterMapProps {
    disasters: Disaster[]
}

const SEVERITY_HEX: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#f59e0b',
    low: '#22c55e',
}

const SEVERITY_RADIUS: Record<string, number> = {
    critical: 12,
    high: 10,
    medium: 8,
    low: 6,
}

/** Auto-fit the map bounds when disaster data changes */
function FitBounds({ disasters }: { disasters: Disaster[] }) {
    const map = useMap()

    useEffect(() => {
        if (disasters.length === 0) return
        const bounds = L.latLngBounds(disasters.map((d) => [d.latitude, d.longitude]))
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
    }, [disasters, map])

    return null
}

export default function DisasterMap({ disasters }: DisasterMapProps) {
    const defaultCenter: [number, number] = [20, 0]
    const defaultZoom = 2

    return (
        <div className="rounded-2xl border border-slate-200 dark:border-white/10 overflow-hidden" style={{ height: 500 }}>
            <style dangerouslySetInnerHTML={{ __html: `
                .disaster-map .leaflet-container {
                    height: 100%;
                    width: 100%;
                    background: #1e293b;
                }
                .disaster-map .leaflet-popup-content-wrapper {
                    background: #0f172a;
                    color: #e2e8f0;
                    border-radius: 12px;
                    border: 1px solid rgba(255,255,255,0.1);
                    box-shadow: 0 20px 40px rgba(0,0,0,0.4);
                }
                .disaster-map .leaflet-popup-content {
                    margin: 12px 14px;
                    font-size: 13px;
                    line-height: 1.5;
                }
                .disaster-map .leaflet-popup-tip {
                    background: #0f172a;
                    border: 1px solid rgba(255,255,255,0.1);
                }
                .disaster-map .leaflet-control-zoom a {
                    background: #1e293b !important;
                    color: #94a3b8 !important;
                    border-color: rgba(255,255,255,0.1) !important;
                }
                .disaster-map .leaflet-control-zoom a:hover {
                    background: #334155 !important;
                    color: #fff !important;
                }
                .disaster-map .leaflet-control-attribution {
                    background: rgba(15,23,42,0.8) !important;
                    color: #64748b !important;
                    font-size: 10px !important;
                }
                .disaster-map .leaflet-control-attribution a {
                    color: #64748b !important;
                }
            `}} />
            <div className="disaster-map h-full w-full">
            <MapContainer
                center={defaultCenter}
                zoom={defaultZoom}
                scrollWheelZoom={true}
                className="h-full w-full"
                style={{ height: '100%', width: '100%' }}
            >
                <TileLayer
                    attribution='&copy; <a href="https://carto.com/">CARTO</a>'
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                />
                {disasters.length > 0 && <FitBounds disasters={disasters} />}
                {disasters.map((d) => {
                    const color = SEVERITY_HEX[d.severity || 'low'] || '#94a3b8'
                    const radius = SEVERITY_RADIUS[d.severity || 'low'] || 7
                    return (
                        <CircleMarker
                            key={d.id}
                            center={[d.latitude, d.longitude]}
                            radius={radius}
                            pathOptions={{
                                color,
                                fillColor: color,
                                fillOpacity: 0.35,
                                weight: 2,
                                opacity: 0.9,
                            }}
                        >
                            <Popup>
                                <div className="space-y-1.5 min-w-[180px]">
                                    <p className="font-semibold text-white text-sm leading-tight">{d.title || 'Untitled'}</p>
                                    <div className="flex items-center gap-2">
                                        <span
                                            className="inline-block w-2 h-2 rounded-full"
                                            style={{ backgroundColor: color }}
                                        />
                                        <span className="text-xs capitalize" style={{ color }}>
                                            {d.severity}
                                        </span>
                                        <span className="text-slate-500 text-xs">•</span>
                                        <span className="text-xs text-slate-400 capitalize">{d.type}</span>
                                    </div>
                                    {(d.location_name || d.location_city) && (
                                        <p className="text-xs text-slate-400">
                                            📍 {d.location_name || d.location_city}
                                            {d.location_country && `, ${d.location_country}`}
                                        </p>
                                    )}
                                    <p className="text-[11px] text-slate-500">
                                        {d.latitude.toFixed(4)}, {d.longitude.toFixed(4)}
                                    </p>
                                    {d.affected_population != null && d.affected_population > 0 && (
                                        <p className="text-xs text-slate-400">
                                            👥 {d.affected_population.toLocaleString()} affected
                                        </p>
                                    )}
                                </div>
                            </Popup>
                        </CircleMarker>
                    )
                })}
            </MapContainer>
            </div>
        </div>
    )
}
