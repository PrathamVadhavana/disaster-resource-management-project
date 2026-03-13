from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationInfo


class DisasterType(StrEnum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    HURRICANE = "hurricane"
    TORNADO = "tornado"
    WILDFIRE = "wildfire"
    TSUNAMI = "tsunami"
    DROUGHT = "drought"
    LANDSLIDE = "landslide"
    VOLCANO = "volcano"
    OTHER = "other"


class DisasterSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DisasterStatus(StrEnum):
    PREDICTED = "predicted"
    ACTIVE = "active"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class ResourceType(StrEnum):
    FOOD = "food"
    WATER = "water"
    MEDICAL = "medical"
    SHELTER = "shelter"
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    OTHER = "other"


class ResourceStatus(StrEnum):
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    IN_TRANSIT = "in_transit"
    DEPLOYED = "deployed"


class LocationType(StrEnum):
    CITY = "city"
    REGION = "region"
    SHELTER = "shelter"
    HOSPITAL = "hospital"
    WAREHOUSE = "warehouse"


class PredictionType(StrEnum):
    SEVERITY = "severity"
    SPREAD = "spread"
    DURATION = "duration"
    IMPACT = "impact"


class LocationBase(BaseModel):
    name: str
    type: LocationType
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: str | None = None
    city: str
    state: str
    country: str
    postal_code: str | None = None
    population: int | None = None
    area_sq_km: float | None = None


class LocationCreate(LocationBase):
    pass


class Location(LocationBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class DisasterBase(BaseModel):
    type: DisasterType
    severity: DisasterSeverity
    title: str
    description: str | None = None
    location_id: str
    affected_population: int | None = None
    casualties: int | None = None
    estimated_damage: float | None = None
    start_date: datetime
    metadata: dict[str, Any] | None = None


class DisasterCreate(DisasterBase):
    pass


class DisasterUpdate(BaseModel):
    severity: DisasterSeverity | None = None
    status: DisasterStatus | None = None
    description: str | None = None
    affected_population: int | None = None
    casualties: int | None = None
    estimated_damage: float | None = None
    end_date: datetime | None = None


class Disaster(DisasterBase):
    id: str
    created_at: datetime
    updated_at: datetime
    status: DisasterStatus
    end_date: datetime | None = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class PredictionInput(BaseModel):
    location_id: str | None = "sandbox"
    prediction_type: PredictionType
    features: dict[str, Any] = Field(
        ..., description="Feature dict for ML model. Required fields vary by prediction type."
    )

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        prediction_type = info.data.get("prediction_type")

        if prediction_type == PredictionType.SEVERITY:
            required = ["temperature", "humidity", "wind_speed", "pressure"]
        elif prediction_type == PredictionType.SPREAD:
            required = ["current_area", "wind_speed"]
        elif prediction_type == PredictionType.IMPACT:
            required = ["affected_population"]
        else:
            required = []

        # Only warn; don't block — the ML service has fallbacks
        missing = [f for f in required if f not in v]
        if missing:
            # Add defaults for missing required features
            for f in missing:
                v.setdefault(f, 0)

        return v


class PredictionResponse(BaseModel):
    id: str
    location_id: str
    prediction_type: PredictionType
    confidence_score: float
    predicted_severity: DisasterSeverity | None = None
    predicted_start_date: datetime | None = None
    predicted_casualties: int | None = None
    predicted_area_km2: float | None = None
    ci_lower_km2: float | None = None
    ci_upper_km2: float | None = None
    predicted_damage_usd: float | None = None
    # ── TFT multi-horizon severity forecasts ──
    severity_6h: str | None = Field(None, description="Predicted severity at t+6 hours")
    severity_12h: str | None = Field(None, description="Predicted severity at t+12 hours")
    severity_24h: str | None = Field(None, description="Predicted severity at t+24 hours")
    severity_48h: str | None = Field(None, description="Predicted severity at t+48 hours")
    lower_bound: dict[str, Any] | None = Field(None, description="10th-percentile bounds per horizon")
    upper_bound: dict[str, Any] | None = Field(None, description="90th-percentile bounds per horizon")
    model_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResourceBase(BaseModel):
    location_id: str | None = None
    type: ResourceType = Field(None, alias="resource_type")
    name: str = Field(..., alias="title")
    description: str | None = None
    quantity: float = Field(..., alias="total_quantity")
    unit: str
    priority: int = Field(default=5, ge=1, le=10)
    category: str | None = None
    status: ResourceStatus = ResourceStatus.AVAILABLE

    @model_validator(mode="before")
    @classmethod
    def map_resource_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map category to type if type is missing
            if not data.get("type") and not data.get("resource_type"):
                if data.get("category"):
                    data["resource_type"] = data["category"]
            
            # Smart mapping for values
            v = data.get("resource_type") or data.get("type")
            if isinstance(v, str):
                v_low = v.lower()
                mapping = {
                    "volunteers": "personnel",
                    "clothing": "equipment",
                    "clothes": "equipment",
                    "financial aid": "other",
                }
                new_v = mapping.get(v_low, v_low)
                if data.get("resource_type"):
                    data["resource_type"] = new_v
                else:
                    data["type"] = new_v
        return data

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }

    pass


class ResourceCreate(ResourceBase):
    disaster_id: str | None = None


class ResourceUpdate(BaseModel):
    quantity: float | None = None
    status: ResourceStatus | None = None
    allocated_to: str | None = None
    priority: int | None = Field(None, ge=1, le=10)


class Resource(ResourceBase):
    id: str
    created_at: datetime
    updated_at: datetime
    disaster_id: str | None
    status: ResourceStatus
    allocated_to: str | None

    pass


class PriorityWeightsSchema(BaseModel):
    """Tunable weights for the allocation objective function."""

    urgency_weight: float = Field(1.0, ge=0, description="Weight for urgency score")
    distance_weight: float = Field(0.3, ge=0, description="Penalty weight for delivery distance")
    expiry_weight: float = Field(0.2, ge=0, description="Bonus weight for soon-to-expire resources")
    coverage_weight: float = Field(1.0, ge=0, description="Weight for overall coverage")


class AllocationRequest(BaseModel):
    disaster_id: str
    required_resources: list[dict[str, Any]] = Field(
        ..., description="List of required resources with type, quantity, and priority"
    )
    priority_weights: PriorityWeightsSchema | None = Field(
        None, description="Optional objective-function weights (defaults used when omitted)"
    )
    max_distance_km: float = Field(
        500.0, gt=0, description="Maximum delivery distance in km — resources further away are excluded"
    )


class OptimizationScoreBreakdown(BaseModel):
    """Detailed breakdown of the optimisation result."""

    coverage_pct: float = Field(0, description="Percentage of requirements met (0-100)")
    unmet_needs: list[dict[str, Any]] = Field(default_factory=list)
    estimated_delivery_km: float = Field(0, description="Total delivery distance across all allocations (km)")
    solver_status: str = Field("not_solved", description="LP solver exit status")


class AllocationResponse(BaseModel):
    disaster_id: str
    allocations: list[dict[str, Any]]
    optimization_score: float
    unmet_needs: list[dict[str, Any]]
    score_breakdown: OptimizationScoreBreakdown | None = None


# ============================================================
# Forecast Schemas
# ============================================================


class ForecastItemSchema(BaseModel):
    resource_type: str
    forecast_hour: int = Field(..., description="Hours from now")
    predicted_demand: float
    predicted_supply: float
    shortfall: float = Field(..., description="Positive = deficit, negative = surplus")
    confidence_lower: float = 0.0
    confidence_upper: float = 0.0


class ForecastResponse(BaseModel):
    generated_at: datetime
    horizon_hours: int = 72
    method: str = Field("linear", description="Forecasting method used (linear | prophet)")
    items: list[ForecastItemSchema] = Field(default_factory=list)


class UserRole(StrEnum):
    VICTIM = "victim"
    NGO = "ngo"
    DONOR = "donor"
    VOLUNTEER = "volunteer"
    ADMIN = "admin"


class UserLogin(BaseModel):
    email: str
    password: str


class UserRegister(BaseModel):
    email: str
    password: str = ""
    full_name: str | None = None
    role: UserRole = UserRole.VICTIM


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str
    redirect_to: str | None = None


class ResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str


class EmailVerificationResponse(BaseModel):
    verified: bool
    message: str
    verification_status: str | None = None


# ============================================================
# Victim Module Schemas
# ============================================================


class VictimResourceType(StrEnum):
    FOOD = "Food"
    WATER = "Water"
    MEDICAL = "Medical"
    SHELTER = "Shelter"
    CLOTHING = "Clothing"
    FINANCIAL_AID = "Financial Aid"
    EVACUATION = "Evacuation"
    VOLUNTEERS = "Volunteers"
    CUSTOM = "Custom"
    MULTIPLE = "Multiple"


class RequestPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    AVAILABILITY_SUBMITTED = "availability_submitted"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CLOSED = "closed"
    REJECTED = "rejected"


class ResourceItem(BaseModel):
    resource_type: str
    quantity: int = Field(default=1, ge=1)
    custom_name: str | None = None


class ResourceRequestCreate(BaseModel):
    resource_type: VictimResourceType | None = None  # primary type (auto-set from items)
    quantity: int = Field(default=1, ge=1)
    items: list[ResourceItem] = Field(default_factory=list)
    description: str | None = None
    priority: RequestPriority = RequestPriority.MEDIUM
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    address_text: str | None = None
    attachments: list[str] | None = Field(default_factory=list)
    disaster_type: str | None = None


class ResourceRequestUpdate(BaseModel):
    resource_type: VictimResourceType | None = None
    quantity: int | None = Field(None, ge=1)
    items: list[ResourceItem] | None = None
    description: str | None = None
    priority: RequestPriority | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    address_text: str | None = None
    attachments: list[str] | None = None


class ResourceRequestResponse(BaseModel):
    id: str
    victim_id: str
    resource_type: str
    quantity: int
    items: list[dict] | None = Field(default_factory=list)
    description: str | None = None
    priority: str
    latitude: float | None = None
    longitude: float | None = None
    address_text: str | None = None
    status: str
    assigned_to: str | None = None
    assigned_role: str | None = None
    estimated_delivery: datetime | None = None
    attachments: list[str] | None = Field(default_factory=list)
    rejection_reason: str | None = None
    is_verified: bool = False
    verification_status: str | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    adopted_by: str | None = None
    adoption_status: str | None = None
    delivery_confirmation_code: str | None = None
    delivery_confirmed_at: datetime | None = None
    # NLP priority scoring fields
    nlp_priority: str | None = None
    nlp_confidence: float | None = None
    manual_priority: str | None = None
    extracted_needs: list[dict] | None = None
    # Fulfillment tracking
    fulfillment_entries: list[dict] | None = Field(default_factory=list)
    fulfillment_pct: int = 0
    # Admin
    admin_note: str | None = None
    # Victim grouping
    group_id: str | None = None
    head_count: int = 1
    # Disaster linking
    linked_disaster_id: str | None = None
    disaster_distance_km: float | None = None
    disaster_id: str | None = None
    # SLA tracking
    sla_escalated_at: datetime | None = None
    sla_admin_alerted: bool = False
    sla_delivery_alerted: bool = False
    # NLP classification
    nlp_classification: dict | None = None
    urgency_signals: list[dict] | None = Field(default_factory=list)
    ai_confidence: float | None = None
    nlp_overridden: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class ResourceRequestListResponse(BaseModel):
    requests: list[ResourceRequestResponse]
    total: int
    page: int
    page_size: int


class DashboardStats(BaseModel):
    total_requests: int = 0
    pending: int = 0
    approved: int = 0
    assigned: int = 0
    in_progress: int = 0
    completed: int = 0
    rejected: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)


class VictimProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    phone: str | None = None
    role: str
    current_status: str | None = None
    needs: list[str] | None = None
    medical_needs: str | None = None
    location_lat: float | None = None
    location_long: float | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class VictimProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    current_status: str | None = None
    needs: list[str] | None = None
    medical_needs: str | None = None
    location_lat: float | None = Field(None, ge=-90, le=90)
    location_long: float | None = Field(None, ge=-180, le=180)


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class UserVerificationUpdate(BaseModel):
    verification_status: VerificationStatus
    verification_notes: str | None = None


# --- Phase 6: Interactivity Schemas ---


class RequestVerificationStatus(StrEnum):
    TRUSTED = "trusted"
    DUBIOUS = "dubious"
    FALSE_ALARM = "false_alarm"


class RequestVerificationCreate(BaseModel):
    request_id: str
    field_notes: str | None = None
    photo_url: str | None = None
    verification_status: RequestVerificationStatus
    latitude_at_verification: float | None = None
    longitude_at_verification: float | None = None


class RequestVerification(RequestVerificationCreate):
    id: str
    volunteer_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class UrgencyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourcingStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_FUNDED = "partially_funded"
    FILLED = "filled"
    CLOSED = "closed"


class ResourceSourcingCreate(BaseModel):
    resource_type: str
    quantity_needed: int
    urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    description: str | None = None


class ResourceSourcing(ResourceSourcingCreate):
    id: str
    ngo_id: str
    status: SourcingStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PledgeStatus(StrEnum):
    PENDING = "pending"
    SHIPPED = "shipped"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class DonorPledgeCreate(BaseModel):
    sourcing_request_id: str | None = None
    quantity_pledged: int = 0
    disaster_id: str | None = None


class DonorPledge(BaseModel):
    id: str
    donor_id: str
    disaster_id: str | None = None
    sourcing_request_id: str | None = None
    quantity_pledged: int = 0
    status: PledgeStatus = PledgeStatus.PENDING
    user_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MobilizationStatus(StrEnum):
    ACTIVE = "active"
    FILLED = "filled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NgoMobilizationCreate(BaseModel):
    title: str
    description: str | None = None
    location_id: str | None = None
    required_volunteers: int = 1


class NgoMobilization(NgoMobilizationCreate):
    id: str
    ngo_id: str
    status: MobilizationStatus
    created_at: datetime

    class Config:
        from_attributes = True


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    ON_SITE = "on_site"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class VolunteerAssignment(BaseModel):
    id: str
    mobilization_id: str
    volunteer_id: str
    status: AssignmentStatus
    assigned_at: datetime
    feedback_notes: str | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class VolunteerProfileUpdate(BaseModel):
    skills: list[str] | None = None
    assets: list[str] | None = None
    availability_status: str | None = None
    bio: str | None = None
    experience: str | None = None
    emergency_contact: str | None = None
    languages: list[str] | None = None


class VolunteerProfile(VolunteerProfileUpdate):
    user_id: str
    updated_at: datetime

    class Config:
        from_attributes = True


class MissionTaskCreate(BaseModel):
    mobilization_id: str
    task_description: str


class MissionTask(MissionTaskCreate):
    id: str
    is_completed: bool
    completed_by: str | None = None
    completed_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class OperationalPulse(BaseModel):
    id: str
    actor_id: str | None
    target_id: str | None
    action_type: str
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
