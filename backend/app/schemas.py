from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class DisasterType(str, Enum):
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


class DisasterSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DisasterStatus(str, Enum):
    PREDICTED = "predicted"
    ACTIVE = "active"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class ResourceType(str, Enum):
    FOOD = "food"
    WATER = "water"
    MEDICAL = "medical"
    SHELTER = "shelter"
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    OTHER = "other"


class ResourceStatus(str, Enum):
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    IN_TRANSIT = "in_transit"
    DEPLOYED = "deployed"


class PredictionType(str, Enum):
    SEVERITY = "severity"
    SPREAD = "spread"
    DURATION = "duration"
    IMPACT = "impact"


class LocationBase(BaseModel):
    name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    city: str
    state: str
    country: str
    population: Optional[int] = None


class LocationCreate(LocationBase):
    pass


class Location(LocationBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DisasterBase(BaseModel):
    type: DisasterType
    severity: DisasterSeverity
    title: str
    description: Optional[str] = None
    location_id: str
    affected_population: Optional[int] = None
    casualties: Optional[int] = None
    estimated_damage: Optional[float] = None
    start_date: datetime


class DisasterCreate(DisasterBase):
    pass


class DisasterUpdate(BaseModel):
    severity: Optional[DisasterSeverity] = None
    status: Optional[DisasterStatus] = None
    description: Optional[str] = None
    affected_population: Optional[int] = None
    casualties: Optional[int] = None
    estimated_damage: Optional[float] = None
    end_date: Optional[datetime] = None


class Disaster(DisasterBase):
    id: str
    created_at: datetime
    updated_at: datetime
    status: DisasterStatus
    end_date: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PredictionInput(BaseModel):
    location_id: str
    prediction_type: PredictionType
    features: Dict[str, Any] = Field(
        ...,
        description="Feature dict for ML model. Required fields vary by prediction type."
    )

    @validator('features')
    def validate_features(cls, v, values):
        prediction_type = values.get('prediction_type')
        
        if prediction_type == PredictionType.SEVERITY:
            required = ['temperature', 'humidity', 'wind_speed', 'pressure']
        elif prediction_type == PredictionType.SPREAD:
            required = ['current_area', 'wind_speed', 'terrain_type']
        elif prediction_type == PredictionType.IMPACT:
            required = ['severity_score', 'affected_population']
        else:
            required = []
        
        for field in required:
            if field not in v:
                raise ValueError(f"Missing required feature: {field}")
        
        return v


class PredictionResponse(BaseModel):
    id: str
    location_id: str
    prediction_type: PredictionType
    confidence_score: float
    predicted_severity: Optional[DisasterSeverity] = None
    predicted_start_date: Optional[datetime] = None
    predicted_casualties: Optional[int] = None
    predicted_area_km2: Optional[float] = None
    ci_lower_km2: Optional[float] = None
    ci_upper_km2: Optional[float] = None
    predicted_damage_usd: Optional[float] = None
    model_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResourceBase(BaseModel):
    location_id: str
    type: ResourceType
    name: str
    quantity: float
    unit: str
    priority: int = Field(default=5, ge=1, le=10)


class ResourceCreate(ResourceBase):
    disaster_id: Optional[str] = None


class ResourceUpdate(BaseModel):
    quantity: Optional[float] = None
    status: Optional[ResourceStatus] = None
    allocated_to: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=10)


class Resource(ResourceBase):
    id: str
    created_at: datetime
    updated_at: datetime
    disaster_id: Optional[str]
    status: ResourceStatus
    allocated_to: Optional[str]

    class Config:
        from_attributes = True


class PriorityWeightsSchema(BaseModel):
    """Tunable weights for the allocation objective function."""
    urgency_weight: float = Field(1.0, ge=0, description="Weight for urgency score")
    distance_weight: float = Field(0.3, ge=0, description="Penalty weight for delivery distance")
    expiry_weight: float = Field(0.2, ge=0, description="Bonus weight for soon-to-expire resources")
    coverage_weight: float = Field(1.0, ge=0, description="Weight for overall coverage")


class AllocationRequest(BaseModel):
    disaster_id: str
    required_resources: List[Dict[str, Any]] = Field(
        ...,
        description="List of required resources with type, quantity, and priority"
    )
    priority_weights: Optional[PriorityWeightsSchema] = Field(
        None,
        description="Optional objective-function weights (defaults used when omitted)"
    )
    max_distance_km: float = Field(
        500.0, gt=0,
        description="Maximum delivery distance in km — resources further away are excluded"
    )


class OptimizationScoreBreakdown(BaseModel):
    """Detailed breakdown of the optimisation result."""
    coverage_pct: float = Field(0, description="Percentage of requirements met (0-100)")
    unmet_needs: List[Dict[str, Any]] = Field(default_factory=list)
    estimated_delivery_km: float = Field(0, description="Total delivery distance across all allocations (km)")
    solver_status: str = Field("not_solved", description="LP solver exit status")


class AllocationResponse(BaseModel):
    disaster_id: str
    allocations: List[Dict[str, Any]]
    optimization_score: float
    unmet_needs: List[Dict[str, Any]]
    score_breakdown: Optional[OptimizationScoreBreakdown] = None


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
    items: List[ForecastItemSchema] = Field(default_factory=list)



class UserRole(str, Enum):
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
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: UserRole = UserRole.VICTIM


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str


# ============================================================
# Victim Module Schemas
# ============================================================

class VictimResourceType(str, Enum):
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


class RequestPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ResourceItem(BaseModel):
    resource_type: str
    quantity: int = Field(default=1, ge=1)
    custom_name: Optional[str] = None


class ResourceRequestCreate(BaseModel):
    resource_type: Optional[VictimResourceType] = None  # primary type (auto-set from items)
    quantity: int = Field(default=1, ge=1)
    items: List[ResourceItem] = Field(default_factory=list)
    description: Optional[str] = None
    priority: RequestPriority = RequestPriority.MEDIUM
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    address_text: Optional[str] = None
    attachments: Optional[List[str]] = Field(default_factory=list)


class ResourceRequestUpdate(BaseModel):
    resource_type: Optional[VictimResourceType] = None
    quantity: Optional[int] = Field(None, ge=1)
    items: Optional[List[ResourceItem]] = None
    description: Optional[str] = None
    priority: Optional[RequestPriority] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    address_text: Optional[str] = None
    attachments: Optional[List[str]] = None


class ResourceRequestResponse(BaseModel):
    id: str
    victim_id: str
    resource_type: str
    quantity: int
    items: Optional[List[Dict]] = Field(default_factory=list)
    description: Optional[str] = None
    priority: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_text: Optional[str] = None
    status: str
    assigned_to: Optional[str] = None
    assigned_role: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    attachments: Optional[List[str]] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResourceRequestListResponse(BaseModel):
    requests: List[ResourceRequestResponse]
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
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_priority: Dict[str, int] = Field(default_factory=dict)


class VictimProfileResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str
    current_status: Optional[str] = None
    needs: Optional[List[str]] = None
    medical_needs: Optional[str] = None
    location_lat: Optional[float] = None
    location_long: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class VictimProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    current_status: Optional[str] = None
    needs: Optional[List[str]] = None
    medical_needs: Optional[str] = None
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_long: Optional[float] = Field(None, ge=-180, le=180)
