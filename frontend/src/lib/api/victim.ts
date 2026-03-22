/**
 * Victim API Client
 * Communicates with FastAPI backend for victim resource requests and profile
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── Types ──────────────────────────────────────────────
export type VictimResourceType = 'Food' | 'Water' | 'Medical' | 'Shelter' | 'Clothing' | 'Financial Aid' | 'Evacuation' | 'Volunteers' | 'Custom' | 'Multiple'
export type RequestPriority = 'critical' | 'high' | 'medium' | 'low'
export type RequestStatus = 'pending' | 'approved' | 'under_review' | 'availability_submitted' | 'assigned' | 'in_progress' | 'delivered' | 'completed' | 'closed' | 'rejected'

export interface ResourceItem {
    resource_type: string
    quantity: number
    custom_name?: string | null
}

export interface ResourceRequest {
    id: string
    victim_id: string
    resource_type: VictimResourceType
    quantity: number
    items: ResourceItem[]
    description: string | null
    priority: RequestPriority
    latitude: number | null
    longitude: number | null
    address_text: string | null
    status: RequestStatus
    assigned_to: string | null
    assigned_role: string | null
    estimated_delivery: string | null
    attachments: string[]
    rejection_reason: string | null
    created_at: string
    updated_at: string
    // NLP / AI triage fields (populated by backend NLP service)
    nlp_classification?: {
        resource_types?: string[]
        recommended_priority?: string
        priority_was_escalated?: boolean
        estimated_quantity?: number | string
        confidence?: number
    } | null
    ai_confidence?: number | null
    nlp_overridden?: boolean
    urgency_signals?: Array<{ keyword: string; label: string; severity_boost: number }>
    // Fulfillment tracking
    fulfillment_pct?: number
    fulfillment_entries?: Array<{
        provider_id: string
        provider_name: string
        provider_role: string
        donation_type?: string
        amount?: number
        resource_items?: Array<{ resource_type: string; quantity: number }>
        status: string
        created_at: string
    }>
    // Delivery verification
    delivery_confirmation_code?: string
    delivery_confirmed_at?: string
    delivery_rating?: number
    delivery_feedback?: string
    // Disaster linking
    linked_disaster_id?: string
}

export interface ResourceRequestCreate {
    resource_type?: VictimResourceType
    quantity?: number
    items: ResourceItem[]
    description?: string
    priority: RequestPriority
    latitude?: number
    longitude?: number
    address_text?: string
    attachments?: string[]
    disaster_type?: string
}

export interface ResourceRequestUpdate {
    resource_type?: VictimResourceType
    quantity?: number
    items?: ResourceItem[]
    description?: string
    priority?: RequestPriority
    latitude?: number
    longitude?: number
    address_text?: string
    attachments?: string[]
}

export interface ResourceRequestListResponse {
    requests: ResourceRequest[]
    total: number
    page: number
    page_size: number
}

export interface DashboardStats {
    total_requests: number
    pending: number
    approved: number
    assigned: number
    in_progress: number
    completed: number
    rejected: number
    by_type: Record<string, number>
    by_priority: Record<string, number>
}

export interface VictimProfile {
    id: string
    email: string
    full_name: string | null
    phone: string | null
    role: string
    current_status: string | null
    needs: string[] | null
    medical_needs: string | null
    location_lat: number | null
    location_long: number | null
    // Disaster linking
    disaster_id: string | null
    disaster_name: string | null
    disaster_type: string | null
    disaster_severity: string | null
    disaster_status: string | null
    // AI insights
    ai_risk_score: number | null
    ai_recommendations: string[] | null
    created_at: string
    updated_at: string
}

export interface VictimProfileUpdate {
    full_name?: string
    phone?: string
    current_status?: string
    needs?: string[]
    medical_needs?: string
    location_lat?: number
    location_long?: number
}

export interface RequestFilters {
    status?: RequestStatus
    resource_type?: VictimResourceType
    priority?: RequestPriority
    search?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
    page?: number
    page_size?: number
}

// ─── Helper ─────────────────────────────────────────────
async function getAccessToken(): Promise<string> {
    const sb = getSupabaseClient()
    const { data: { session } } = await sb.auth.getSession()
    if (!session) {
        throw new Error('Not authenticated')
    }
    return session.access_token
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await getAccessToken()
    const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            ...options.headers,
        },
    })

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
    }

    // Handle 204 No Content
    if (res.status === 204) return {} as T

    return res.json()
}

// ─── Resource Request APIs ──────────────────────────────
export async function createResourceRequest(data: ResourceRequestCreate): Promise<ResourceRequest> {
    return apiFetch<ResourceRequest>('/api/victim/requests', {
        method: 'POST',
        body: JSON.stringify(data),
    })
}

export async function getResourceRequests(filters: RequestFilters = {}): Promise<ResourceRequestListResponse> {
    const params = new URLSearchParams()
    if (filters.status) params.set('status', filters.status)
    if (filters.resource_type) params.set('resource_type', filters.resource_type)
    if (filters.priority) params.set('priority', filters.priority)
    if (filters.search) params.set('search', filters.search)
    if (filters.sort_by) params.set('sort_by', filters.sort_by)
    if (filters.sort_order) params.set('sort_order', filters.sort_order)
    if (filters.page) params.set('page', String(filters.page))
    if (filters.page_size) params.set('page_size', String(filters.page_size))

    const qs = params.toString()
    return apiFetch<ResourceRequestListResponse>(`/api/victim/requests${qs ? `?${qs}` : ''}`)
}

export async function getResourceRequest(id: string): Promise<ResourceRequest> {
    return apiFetch<ResourceRequest>(`/api/victim/requests/${id}`)
}

export async function updateResourceRequest(id: string, data: ResourceRequestUpdate): Promise<ResourceRequest> {
    return apiFetch<ResourceRequest>(`/api/victim/requests/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    })
}

export async function deleteResourceRequest(id: string): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/api/victim/requests/${id}`, {
        method: 'DELETE',
    })
}

export async function getDashboardStats(): Promise<DashboardStats> {
    return apiFetch<DashboardStats>('/api/victim/dashboard-stats')
}

// ─── Profile APIs ───────────────────────────────────────
export async function getVictimProfile(): Promise<VictimProfile> {
    return apiFetch<VictimProfile>('/api/victim/profile')
}

export async function updateVictimProfile(data: VictimProfileUpdate): Promise<VictimProfile> {
    return apiFetch<VictimProfile>('/api/victim/profile', {
        method: 'PUT',
        body: JSON.stringify(data),
    })
}

// ─── Available Resources APIs ───────────────────────────
export interface AvailableResource {
    resource_id: string
    category: string        // 'Food' | 'Water' | 'Medical' | 'Shelter' | 'Clothes'
    resource_type: string
    title: string
    description: string | null
    total_quantity: number
    claimed_quantity: number
    remaining_quantity: number
    unit: string            // 'bags' | 'bottles' | 'kits' | 'tents' | 'sets' etc.
    address_text: string | null
}

export async function getAvailableResources(category?: string): Promise<{ resources: AvailableResource[] }> {
    const params = category ? `?category=${encodeURIComponent(category)}` : ''
    return apiFetch<{ resources: AvailableResource[] }>(`/api/victim/available-resources${params}`)
}

// ─── AI Chatbot APIs ────────────────────────────────────
export interface ChatbotResponse {
    session_id: string
    assistant_message: string
    extracted_data: {
        situation_description?: string
        resource_types?: string[]
        resource_type_scores?: Record<string, number>
        quantity?: number
        location?: string
        people_count?: number
        has_medical_needs?: boolean
        medical_details?: string
        urgency_signals?: Array<{ keyword: string; label: string; severity_boost: number }>
        recommended_priority?: string
        priority_escalated?: boolean
        confidence?: number
        // Mapped aliases used by the UI
        priority?: string
        estimated_quantity?: number
        description?: string
        address_text?: string
    } | null
    request_ready: boolean
    message_count: number
}

/**
 * Normalize the extracted_data shape returned by the backend so the
 * UI can always use `priority`, `estimated_quantity`, `description`, and
 * `address_text` consistently.
 */
function normalizeChatbotResponse(raw: ChatbotResponse): ChatbotResponse {
    if (!raw.extracted_data) return raw
    const d = { ...raw.extracted_data }
    // Map backend field names → frontend field names
    if (!d.priority && d.recommended_priority) d.priority = d.recommended_priority
    if (d.estimated_quantity == null && d.quantity != null) d.estimated_quantity = d.quantity
    if (!d.description && d.situation_description) d.description = d.situation_description
    if (!d.address_text && d.location) d.address_text = d.location
    return { ...raw, extracted_data: d }
}

export async function sendChatMessage(
    message: string,
    sessionId: string | null,
): Promise<ChatbotResponse> {
    const raw = await apiFetch<ChatbotResponse>('/api/nlp/chatbot', {
        method: 'POST',
        body: JSON.stringify({
            message,
            session_id: sessionId,
        }),
    })
    return normalizeChatbotResponse(raw)
}

export async function getChatSession(sessionId: string): Promise<Record<string, any>> {
    return apiFetch<Record<string, any>>(`/api/nlp/chatbot/${sessionId}`)
}

export async function endChatSession(sessionId: string): Promise<{ message: string }> {
    return apiFetch<{ message: string }>(`/api/nlp/chatbot/${sessionId}`, {
        method: 'DELETE',
    })
}

