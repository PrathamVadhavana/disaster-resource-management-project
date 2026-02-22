/**
 * Shared TypeScript types for API responses.
 * All API client methods should use these instead of `any`.
 */

// ─── Disasters ──────────────────────────────────────────────────────────────

export interface DisasterLocation {
  latitude: number | null
  longitude: number | null
  location_name: string
  location_city: string
  location_country: string
}

export interface Disaster extends DisasterLocation {
  id: string
  type: string
  severity: string
  title: string
  description: string | null
  location_id: string
  affected_population: number | null
  casualties: number | null
  estimated_damage: number | null
  start_date: string
  end_date: string | null
  status: string
  created_at: string
  updated_at: string
}

// ─── Predictions ────────────────────────────────────────────────────────────

export interface Prediction {
  id: string
  location_id: string
  prediction_type: string
  confidence_score: number
  predicted_severity?: string
  predicted_area_km2?: number
  ci_lower_km2?: number
  ci_upper_km2?: number
  predicted_casualties?: number
  predicted_damage_usd?: number
  model_version: string
  created_at: string
}

// ─── Resources ──────────────────────────────────────────────────────────────

export interface Resource {
  id: string
  location_id: string
  type: string
  name: string
  quantity: number
  unit: string
  priority: number
  status: string
  disaster_id: string | null
  allocated_to: string | null
  created_at: string
  updated_at: string
}

export interface AllocationResponse {
  disaster_id: string
  allocations: Array<{
    resource_id: string
    type: string
    quantity: number
    location: string
    distance_km: number
    expiry_date: string | null
  }>
  optimization_score: number
  unmet_needs: Array<{ type: string; quantity: number; urgency: number }>
  score_breakdown: {
    coverage_pct: number
    unmet_needs: Array<{ type: string; quantity: number; urgency: number }>
    estimated_delivery_km: number
    solver_status: string
  } | null
}

export interface ForecastItem {
  resource_type: string
  forecast_hour: number
  predicted_demand: number
  predicted_supply: number
  shortfall: number
  confidence_lower: number
  confidence_upper: number
}

export interface ForecastResponse {
  generated_at: string
  horizon_hours: number
  method: string
  items: ForecastItem[]
}

// ─── NGO / Victim Requests ──────────────────────────────────────────────────

export interface ResourceRequest {
  id: string
  victim_id: string
  resource_type: string
  quantity: number
  items: Array<{ resource_type: string; quantity: number; custom_name?: string }>
  description: string | null
  priority: 'critical' | 'high' | 'medium' | 'low'
  latitude: number | null
  longitude: number | null
  address_text: string | null
  status: string
  assigned_to: string | null
  assigned_role: string | null
  estimated_delivery: string | null
  attachments: string[]
  rejection_reason: string | null
  created_at: string
  updated_at: string
  // Flattened fields that may come from joined queries
  title?: string
  location_name?: string
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

// ─── Auth ───────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  email: string
}

// ─── Ingestion / Alerts ─────────────────────────────────────────────────────

export interface IngestedEvent {
  id: string
  source_id: string
  external_id: string | null
  event_type: string
  title: string | null
  description: string | null
  severity: string | null
  latitude: number | null
  longitude: number | null
  location_name: string | null
  raw_payload: Record<string, unknown>
  ingested_at: string
  processed: boolean
  disaster_id: string | null
  prediction_ids: string[]
}

export interface AlertNotification {
  id: string
  event_id: string | null
  disaster_id: string | null
  channel: string
  recipient: string
  severity: string
  status: string
  subject: string | null
  body: string | null
  created_at: string
}

// ─── AI Coordinator ─────────────────────────────────────────────────────────

export interface SitrepReport {
  id: string
  report_type: string
  generated_by: string
  content: string
  created_at: string
}

export interface AnomalyAlert {
  id: string
  anomaly_type: string
  severity: string
  description: string
  status: string
  detected_at: string
  acknowledged_at: string | null
  resolved_at: string | null
}

export interface HealthResponse {
  status: string
  ml_models_loaded: boolean
}
