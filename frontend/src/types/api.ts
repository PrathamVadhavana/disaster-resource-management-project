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
  // NLP priority scoring
  nlp_priority?: string | null
  nlp_confidence?: number | null
  manual_priority?: string | null
  extracted_needs?: Array<Record<string, unknown>> | null
  // Fulfillment tracking
  fulfillment_entries?: Array<{
    provider_id?: string
    provider_name?: string
    provider_role?: string
    donation_type?: string
    amount?: number
    resource_items?: Array<Record<string, unknown>>
    status?: string
    created_at?: string
  }>
  fulfillment_pct?: number
  // Verification
  is_verified?: boolean
  verification_status?: string | null
  verified_at?: string | null
  verified_by?: string | null
  // Delivery confirmation
  delivery_confirmation_code?: string | null
  delivery_confirmed_at?: string | null
  // Donor adoption
  adopted_by?: string | null
  adoption_status?: string | null
  // Victim grouping
  group_id?: string | null
  head_count?: number
  // Disaster linking
  linked_disaster_id?: string | null
  disaster_distance_km?: number | null
  disaster_id?: string | null
  // SLA tracking
  sla_escalated_at?: string | null
  sla_admin_alerted?: boolean
  sla_delivery_alerted?: boolean
  // Admin
  admin_note?: string | null
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
  prediction_id: string | null
  channel: string
  recipient: string
  recipient_role: string | null
  severity: string
  status: string
  subject: string | null
  body: string | null
  external_ref: string | null
  error_message: string | null
  sent_at: string | null
  created_at: string
}

// ─── AI Operations ──────────────────────────────────────────────────────────

export interface SitrepReport {
  id: string
  report_date: string
  report_type: string
  title: string
  markdown_body: string
  summary: string | null
  key_metrics: Record<string, unknown>
  recommendations: Array<Record<string, unknown>>
  model_used: string
  generated_by: string
  generation_time_ms: number | null
  emailed_to: string[]
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface AnomalyAlert {
  id: string
  anomaly_type: string
  severity: string
  title: string
  description: string | null
  ai_explanation: string | null
  metric_name: string
  metric_value: number
  expected_range: Record<string, unknown>
  anomaly_score: number | null
  related_disaster_id: string | null
  related_location_id: string | null
  context_data: Record<string, unknown>
  status: string
  acknowledged_by: string | null
  acknowledged_at: string | null
  detected_at: string
  created_at: string
}

export interface HealthResponse {
  status: string
  ml_models_loaded: boolean
}

// ─── Fairness ───────────────────────────────────────────────────────────────

export interface FairnessPlan {
  plan_index: number
  equity_weight: number
  efficiency_score: number
  equity_score: number
  gini: number
  allocation_count: number
  zone_allocations: Record<string, number>
  adjustments_applied: string[]
  allocations: Array<{
    resource_id: string
    type: string
    quantity: number
    location: string
    distance_km: number
    zone_id?: string
    rural_boost_applied?: boolean
    vulnerability_bump?: boolean
    underservice_bonus_applied?: boolean
  }>
}

export interface FairnessFrontierResponse {
  disaster_id: string | null
  total_resources: number
  total_needs: number
  total_zones: number
  plans: FairnessPlan[]
}

export interface FairnessApplyResponse {
  status: string
  plan_index: number
  resources_allocated: number
  efficiency_score: number
  equity_score: number
  gini: number
  adjustments_applied: string[]
}

export interface FairnessAudit {
  disaster_id: string | null
  gini_coefficient: number
  overall_equity_score: number
  vulnerability_scores: Record<string, number>
  underservice_scores: Record<string, number>
  zone_details: Array<{
    zone_id: string
    zone_name: string
    population: number
    vulnerability_index: number
    underservice_score: number
    allocated: number
    needed: number
    fulfillment_pct: number
    is_rural: boolean
    ngo_count_within_20km: number
  }>
  distribution_by_vulnerability_group: Record<string, {
    zone_count: number
    total_allocated: number
    total_needed: number
    avg_fulfillment_pct: number
  }>
  plan_index?: number
  applied_by?: string
  applied_at?: string
}
