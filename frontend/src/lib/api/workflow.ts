/**
 * Workflow API Client
 * SLA management, delivery verification, what-if analysis, ML integration endpoints,
 * NLP corrections, pre-staging, and more.
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ─── Helper ─────────────────────────────────────────────
async function getAccessToken(): Promise<string> {
    try {
        const sb = getSupabaseClient()
        const sessionPromise = sb.auth.getSession()
        const timeoutPromise = new Promise<never>((_, reject) => {
            setTimeout(() => reject(new Error('Session lookup timed out')), 8000)
        })
        const { data: { session } } = await Promise.race([sessionPromise, timeoutPromise])
        if (session?.access_token) return session.access_token
    } catch {
        // fall back to cookie token below
    }

    if (typeof document !== 'undefined') {
        const tokenCookie = document.cookie
            .split('; ')
            .find((row) => row.startsWith('sb-token='))
            ?.split('=')[1]
        if (tokenCookie) return decodeURIComponent(tokenCookie)
    }

    throw new Error('Not authenticated')
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await getAccessToken()
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(options.headers as Record<string, string> ?? {}),
    }

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 20000)

    let res: Response
    try {
        res = await fetch(`${API_BASE}${path}`, {
            ...options,
            headers,
            signal: controller.signal,
        })
    } catch (error: any) {
        if (error?.name === 'AbortError') {
            throw new Error('Request timed out')
        }
        throw error
    } finally {
        clearTimeout(timeoutId)
    }

    if (!res.ok) {
        if (res.status === 401) {
            try {
                const sb = getSupabaseClient()
                const { data } = await sb.auth.refreshSession()
                if (data.session?.access_token) {
                    headers.Authorization = `Bearer ${data.session.access_token}`
                    const retry = await fetch(`${API_BASE}${path}`, { ...options, headers })
                    if (retry.ok) {
                        if (retry.status === 204) return {} as T
                        return retry.json()
                    }
                }
            } catch {
                // fall through to regular error parsing
            }
        }
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
    }
    if (res.status === 204) return {} as T
    return res.json()
}

// ─── Types ──────────────────────────────────────────────

export interface SLAConfig {
    approved_sla_hours: number
    assigned_sla_hours: number
    in_progress_sla_hours: number
    sla_enabled: boolean
}

export interface SLAViolation {
    request_id: string
    type: string
    sla_hours: number
    hours_elapsed: number
    priority: string
    resource_type: string
    status: string
    assigned_to: string | null
    escalated: boolean
}

export interface SLAViolationsResponse {
    violations: SLAViolation[]
    total: number
    settings: SLAConfig
    total_active_requests: number
    compliant_active_requests: number
    at_risk_count: number
    context_summary?: {
        tracked_statuses: string[]
        live_breaches: number
        requests_at_risk: number
    }
}

export interface LiveDataSummary {
    active_request_count: number
    urgent_request_count: number
    victims_impacted: number
    unique_victims?: number
    requested_resource_units: number
    available_resource_units: number
    availability_pct: number
    active_disaster_count?: number
    responders_considered?: number
    zones_with_live_requests?: number
}

export interface DeliveryConfirmation {
    confirmation_code: string
    rating?: number
    feedback?: string
    photo_url?: string
}

export interface WhatIfQuery {
    disaster_id?: string
    intervention_variable: string
    current_value: number
    proposed_value: number
    outcome_variable?: string
}

export interface WhatIfResult {
    intervention: { variable: string; from: number; to: number }
    outcome: string
    original_value: number
    counterfactual_value: number
    difference: number
    confidence_interval: [number, number]
    explanation: string
    disaster_id?: string
    summary?: LiveDataSummary
    derived_from?: string
}

export interface WhatIfContextResponse {
    disaster_id?: string
    observation: Record<string, number | string>
    summary: LiveDataSummary
    derived_from: string
}

export interface TopInterventionsResponse {
    interventions: Array<{
        variable: string
        current_value: number
        proposed_value: number
        estimated_reduction?: number
    }>
    outcome_variable: string
    summary?: LiveDataSummary
    derived_from?: string
}

export interface NGORecommendation {
    ngo_id: string
    ngo_name: string
    distance_km: number | null
    completed_requests: number
    available_stock: number
    match_score: number
}

export interface ForecastHorizon {
    horizon: string
    predicted_severity: string
    lower_bound: string
    upper_bound: string
}

export interface HeatmapData {
    center: { latitude: number; longitude: number }
    radius_km: number
    horizons: Record<string, { grid: number[][]; x_range: number[]; y_range: number[]; learned_physics: any }>
    model: string
}

export interface RequestEvent {
    id: string
    entity_type: string
    entity_id: string
    event_type: string
    data: any
    actor_id: string | null
    timestamp: string
}

// ─── SLA APIs ───────────────────────────────────────────

export async function getSLAConfig(): Promise<SLAConfig> {
    return apiFetch<SLAConfig>('/api/workflow/sla/config')
}

export async function updateSLAConfig(config: Partial<SLAConfig>): Promise<SLAConfig> {
    return apiFetch<SLAConfig>('/api/workflow/sla/config', {
        method: 'PUT',
        body: JSON.stringify(config),
    })
}

export async function getSLAViolations(): Promise<SLAViolationsResponse> {
    return apiFetch<SLAViolationsResponse>('/api/workflow/sla/violations')
}

export async function getSLAHistory(days: number = 30): Promise<{
    chart_data: Array<{
        date: string
        violations: number
        avg_response_time: number
        total_requests: number
    }>
    summary: {
        total_violations: number
        avg_violations_per_day: number
        avg_response_time: number
        total_requests: number
        days_analyzed: number
    }
    sla_settings: SLAConfig
    date_range: {
        start: string
        end: string
        days: number
    }
}> {
    return apiFetch(`/api/workflow/sla/history?days=${days}`)
}

// ─── Delivery Verification ──────────────────────────────

export async function confirmDelivery(requestId: string, data: DeliveryConfirmation) {
    return apiFetch(`/api/workflow/requests/${requestId}/confirm-delivery`, {
        method: 'POST',
        body: JSON.stringify(data),
    })
}

// ─── Disaster Demand/Supply ─────────────────────────────

export async function getDisasterDemandSupply(disasterId: string) {
    return apiFetch(`/api/workflow/disasters/${disasterId}/demand-supply`)
}

// ─── Pre-staging ────────────────────────────────────────

export async function getPrestagingRecommendations() {
    return apiFetch('/api/workflow/prestaging/recommendations')
}

// ─── Event History ──────────────────────────────────────

export async function getRequestEvents(requestId: string): Promise<{ events: RequestEvent[]; total: number }> {
    return apiFetch(`/api/workflow/requests/${requestId}/events`)
}

// ─── What-If Analysis ───────────────────────────────────

export async function runWhatIfAnalysis(query: WhatIfQuery): Promise<WhatIfResult> {
    return apiFetch<WhatIfResult>('/api/workflow/what-if', {
        method: 'POST',
        body: JSON.stringify(query),
    })
}

export async function getWhatIfContext(disasterId?: string): Promise<WhatIfContextResponse> {
    const query = disasterId ? `?disaster_id=${encodeURIComponent(disasterId)}` : ''
    return apiFetch<WhatIfContextResponse>(`/api/workflow/what-if/context${query}`)
}

export async function getTopInterventions(outcomeVariable?: string, k?: number, disasterId?: string): Promise<TopInterventionsResponse> {
    return apiFetch<TopInterventionsResponse>('/api/workflow/what-if/top-interventions', {
        method: 'POST',
        body: JSON.stringify({ outcome_variable: outcomeVariable || 'casualties', k: k || 5, disaster_id: disasterId }),
    })
}

// ─── GAT NGO Recommendations ───────────────────────────

export async function getRecommendedNGOs(requestId: string): Promise<{ recommendations: NGORecommendation[]; method: string }> {
    return apiFetch(`/api/workflow/requests/${requestId}/recommended-ngo`)
}

// ─── RL Reward Feedback ─────────────────────────────────

export async function submitRLReward(data: {
    allocation_id: string
    actual_response_hours: number
    coverage_achieved: number
    actual_distance_km: number
}) {
    return apiFetch('/api/workflow/rl/reward-feedback', {
        method: 'POST',
        body: JSON.stringify(data),
    })
}

// ─── TFT Forecast ───────────────────────────────────────

export async function getMultiHorizonForecast(features?: Record<string, any>, disasterId?: string): Promise<{
    horizons: ForecastHorizon[]
    current_severity: string
    confidence: number
    model_version: string
    summary?: LiveDataSummary
    derived_from?: string
}> {
    return apiFetch('/api/workflow/forecast/multi-horizon', {
        method: 'POST',
        body: JSON.stringify({ features: features || {}, disaster_id: disasterId }),
    })
}

// ─── PINN Heatmap ───────────────────────────────────────

export async function getSpreadHeatmap(params: {
    latitude: number
    longitude: number
    radius_km?: number
    horizons?: number[]
    resolution?: number
}): Promise<HeatmapData> {
    return apiFetch<HeatmapData>('/api/workflow/spread/heatmap', {
        method: 'POST',
        body: JSON.stringify(params),
    })
}

// ─── NLP Active Learning ────────────────────────────────

export async function recordNLPCorrection(data: {
    request_id: string
    predicted_priority: string
    corrected_priority: string
    description?: string
}) {
    return apiFetch('/api/workflow/nlp/correction', {
        method: 'POST',
        body: JSON.stringify(data),
    })
}

export async function getNLPCorrections(unusedOnly?: boolean) {
    const params = unusedOnly !== undefined ? `?unused_only=${unusedOnly}` : ''
    return apiFetch(`/api/workflow/nlp/corrections${params}`)
}

export async function triggerNLPRetrain() {
    return apiFetch('/api/workflow/nlp/retrain', { method: 'POST' })
}

// ─── Federated Learning ─────────────────────────────────

export async function getFederatedPrivacyMetrics() {
    return apiFetch('/api/workflow/federated/privacy-metrics')
}

// (removed - not applicable to PostgreSQL)

export async function getIndexSuggestions() {
    return apiFetch('/api/workflow/indexes/suggestions')
}
