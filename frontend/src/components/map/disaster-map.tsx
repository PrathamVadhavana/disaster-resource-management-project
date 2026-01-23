'use client'

import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import { Icon } from 'leaflet'
import { supabase } from '@/lib/supabase'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import 'leaflet/dist/leaflet.css'

interface Disaster {
  id: string
  title: string
  type: string
  severity: string
  locations: { latitude: number, longitude: number, name: string }
}

const createIcon = (severity: string): Icon => {
  const colors = { low: '#10B981', medium: '#F59E0B', high: '#EA580C', critical: '#DC2626' }
  const color = colors[severity as keyof typeof colors] || colors.medium
  
  return new Icon({
    iconUrl: `data:image/svg+xml,${encodeURIComponent(`
      <svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <circle cx="16" cy="16" r="12" fill="${color}" opacity="0.8"/>
        <circle cx="16" cy="16" r="8" fill="${color}"/>
      </svg>
    `)}`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16]
  })
}

export function DisasterMap() {
  const queryClient = useQueryClient()

  const { data: disasters = [], isLoading, error } = useQuery({
    queryKey: ['disasters'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('disasters')
        .select('*, locations(*)')
        .in('status', ['active', 'monitoring'])
        .order('created_at', { ascending: false })
      if (error) throw error
      return data as Disaster[]
    }
  })

  useEffect(() => {
    const channel = supabase
      .channel('disasters-changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'disasters'
      }, () => {
        queryClient.invalidateQueries({ queryKey: ['disasters'] })
      })
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [queryClient])

  if (error) return <div className="h-full flex items-center justify-center bg-red-50">Failed to load</div>
  if (isLoading) return <div className="h-full flex items-center justify-center">Loading...</div>

  return (
    <div className="h-full w-full relative">
      <MapContainer center={[20, 0]} zoom={2} scrollWheelZoom style={{height: '600px', width: '100%'}}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {disasters.filter(disaster => disaster.locations).map(disaster => (
          <Marker key={disaster.id} position={[disaster.locations.latitude, disaster.locations.longitude]} icon={createIcon(disaster.severity)}>
            <Popup>
              <div className="p-2 min-w-[200px]">
                <h3 className="font-bold text-lg mb-2">{disaster.title}</h3>
                <p><span className="font-semibold">Type:</span> {disaster.type}</p>
                <p><span className="font-semibold">Severity:</span> {disaster.severity.toUpperCase()}</p>
                <p><span className="font-semibold">Location:</span> {disaster.locations.name}</p>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <div className="absolute bottom-4 right-4 bg-white p-4 rounded-lg shadow-lg z-[1000]">
        <h4 className="font-semibold mb-2 text-sm">Severity Legend</h4>
        <div className="space-y-1 text-xs">
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-red-500" />Critical</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-orange-500" />High</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-yellow-500" />Medium</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-green-500" />Low</div>
        </div>
      </div>
    </div>
  )
}
