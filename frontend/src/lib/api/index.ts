    /**
 * Centralised API client — barrel export consumed by every dashboard module.
 *
 * Usage:  import { api } from '@/lib/api'
 *         const disasters = await api.getDisasters({ status: 'active' })
 */
import { getSupabaseClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Auth helper ──────────────────────────────────────────────────────────────

async function getAccessToken(): Promise<string | null> {
    try {
        const sb = getSupabaseClient()
        const { data } = await sb.auth.getSession()
        return data.session?.access_token || null
    } catch {
        return null
    }
}

// ── Generic fetch wrapper ────────────────────────────────────────────────────

async function apiFetch<T = any>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    const token = await getAccessToken()
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> ?? {}),
    }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
    if (!res.ok) {
        if (res.status === 401) {
            // Try refreshing the session once
            try {
                const sb = getSupabaseClient()
                const { data } = await sb.auth.refreshSession()
                if (data.session) {
                    headers['Authorization'] = `Bearer ${data.session.access_token}`
                    const retry = await fetch(`${API_BASE}${path}`, { ...options, headers })
                    if (retry.ok) {
                        if (retry.status === 204) return undefined as unknown as T
                        return retry.json()
                    }
                }
            } catch { /* refresh failed */ }
            const err = new Error('Session expired') as any
            err.status = 401
            throw err
        }
        const body = await res.json().catch(() => ({}))
        const msg = (typeof body?.detail === 'string') 
            ? body.detail 
            : `API error ${res.status}`
        const err = new Error(msg) as any
        err.status = res.status
        err.detail = body?.detail
        err.body = body
        throw err
    }
    // 204 No Content
    if (res.status === 204) return undefined as unknown as T
    return res.json()
}

function qs(params?: Record<string, any>): string {
    if (!params) return ''
    const parts = Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    return parts.length ? `?${parts.join('&')}` : ''
}

// ── API object ───────────────────────────────────────────────────────────────

export const api = {
    // ━━ Disasters ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getDisasters: (params?: { status?: string; severity?: string; type?: string; limit?: number; offset?: number; search?: string; source?: string }) =>
        apiFetch(`/api/disasters${qs(params)}`),

    getDisaster: (id: string) =>
        apiFetch(`/api/disasters/${id}`),

    createDisaster: (data: any) =>
        apiFetch('/api/disasters', { method: 'POST', body: JSON.stringify(data) }),

    updateDisaster: (id: string, data: any) =>
        apiFetch(`/api/disasters/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

    deleteDisaster: (id: string) =>
        apiFetch(`/api/disasters/${id}`, { method: 'DELETE' }),

    // ━━ Resources ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getResources: (params?: { status?: string; type?: string; limit?: number }) =>
        apiFetch(`/api/resources${qs(params)}`),

    createResource: (data: any) =>
        apiFetch('/api/resources', { method: 'POST', body: JSON.stringify(data) }),

    updateResource: (resourceId: string, data: any) =>
        apiFetch(`/api/resources/${resourceId}`, { method: 'PATCH', body: JSON.stringify(data) }),

    deleteResource: (resourceId: string) =>
        apiFetch(`/api/resources/${resourceId}`, { method: 'DELETE' }),

    // ━━ Predictions ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getPredictions: (params?: { disaster_id?: string; limit?: number }) =>
        apiFetch(`/api/predictions${qs(params)}`),

    // ━━ Ingestion / Events ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getIngestedEvents: (params?: { limit?: number; offset?: number }) =>
        apiFetch(`/api/ingestion/events${qs(params)}`),

    getWeatherObservations: (locationId?: string, limit?: number) =>
        apiFetch(`/api/ingestion/weather${qs({ location_id: locationId, limit })}`),

    startOrchestrator: () =>
        apiFetch('/api/ingestion/start', { method: 'POST' }),

    // ━━ Admin ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getUsers: () =>
        apiFetch('/api/admin/users'),

    updateUserRole: (userId: string, role: string, reason?: string) =>
        apiFetch(`/api/admin/users/${userId}/role`, { method: 'PATCH', body: JSON.stringify({ role, reason }) }),

    reviewRoleSwitchRequest: (
        userId: string,
        data: { action: 'approve' | 'reject'; requested_role: string; request_id?: string; reason?: string }
    ) =>
        apiFetch(`/api/admin/users/${userId}/role-request/review`, { method: 'POST', body: JSON.stringify(data) }),

    deleteUser: (userId: string) =>
        apiFetch(`/api/admin/users/${userId}`, { method: 'DELETE' }),

    getSettings: () =>
        apiFetch('/api/admin/settings'),

    updateSettings: (data: any) =>
        apiFetch('/api/admin/settings', { method: 'PUT', body: JSON.stringify(data) }),

    getPlatformStats: () =>
        apiFetch('/api/admin/platform-stats'),

    // ━━ Coordinator (Phase 5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Situation reports
    generateSitrep: (reportType: string = 'on_demand', generatedBy: string = 'user') =>
        apiFetch('/api/ml/sitreps/generate', { method: 'POST', body: JSON.stringify({ report_type: reportType, generated_by: generatedBy }) }),

    getSitreps: (params?: { report_type?: string; limit?: number; offset?: number }) =>
        apiFetch(`/api/ml/sitreps${qs(params)}`),

    getLatestSitrep: () =>
        apiFetch('/api/ml/sitreps/latest'),

    getSitrep: (id: string) =>
        apiFetch(`/api/ml/sitreps/${id}`),

    // Natural language queries
    askCoordinatorQuery: (query: string, userId?: string, sessionId?: string, context?: Array<{question: string, answer: string}>) =>
        apiFetch('/api/ml/query', { method: 'POST', body: JSON.stringify({ query, user_id: userId, session_id: sessionId, context }) }),

    getQueryHistory: (params?: { user_id?: string; session_id?: string; limit?: number }) =>
        apiFetch(`/api/ml/query-history${qs(params)}`),

    // Anomaly alerts
    getAnomalyAlerts: (params?: { status?: string; severity?: string; limit?: number }) =>
        apiFetch(`/api/ml/anomalies${qs(params)}`),

    runAnomalyDetection: () =>
        apiFetch('/api/ml/anomalies/run', { method: 'POST' }),

    acknowledgeAnomaly: (alertId: string, userId: string) =>
        apiFetch(`/api/ml/anomalies/${alertId}/acknowledge`, { method: 'PATCH', body: JSON.stringify({ user_id: userId }) }),

    resolveAnomaly: (alertId: string, status: string = 'resolved') =>
        apiFetch(`/api/ml/anomalies/${alertId}/resolve`, { method: 'PATCH', body: JSON.stringify({ status }) }),

    // Outcome tracking
    getAccuracySummary: () =>
        apiFetch('/api/ml/accuracy-summary'),

    getOutcomes: (params?: { disaster_id?: string; limit?: number }) =>
        apiFetch(`/api/ml/outcomes${qs(params)}`),

    autoCaptureOutcomes: () =>
        apiFetch('/api/ml/outcomes/auto-capture', { method: 'POST' }),

    getEvaluationReports: (params?: { model_type?: string; limit?: number }) =>
        apiFetch(`/api/ml/evaluation-reports${qs(params)}`),

    generateEvaluationReport: (params?: { model_type?: string; period_days?: number }) =>
        apiFetch(`/api/ml/evaluation-reports/generate${qs(params)}`, { method: 'POST' }),

    // ━━ Volunteer ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getCertifications: () =>
        apiFetch('/api/volunteer/certifications'),

    createCertification: (data: any) =>
        apiFetch('/api/volunteer/certifications', { method: 'POST', body: JSON.stringify(data) }),

    updateCertification: (id: string, data: any) =>
        apiFetch(`/api/volunteer/certifications/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

    deleteCertification: (id: string) =>
        apiFetch(`/api/volunteer/certifications/${id}`, { method: 'DELETE' }),

    getVolunteerProfile: () =>
        apiFetch('/api/volunteer/profile'),

    updateVolunteerProfile: (data: any) =>
        apiFetch('/api/volunteer/profile', { method: 'PUT', body: JSON.stringify(data) }),

    getVolunteerStats: () =>
        apiFetch('/api/volunteer/dashboard-stats'),

    getActiveDeployment: () =>
        apiFetch('/api/volunteer/ops/active'),

    getVolunteerAvailableAssignments: () =>
        apiFetch('/api/volunteer/assignments/available'),

    checkInVolunteer: (data: { disaster_id: string; task_description: string; latitude?: number; longitude?: number }) =>
        apiFetch('/api/volunteer/ops/check-in', { method: 'POST', body: JSON.stringify(data) }),

    checkOutVolunteer: (opId: string, data: { notes?: string }) =>
        apiFetch(`/api/volunteer/ops/${opId}/check-out`, { method: 'POST', body: JSON.stringify(data) }),

    // ━━ Donor ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getDonations: (params?: { status?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/donor/donations${qs(params)}`),

    getDonationReceipt: (id: string) =>
        apiFetch(`/api/donor/donations/${id}/receipt`),

    getTaxCertificatePdf: async (id: string): Promise<Blob> => {
        const token = await getAccessToken()
        const headers: Record<string, string> = {}
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch(`${API_BASE}/api/donor/donations/${id}/tax-certificate`, { headers })
        if (!res.ok) {
            const body = await res.json().catch(() => ({}))
            throw new Error(body?.detail || `API error ${res.status}`)
        }
        return res.blob()
    },

    createDonation: (data: { disaster_id?: string | null; request_id?: string; amount?: number; status?: string; notes?: string; donation_type?: string; resource_items?: { resource_type: string; quantity: number; unit?: string }[] }) =>
        apiFetch('/api/donor/donations', { method: 'POST', body: JSON.stringify(data) }),

    updateDonation: (id: string, data: any) =>
        apiFetch(`/api/donor/donations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

    deleteDonation: (id: string) =>
        apiFetch(`/api/donor/donations/${id}`, { method: 'DELETE' }),

    getDonorStats: () =>
        apiFetch('/api/donor/stats'),

    getPledges: () =>
        apiFetch('/api/donor/pledges'),

    createPledge: (disasterId: string) =>
        apiFetch('/api/donor/pledges', { method: 'POST', body: JSON.stringify({ disaster_id: disasterId }) }),

    removePledge: (disasterId: string) =>
        apiFetch(`/api/donor/pledges/${disasterId}`, { method: 'DELETE' }),

    getUrgentNeeds: () =>
        apiFetch('/api/resources?status=critical&limit=20'),

    getDonorApprovedRequests: (params?: { resource_type?: string; priority?: string; search?: string; donor_latitude?: number; donor_longitude?: number; sort?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/donor/approved-requests${qs(params)}`),

    // ━━ Admin – Requests ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getAdminRequests: (params?: { status?: string; priority?: string; resource_type?: string; search?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/admin/requests${qs(params)}`),

    getAdminRequestDetail: (requestId: string) =>
        apiFetch(`/api/admin/requests/${requestId}`),

    adminRequestAction: (requestId: string, data: { action: 'approve' | 'reject' | 'reassign' | 'escalate' | string; rejection_reason?: string; admin_note?: string; assigned_to?: string; assigned_role?: string; estimated_delivery?: string }) =>
        apiFetch(`/api/admin/requests/${requestId}/action`, { method: 'POST', body: JSON.stringify(data) }),

    adminUpdateRequestStatus: (requestId: string, data: { status: string; rejection_reason?: string; assigned_to?: string; estimated_delivery?: string }) =>
        apiFetch(`/api/admin/requests/${requestId}/status`, { method: 'PATCH', body: JSON.stringify(data) }),

    getRequestAuditTrail: (requestId: string) =>
        apiFetch(`/api/admin/requests/${requestId}/audit-trail`),

    getRequestNgoSubmissions: (requestId: string) =>
        apiFetch(`/api/admin/requests/${requestId}/ngo-submissions`),

    getAdminAvailableResources: (params?: { category?: string; status?: string; search?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/admin/available-resources${qs(params)}`),

    getAdminNotifications: (params?: { limit?: number; offset?: number }) =>
        apiFetch(`/api/admin/notifications${qs(params)}`),

    markAdminNotificationsRead: (notificationIds?: string[]) =>
        apiFetch('/api/admin/notifications/mark-read', { method: 'POST', body: JSON.stringify({ notification_ids: notificationIds }) }),

    getRequestTrends: (params?: { period?: string; days?: number }) =>
        apiFetch(`/api/admin/analytics/request-trends${qs(params)}`),

    // ━━ NGO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getNGORequests: (params?: { status?: string; priority?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/victim/requests${qs(params)}`),

    getNgoAvailableRequests: (params?: { resource_type?: string; priority?: string; ngo_latitude?: number; ngo_longitude?: number; sort?: string; limit?: number; offset?: number }) =>
        apiFetch(`/api/ngo/requests/available${qs(params)}`),

    getNgoAssignedRequests: (params?: { status?: string; limit?: number; offset?: number; ngo_latitude?: number; ngo_longitude?: number }) =>
        apiFetch(`/api/ngo/requests/assigned${qs(params)}`),

    claimNgoRequest: (requestId: string, data: { estimated_delivery?: string; notes?: string }) =>
        apiFetch(`/api/ngo/requests/${requestId}/claim`, { method: 'POST', body: JSON.stringify(data) }),

    updateNgoRequestStatus: (requestId: string, data: { status: string; proof_url?: string; notes?: string }) =>
        apiFetch(`/api/ngo/requests/${requestId}/status`, { method: 'PUT', body: JSON.stringify(data) }),

    getNgoDashboardStats: () =>
        apiFetch('/api/ngo/dashboard-stats'),

    // ━━ Dashboard component (live impact map) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getGlobalDisasters: () =>
        apiFetch('/api/global-disasters'),

    // ━━ Victim Requests ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getVictimRequests: (params?: { status?: string; priority?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/victim/requests${qs(params)}`),

    getVictimRequestTimeline: (requestId: string) =>
        apiFetch(`/api/victim/requests/${requestId}/timeline`),

    getRequestFulfillment: (requestId: string) =>
        apiFetch(`/api/victim/requests/${requestId}/fulfillment`),

    getResourcePool: (requestId: string) =>
        apiFetch(`/api/victim/requests/${requestId}/resource-pool`),

    getDonorRequestPool: (requestId: string) =>
        apiFetch(`/api/donor/requests/${requestId}/pool`),

    getNgoRequestPool: (requestId: string) =>
        apiFetch(`/api/ngo/requests/${requestId}/pool`),

    // ━━ Auth / Profile ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getMyProfile: () =>
        apiFetch('/api/auth/me'),

    updateMyProfile: (data: any) =>
        apiFetch('/api/auth/me', { method: 'PUT', body: JSON.stringify(data) }),

    switchRole: (newRole: string) =>
        apiFetch('/api/auth/me/switch-role', { method: 'POST', body: JSON.stringify({ new_role: newRole }) }),

    // ━━ Notifications (shared) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getNotifications: (params?: { unread_only?: boolean; limit?: number }) =>
        apiFetch(`/api/admin/notifications${qs(params)}`),

    markNotificationsRead: (notificationIds?: string[]) =>
        apiFetch('/api/admin/notifications/mark-read', { method: 'POST', body: JSON.stringify({ notification_ids: notificationIds }) }),

    // ━━ Disaster Chat ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getDisasterChat: (disasterId: string) =>
        apiFetch(`/api/disasters/${disasterId}/chat`),

    postDisasterChat: (disasterId: string, data: { content: string; user_name?: string; user_role?: string }) =>
        apiFetch(`/api/disasters/${disasterId}/chat`, { method: 'POST', body: JSON.stringify(data) }),

    // ━━ Interactivity ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getOperationalPulse: (params?: { limit?: number }) =>
        apiFetch(`/api/interactivity/operational-pulse${qs(params)}`),

    getActiveNeeds: (params?: { limit?: number }) =>
        apiFetch(`/api/interactivity/active-needs${qs(params)}`),

    createSourcingRequest: (data: { resource_type: string; quantity_needed: number; urgency?: string; description?: string }) =>
        apiFetch('/api/interactivity/sourcing-request', { method: 'POST', body: JSON.stringify(data) }),

    createMobilization: (data: { title: string; description?: string; location_id?: string; required_volunteers?: number }) =>
        apiFetch('/api/interactivity/mobilize', { method: 'POST', body: JSON.stringify(data) }),

    pledgeToSourcing: (data: { sourcing_request_id: string; quantity_pledged: number }) =>
        apiFetch('/api/interactivity/pledge', { method: 'POST', body: JSON.stringify(data) }),

    adoptRequest: (requestId: string) =>
        apiFetch(`/api/interactivity/adopt-request/${requestId}`, { method: 'POST' }),

    // ━━ Verification / Volunteer ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    verifyRequest: (data: { request_id: string; verification_status: string; field_notes?: string; photo_url?: string; latitude_at_verification?: number; longitude_at_verification?: number }) =>
        apiFetch('/api/interactivity/verify-request', { method: 'POST', body: JSON.stringify(data) }),

    completeAssignment: (assignmentId: string, feedback: string = '') =>
        apiFetch(`/api/interactivity/complete-assignment/${assignmentId}`, { method: 'POST', body: JSON.stringify({ feedback }) }),

    getActiveMissions: (params?: { limit?: number }) =>
        apiFetch(`/api/interactivity/active-missions${qs(params)}`),

    getUserImpact: () =>
        apiFetch('/api/interactivity/my-impact'),

    // ━━ Admin – Users ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    confirmUserVerification: (userId: string, status: string, notes?: string) =>
        apiFetch(`/api/admin/users/${userId}/verify`, { method: 'POST', body: JSON.stringify({ status, notes }) }),

    // ━━ Admin – Export ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    exportData: (dataType: string) =>
        apiFetch(`/api/admin/export/${dataType}`),

    exportInteractivityData: (table: string) =>
        apiFetch(`/api/analytics/export/interactivity${qs({ table })}`),

    // ━━ Analytics ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getAnalyticsSummary: () =>
        apiFetch('/api/analytics/summary'),

    getVolunteerPerformance: (params?: { limit?: number }) =>
        apiFetch(`/api/analytics/volunteer-performance${qs(params)}`),

    getResourceBurnRate: (params?: { days?: number }) =>
        apiFetch(`/api/analytics/resource-burn-rate${qs(params)}`),

    // ━━ Ingestion ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getIngestionStatus: () =>
        apiFetch('/api/ingestion/status'),

    stopOrchestrator: () =>
        apiFetch('/api/ingestion/stop', { method: 'POST' }),

    // ━━ ML / Predictions  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getModelInfo: () =>
        apiFetch('/api/admin/analytics/model-info'),

    predictSandbox: (data: any) =>
        apiFetch('/api/predictions/sandbox', { method: 'POST', body: JSON.stringify(data) }),

    // ━━ NGO Stats (alias) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getNgoStats: () =>
        apiFetch('/api/ngo/dashboard-stats'),

    // ━━ NGO Enhanced Dashboard ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    submitNgoAvailability: (requestId: string, data: { available_quantity: number; estimated_delivery_time: string; assigned_team?: string; vehicle_type?: string; ngo_latitude?: number; ngo_longitude?: number; notes?: string }) =>
        apiFetch(`/api/ngo/requests/${requestId}/availability`, { method: 'POST', body: JSON.stringify(data) }),

    getNgoAvailability: (requestId: string) =>
        apiFetch(`/api/ngo/requests/${requestId}/availability`),

    updateNgoDeliveryStatus: (requestId: string, data: { new_status: string; proof_url?: string; notes?: string; delivery_latitude?: number; delivery_longitude?: number }) =>
        apiFetch(`/api/ngo/requests/${requestId}/delivery`, { method: 'PUT', body: JSON.stringify(data) }),

    getNgoInventory: (params?: { category?: string; status?: string; limit?: number; offset?: number }) =>
        apiFetch(`/api/ngo/inventory${qs(params)}`),

    addNgoInventoryItem: (data: { category: string; resource_type: string; title: string; description?: string; total_quantity: number; unit?: string; address_text?: string }) =>
        apiFetch('/api/ngo/inventory', { method: 'POST', body: JSON.stringify(data) }),

    updateNgoInventoryItem: (resourceId: string, params: { total_quantity?: number; status?: string }) =>
        apiFetch(`/api/ngo/inventory/${resourceId}${qs(params)}`, { method: 'PATCH' }),

    getNgoAuditLog: (params?: { action_type?: string; limit?: number; offset?: number }) =>
        apiFetch(`/api/ngo/audit-log${qs(params)}`),

    getNgoNotifications: (params?: { unread_only?: boolean; limit?: number }) =>
        apiFetch(`/api/ngo/notifications${qs(params)}`),

    markNgoNotificationsRead: (notificationIds?: string[]) =>
        apiFetch('/api/ngo/notifications/mark-read', { method: 'POST', body: JSON.stringify({ notification_ids: notificationIds }) }),

    // ━━ DisasterGPT LLM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    queryLLM: (data: { query: string; disaster_id?: string; top_k?: number; max_tokens?: number; temperature?: number }) =>
        apiFetch('/api/llm/query', { method: 'POST', body: JSON.stringify(data) }),

    getLLMStats: () =>
        apiFetch('/api/llm/stats'),

    triggerLLMIndex: () =>
        apiFetch('/api/llm/index', { method: 'POST' }),

    // ━━ Fairness Frontier ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getFairnessFrontier: (params?: { disaster_id?: string; max_distance_km?: number }) =>
        apiFetch(`/api/admin/fairness-frontier${qs(params)}`),

    applyFairnessPlan: (data: { plan_index: number; disaster_id?: string }) =>
        apiFetch('/api/admin/fairness-frontier/apply', { method: 'POST', body: JSON.stringify(data) }),

    getDisasterDropdownOptions: () =>
        apiFetch('/api/disasters/dropdown/options'),

    getFairnessAudits: (params?: { disaster_id?: string; limit?: number }) =>
        apiFetch(`/api/admin/fairness-audit${qs(params)}`),

    // ━━ Hotspot Clusters ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getHotspots: (params?: { status?: string; min_priority?: string }) =>
        apiFetch(`/api/hotspots${qs(params)}`),

    getHotspotDetail: (clusterId: string) =>
        apiFetch(`/api/hotspots/${clusterId}`),

    triggerClustering: () =>
        apiFetch('/api/hotspots/trigger', { method: 'POST' }),

    updateHotspotStatus: (clusterId: string, status: string) =>
        apiFetch(`/api/hotspots/${clusterId}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),

    assignHotspotResources: (clusterId: string, data: { resource_type: string; quantity: number; assigned_to?: string; notes?: string }) =>
        apiFetch(`/api/hotspots/${clusterId}/assign`, { method: 'POST', body: JSON.stringify(data) }),

    sendHotspotAlert: (clusterId: string, data: { channel?: string; recipient_role?: string; subject?: string; body?: string; severity?: string }) =>
        apiFetch(`/api/hotspots/${clusterId}/alert`, { method: 'POST', body: JSON.stringify(data) }),

    getHotspotInsights: (clusterId: string) =>
        apiFetch(`/api/hotspots/${clusterId}/insights`),

    // ━━ Causal AI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    runCounterfactual: (data: { disaster_id: string; intervention: { variable: string; new_value: number }; outcome_variable?: string }) =>
        apiFetch('/api/causal/counterfactual', { method: 'POST', body: JSON.stringify(data) }),

    getCausalEffects: () =>
        apiFetch('/api/causal/effects'),

    getCausalGraph: () =>
        apiFetch('/api/causal/graph'),

    getCausalAudit: (disasterId: string) =>
        apiFetch(`/api/causal/audit/${disasterId}`, { method: 'POST' }),

    // ━━ Unified DisasterGPT Streaming ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    streamUnifiedQuery: async function* (data: { query: string; disaster_id?: string; mode?: string; top_k?: number; max_tokens?: number; temperature?: number }) {
        const token = await getAccessToken()
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const res = await fetch(`${API_BASE}/api/llm/unified`, {
            method: 'POST',
            headers,
            body: JSON.stringify(data),
        })
        if (!res.ok) throw new Error(`Stream error ${res.status}`)
        if (!res.body) return

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })

            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6).trim()
                    if (payload) {
                        try { yield JSON.parse(payload) } catch { yield payload }
                    }
                }
            }
        }
    },

    // ━━ DisasterGPT Streaming ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    streamLLMQuery: async function* (data: { query: string; disaster_id?: string; top_k?: number; max_tokens?: number; temperature?: number }) {
        const token = await getAccessToken()
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const res = await fetch(`${API_BASE}/api/llm/stream`, {
            method: 'POST',
            headers,
            body: JSON.stringify(data),
        })
        if (!res.ok) throw new Error(`Stream error ${res.status}`)
        if (!res.body) return

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })

            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6).trim()
                    if (payload) {
                        try { yield JSON.parse(payload) } catch { yield payload }
                    }
                }
            }
        }
    },

    // ━━ RL Allocation ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    rlAllocate: (data: { disaster_id: string; required_resources: any[]; max_distance_km?: number }) =>
        apiFetch('/api/ml/rl-allocate', { method: 'POST', body: JSON.stringify(data) }),

    getRLStatus: () =>
        apiFetch('/api/ml/rl-status'),

    trainRL: (nEpisodes: number = 500) =>
        apiFetch(`/api/ml/rl-train?n_episodes=${nEpisodes}`, { method: 'POST' }),

    // ━━ GAT Matching ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    gatMatch: (data?: { disaster_id?: string; radius_km?: number }) =>
        apiFetch('/api/ml/gat/match', { method: 'POST', body: JSON.stringify(data || {}) }),

    getGATStatus: () =>
        apiFetch('/api/ml/gat/status'),

    // ━━ Federated Learning ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    runFederatedRound: (data?: { n_clients?: number; epochs_per_client?: number; non_iid?: boolean }) =>
        apiFetch('/api/ml/federated/round', { method: 'POST', body: JSON.stringify(data || {}) }),

    getFederatedStatus: () =>
        apiFetch('/api/ml/federated/status'),

    trainFederated: (data?: { n_rounds?: number; n_clients?: number; epochs_per_client?: number }) =>
        apiFetch('/api/ml/federated/train', { method: 'POST', body: JSON.stringify(data || {}) }),

    // ━━ Multi-Agent System ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    agentQuery: (data: { query: string; disaster_id?: string }) =>
        apiFetch('/api/ml/agent/query', { method: 'POST', body: JSON.stringify(data) }),

    streamAgentQuery: async function* (data: { query: string; disaster_id?: string }) {
        const token = await getAccessToken()
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const res = await fetch(`${API_BASE}/api/ml/agent/stream`, {
            method: 'POST',
            headers,
            body: JSON.stringify(data),
        })
        if (!res.ok) throw new Error(`Agent stream error ${res.status}`)
        if (!res.body) return

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })

            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6).trim()
                    if (payload) {
                        try { yield JSON.parse(payload) } catch { yield payload }
                    }
                }
            }
        }
    },

    getAgentStatus: () =>
        apiFetch('/api/ml/agent/status'),

    // ━━ PINN Spread Prediction ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    pinnPredict: (data: { points: number[][] }) =>
        apiFetch('/api/ml/pinn/predict', { method: 'POST', body: JSON.stringify(data) }),

    pinnPredictGrid: (data: { x_range: number[]; y_range: number[]; time: number; resolution?: number }) =>
        apiFetch('/api/ml/pinn/predict-grid', { method: 'POST', body: JSON.stringify(data) }),

    getPINNStatus: () =>
        apiFetch('/api/ml/pinn/status'),

    // ━━ ML Health ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getMLHealth: () =>
        apiFetch('/api/ml/health'),

    // ━━ Scheduled SitRep ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    scheduleSitrep: (data: { interval_hours: number }) =>
        apiFetch('/api/admin/sitrep/schedule', { method: 'POST', body: JSON.stringify(data) }),

    getSitrepSchedule: () =>
        apiFetch('/api/admin/sitrep/schedule'),

    // ━━ Disaster-Aware Enhancements ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    // Per-disaster anomaly detection
    getDisasterAnomalies: (disasterId: string, params?: { status?: string; severity?: string; limit?: number }) =>
        apiFetch(`/api/ml/anomalies/disaster/${disasterId}${qs(params)}`),

    // Disaster-specific outcome tracking
    getDisasterOutcomes: (disasterId: string, params?: { limit?: number }) =>
        apiFetch(`/api/ml/outcomes/disaster/${disasterId}${qs(params)}`),

    // Disaster-specific hotspots
    getDisasterHotspots: (disasterId: string) =>
        apiFetch(`/api/hotspots/disaster/${disasterId}`),

    // Disaster-specific severity forecast
    getDisasterSeverityForecast: (disasterId: string, params?: { horizon_hours?: number }) =>
        apiFetch(`/api/ml/forecast/disaster/${disasterId}${qs(params)}`),

    // Disaster-specific spread prediction
    getDisasterSpreadPrediction: (disasterId: string, params?: { time_hours?: number }) =>
        apiFetch(`/api/ml/pinn/disaster/${disasterId}${qs(params)}`),

    // Disaster-specific situation report
    generateDisasterSitrep: (disasterId: string, reportType: string = 'disaster_focused') =>
        apiFetch('/api/ml/sitreps/generate', { method: 'POST', body: JSON.stringify({ disaster_id: disasterId, report_type: reportType, generated_by: 'user' }) }),

    getDisasterSitrep: (disasterId: string, params?: { limit?: number }) =>
        apiFetch(`/api/ml/sitreps/disaster/${disasterId}${qs(params)}`),

    // Disaster-specific query history
    getDisasterQueryHistory: (disasterId: string, params?: { limit?: number }) =>
        apiFetch(`/api/ml/query-history/disaster/${disasterId}${qs(params)}`),

    // Victim disaster context
    getVictimDisasterContext: (victimId: string) =>
        apiFetch(`/api/victim/disaster-context/${victimId}`),

    // Disaster resource recommendations
    getDisasterResourceRecommendations: (disasterId: string) =>
        apiFetch(`/api/ml/recommendations/disaster/${disasterId}`),

    // Nearby resources for victim
    getNearbyResources: (latitude: number, longitude: number, params?: { radius_km?: number; category?: string; limit?: number }) =>
        apiFetch(`/api/resources/nearby${qs({ latitude, longitude, ...params })}`),

    // Real-time disaster updates
    getDisasterUpdates: (disasterId: string, params?: { since?: string; limit?: number }) =>
        apiFetch(`/api/disasters/${disasterId}/updates${qs(params)}`),

    // Disaster evacuation routes
    getEvacuationRoutes: (disasterId: string, latitude: number, longitude: number) =>
        apiFetch(`/api/disasters/${disasterId}/evacuation-routes${qs({ latitude, longitude })}`),

    // ━━ MoE (Mixture of Experts) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getMoEStatus: () =>
        apiFetch('/api/ml/moe/status'),

    moePredict: (data: { features: Record<string, any>; disaster_type?: string; severity?: string; latitude?: number; longitude?: number; use_cache?: boolean }) =>
        apiFetch('/api/ml/moe/predict', { method: 'POST', body: JSON.stringify(data) }),

    moePredictTask: (data: { features: Record<string, any>; task?: string; disaster_type?: string; severity?: string; latitude?: number; longitude?: number }) =>
        apiFetch('/api/ml/moe/predict-task', { method: 'POST', body: JSON.stringify(data) }),

    trainMoE: (params?: { epochs?: number; batch_size?: number; learning_rate?: number }) =>
        apiFetch(`/api/ml/moe/train${qs(params)}`, { method: 'POST' }),

    getMoECacheStats: () =>
        apiFetch('/api/ml/moe/cache-stats'),

    clearMoECache: () =>
        apiFetch('/api/ml/moe/clear-cache', { method: 'POST' }),

    resetMoEStats: () =>
        apiFetch('/api/ml/moe/reset-stats', { method: 'POST' }),
}
