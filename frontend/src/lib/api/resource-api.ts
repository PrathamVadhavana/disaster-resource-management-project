/**
 * Resource API — routes through the FastAPI backend.
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface AvailableResource {
  resource_id: string
  provider_id: string
  provider_role: string
  category: string
  title: string
  description: string | null
  total_quantity: number
  claimed_quantity: number
  address_text: string
  location_lat: number | null
  location_long: number | null
  expiry_at: string | null
  is_active: boolean
  status: string
  created_at: string
  location: unknown | null
}

export interface ResourceRequest {
  id: string
  user_id: string
  resource_id: string
  quantity_requested: number
  status: string
  created_at: string
  updated_at: string
  notes: string | null
  resource?: {
    title?: string
    category?: string
    address_text?: string
  } | null
}

export interface ResourceWithDetails extends AvailableResource {
  available_quantity: number
  distance_km?: number
}

async function getToken(): Promise<string | null> {
  try {
    const sb = getSupabaseClient()
    const { data: { session } } = await sb.auth.getSession()
    return session?.access_token ?? null
  } catch {
    return null
  }
}

async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail || `API error ${res.status}`)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json()
}

export const resourceApi = {
  // Fetch available resources with enhanced filtering
  async getAvailableResources(userLocation?: { lat: number; lng: number } | null) {
    try {
      const data: AvailableResource[] = await apiFetch('/api/ngo/inventory?status=available&limit=200')

      // Transform data and calculate available quantity
      const transformedResources: ResourceWithDetails[] = (data || []).map((resource: any) => ({
        ...resource,
        available_quantity: resource.total_quantity - (resource.claimed_quantity || 0)
      }))

      // If user has location, calculate distances
      if (userLocation) {
        return transformedResources.map(resource => {
          if (resource.location_lat && resource.location_long) {
            const distance = calculateDistance(
              userLocation.lat,
              userLocation.lng,
              resource.location_lat!,
              resource.location_long!
            )
            return { ...resource, distance_km: distance }
          }
          return resource
        })
      }

      return transformedResources
    } catch (err: any) {
      console.error('Error fetching resources:', err)
      throw new Error('Failed to fetch available resources. Please try again.')
    }
  },

  // Fetch user's resource requests
  async getUserRequests(userId: string) {
    try {
      const data = await apiFetch('/api/victim/requests')
      return data || []
    } catch (err: any) {
      console.error('Error fetching requests:', err)
      throw new Error('Failed to fetch your requests. Please try again.')
    }
  },

  // Submit a new resource request
  async submitRequest(userId: string, resourceId: string, quantity: number) {
    try {
      await apiFetch('/api/victim/requests', {
        method: 'POST',
        body: JSON.stringify({
          resource_id: resourceId,
          quantity_requested: quantity,
        }),
      })
      return { success: true }
    } catch (err: any) {
      console.error('Error submitting request:', err)
      throw new Error('Failed to submit resource request. Please try again.')
    }
  },

  // Cancel a resource request
  async cancelRequest(requestId: string) {
    try {
      await apiFetch(`/api/victim/requests/${requestId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'cancelled' }),
      })
      return { success: true }
    } catch (err: any) {
      console.error('Error cancelling request:', err)
      throw new Error('Failed to cancel request. Please try again.')
    }
  }
}

// Helper function to calculate distance between two coordinates
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371 // Radius of the earth in km
  const dLat = deg2rad(lat2 - lat1)
  const dLon = deg2rad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  const distance = R * c // Distance in km
  return Math.round(distance * 100) / 100
}

function deg2rad(deg: number): number {
  return deg * (Math.PI / 180)
}