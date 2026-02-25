/**
 * Centralised API client — barrel export consumed by every dashboard module.
 *
 * Usage:  import { api } from '@/lib/api'
 *         const disasters = await api.getDisasters({ status: 'active' })
 */
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Auth helper ──────────────────────────────────────────────────────────────

async function getAccessToken(): Promise<string | null> {
    try {
        const supabase = createClient()
        const { data } = await supabase.auth.getSession()
        return data?.session?.access_token ?? null
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
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `API error ${res.status}`)
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
    getDisasters: (params?: { status?: string; severity?: string; type?: string; limit?: number; offset?: number }) =>
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
    askCoordinatorQuery: (query: string, userId?: string, sessionId?: string) =>
        apiFetch('/api/ml/query', { method: 'POST', body: JSON.stringify({ query, user_id: userId, session_id: sessionId }) }),

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
    getDonations: (params?: { status?: string; limit?: number }) =>
        apiFetch(`/api/donor/donations${qs(params)}`),

    getDonationReceipt: (id: string) =>
        apiFetch(`/api/donor/donations/${id}/receipt`),

    createDonation: (data: { disaster_id?: string | null; request_id?: string; amount?: number; status?: string; notes?: string }) =>
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

    // ━━ Admin – Requests ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    getAdminRequests: (params?: { status?: string; priority?: string; resource_type?: string; search?: string; page?: number; page_size?: number }) =>
        apiFetch(`/api/admin/requests${qs(params)}`),

    getAdminRequestDetail: (requestId: string) =>
        apiFetch(`/api/admin/requests/${requestId}`),

    adminRequestAction: (requestId: string, data: { action: string; rejection_reason?: string; admin_note?: string; assigned_to?: string; estimated_delivery?: string }) =>
        apiFetch(`/api/admin/requests/${requestId}/action`, { method: 'POST', body: JSON.stringify(data) }),

    adminUpdateRequestStatus: (requestId: string, data: { status: string; rejection_reason?: string; assigned_to?: string; estimated_delivery?: string }) =>
        apiFetch(`/api/admin/requests/${requestId}/status`, { method: 'PATCH', body: JSON.stringify(data) }),

    getRequestAuditTrail: (requestId: string) =>
        apiFetch(`/api/admin/requests/${requestId}/audit-trail`),

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

    getNgoAvailableRequests: (params?: { resource_type?: string; priority?: string; limit?: number; offset?: number }) =>
        apiFetch(`/api/ngo/requests/available${qs(params)}`),

    getNgoAssignedRequests: (params?: { status?: string; limit?: number; offset?: number }) =>
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
}
