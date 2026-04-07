'use client'

import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, Marker } from 'react-leaflet'
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

interface Resource {
    id: string
    name?: string
    type?: string
    status?: string
    quantity?: number
    unit?: string
    latitude?: number
    longitude?: number
    disaster_id?: string
}

interface DisasterMapProps {
    disasters: Disaster[]
    resources?: Resource[]
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

const RESOURCE_TYPE_HEX: Record<string, string> = {
    food: '#22c55e',
    water: '#3b82f6',
    medical: '#ef4444',
    shelter: '#a855f7',
    clothing: '#f59e0b',
    equipment: '#6366f1',
    transport: '#14b8a6',
    personnel: '#ec4899',
}

/** Auto-fit the map bounds when disaster data changes */
function FitBounds({ disasters, resources }: { disasters: Disaster[]; resources?: Resource[] }) {
    const map = useMap()

    useEffect(() => {
        const points: [number, number][] = []
        disasters.forEach((d) => points.push([d.latitude, d.longitude]))
        resources?.forEach((r) => {
            if (r.latitude != null && r.longitude != null) {
                points.push([r.latitude, r.longitude])
            }
        })
        if (points.length === 0) return
        const bounds = L.latLngBounds(points)
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
    }, [disasters, resources, map])

    return null
}

/** Create a custom diamond-shaped SVG icon for resources */
function createResourceIcon(color: string) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
        <rect x="4" y="4" width="16" height="16" rx="3" fill="${color}" fill-opacity="0.8" stroke="white" stroke-width="2"/>
        <rect x="8" y="8" width="8" height="8" rx="1.5" fill="white" fill-opacity="0.6"/>
    </svg>`
    return L.divIcon({
        html: svg,
        className: 'resource-marker-icon',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -12],
    })
}

export default function DisasterMap({ disasters, resources = [] }: DisasterMapProps) {
    const defaultCenter: [number, number] = [20, 0]
    const defaultZoom = 2
    const deployedResources = resources.filter(
        (r) => r.latitude != null && r.longitude != null && (r.status === 'allocated' || r.status === 'in_use' || r.status === 'deployed')
    )

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
                .resource-marker-icon {
                    background: transparent !important;
                    border: none !important;
                }
                .map-legend {
                    background: rgba(15,23,42,0.9);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 11px;
                    color: #94a3b8;
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
                {(disasters.length > 0 || deployedResources.length > 0) && (
                    <FitBounds disasters={disasters} resources={deployedResources} />
                )}

                {/* Disaster zone markers */}
                {disasters.map((d) => {
                    const color = SEVERITY_HEX[d.severity || 'low'] || '#94a3b8'
                    const radius = SEVERITY_RADIUS[d.severity || 'low'] || 7
                    return (
                        <CircleMarker
                            key={`disaster-${d.id}`}
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

                {/* Deployed resource markers */}
                {deployedResources.map((r) => {
                    const resourceType = (r.type || 'equipment').toLowerCase()
                    const color = RESOURCE_TYPE_HEX[resourceType] || '#6366f1'
                    return (
                        <Marker
                            key={`resource-${r.id}`}
                            position={[r.latitude!, r.longitude!]}
                            icon={createResourceIcon(color)}
                        >
                            <Popup>
                                <div className="space-y-1.5 min-w-[160px]">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wide"
                                            style={{ backgroundColor: `${color}20`, color }}>
                                            Resource
                                        </span>
                                    </div>
                                    <p className="font-semibold text-white text-sm leading-tight">{r.name || 'Unnamed Resource'}</p>
                                    <div className="flex items-center gap-2 text-xs">
                                        <span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: color }} />
                                        <span className="capitalize text-slate-400">{resourceType}</span>
                                        <span className="text-slate-500">•</span>
                                        <span className="text-slate-400 capitalize">{r.status}</span>
                                    </div>
                                    {r.quantity != null && (
                                        <p className="text-xs text-slate-400">
                                            📦 {r.quantity} {r.unit || 'units'}
                                        </p>
                                    )}
                                    <p className="text-[11px] text-slate-500">
                                        {r.latitude!.toFixed(4)}, {r.longitude!.toFixed(4)}
                                    </p>
                                </div>
                            </Popup>
                        </Marker>
                    )
                })}
            </MapContainer>
            </div>
        </div>
    )
}
