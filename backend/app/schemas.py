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
            required = ['current_area', 'wind_direction', 'terrain_type']
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
    predicted_severity: Optional[DisasterSeverity]
    predicted_start_date: Optional[datetime]
    predicted_casualties: Optional[int]
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


class AllocationRequest(BaseModel):
    disaster_id: str
    required_resources: List[Dict[str, Any]] = Field(
        ...,
        description="List of required resources with type, quantity, and priority"
    )


class AllocationResponse(BaseModel):
    disaster_id: str
    allocations: List[Dict[str, Any]]
    optimization_score: float
    unmet_needs: List[Dict[str, Any]]


class UserLogin(BaseModel):
    email: str
    password: str


class UserRegister(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
