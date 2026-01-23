# API Documentation

Complete API reference for the Disaster Management System backend.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: `https://api.yourdomain.com`

## Authentication

All protected endpoints require a Bearer token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

Get a token by logging in via the `/api/auth/login` endpoint.

## Response Format

### Success Response
```json
{
  "data": { /* response data */ },
  "message": "Success message"
}
```

### Error Response
```json
{
  "detail": "Error message"
}
```

## Endpoints

### Authentication

#### POST /api/auth/register

Register a new user.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "John Doe"
}
```

**Response (201):**
```json
{
  "access_token": "eyJhbGciOiJI...",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "user@example.com"
}
```

#### POST /api/auth/login

Login user.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJI...",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "user@example.com"
}
```

#### GET /api/auth/me

Get current user profile.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "viewer",
  "organization": "Relief Org",
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### Disasters

#### GET /api/disasters

Get all disasters with filtering.

**Query Parameters:**
- `status` (optional): active | monitoring | predicted | resolved
- `severity` (optional): low | medium | high | critical
- `type` (optional): earthquake | flood | hurricane | etc.
- `limit` (optional, default: 100): Max results
- `offset` (optional, default: 0): Pagination offset

**Example:**
```
GET /api/disasters?status=active&severity=high&limit=20
```

**Response (200):**
```json
[
  {
    "id": "uuid",
    "type": "earthquake",
    "severity": "high",
    "status": "active",
    "title": "Magnitude 7.2 Earthquake",
    "description": "Major seismic event in coastal region",
    "location_id": "uuid",
    "affected_population": 50000,
    "casualties": 120,
    "estimated_damage": 1500000000,
    "start_date": "2024-01-15T14:30:00Z",
    "end_date": null,
    "created_at": "2024-01-15T14:35:00Z",
    "updated_at": "2024-01-15T14:35:00Z"
  }
]
```

#### GET /api/disasters/{disaster_id}

Get specific disaster by ID.

**Response (200):** Single disaster object

**Response (404):**
```json
{
  "detail": "Disaster not found"
}
```

#### POST /api/disasters

Create a new disaster.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "type": "flood",
  "severity": "medium",
  "title": "Coastal Flooding Event",
  "description": "Heavy rainfall causing widespread flooding",
  "location_id": "uuid",
  "affected_population": 10000,
  "casualties": 5,
  "estimated_damage": 50000000,
  "start_date": "2024-01-20T10:00:00Z"
}
```

**Response (201):** Created disaster object

#### PATCH /api/disasters/{disaster_id}

Update existing disaster.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body (partial update):**
```json
{
  "severity": "high",
  "affected_population": 15000,
  "casualties": 12,
  "status": "monitoring"
}
```

**Response (200):** Updated disaster object

#### GET /api/disasters/{disaster_id}/resources

Get all resources allocated to a disaster.

**Response (200):**
```json
[
  {
    "id": "uuid",
    "type": "water",
    "name": "Bottled Water Supply",
    "quantity": 10000,
    "unit": "liters",
    "status": "deployed",
    "priority": 8
  }
]
```

---

### Predictions

#### POST /api/predictions

Create ML prediction.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "location_id": "uuid",
  "prediction_type": "severity",
  "features": {
    "temperature": 32.5,
    "humidity": 75,
    "wind_speed": 45,
    "pressure": 1010.5
  }
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "location_id": "uuid",
  "prediction_type": "severity",
  "confidence_score": 0.85,
  "predicted_severity": "high",
  "model_version": "1.0.0",
  "created_at": "2024-01-20T15:00:00Z"
}
```

#### GET /api/predictions

Get predictions with filtering.

**Query Parameters:**
- `location_id` (optional): Filter by location
- `prediction_type` (optional): severity | spread | duration | impact
- `limit` (optional, default: 100)

**Response (200):** Array of prediction objects

#### POST /api/predictions/batch

Create multiple predictions.

**Request Body:**
```json
[
  {
    "location_id": "uuid-1",
    "prediction_type": "severity",
    "features": { /* ... */ }
  },
  {
    "location_id": "uuid-2",
    "prediction_type": "spread",
    "features": { /* ... */ }
  }
]
```

**Response (201):** Array of created predictions

---

### Resources

#### GET /api/resources

Get resources with filtering.

**Query Parameters:**
- `location_id` (optional)
- `status` (optional): available | allocated | in_transit | deployed
- `disaster_id` (optional)
- `limit` (optional, default: 100)

**Response (200):**
```json
[
  {
    "id": "uuid",
    "location_id": "uuid",
    "disaster_id": "uuid",
    "type": "medical",
    "name": "Emergency Medical Kit",
    "quantity": 500,
    "unit": "units",
    "status": "allocated",
    "priority": 9,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T12:00:00Z"
  }
]
```

#### POST /api/resources

Create new resource.

**Request Body:**
```json
{
  "location_id": "uuid",
  "type": "food",
  "name": "Emergency Food Rations",
  "quantity": 1000,
  "unit": "meals",
  "priority": 7
}
```

**Response (201):** Created resource object

#### PATCH /api/resources/{resource_id}

Update resource.

**Request Body:**
```json
{
  "quantity": 750,
  "status": "in_transit"
}
```

**Response (200):** Updated resource object

#### POST /api/resources/allocate

Allocate resources to disaster using optimization.

**Request Body:**
```json
{
  "disaster_id": "uuid",
  "required_resources": [
    {
      "type": "water",
      "quantity": 5000,
      "priority": 10
    },
    {
      "type": "medical",
      "quantity": 200,
      "priority": 9
    }
  ]
}
```

**Response (200):**
```json
{
  "disaster_id": "uuid",
  "allocations": [
    {
      "resource_id": "uuid-1",
      "type": "water",
      "quantity": 5000,
      "location": "uuid"
    },
    {
      "resource_id": "uuid-2",
      "type": "medical",
      "quantity": 200,
      "location": "uuid"
    }
  ],
  "optimization_score": 1.0,
  "unmet_needs": []
}
```

#### POST /api/resources/{resource_id}/deallocate

Make resource available again.

**Response (200):**
```json
{
  "message": "Resource deallocated successfully"
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

## Rate Limiting

- **Rate**: 100 requests per minute per IP
- **Burst**: 200 requests
- **Headers**:
  - `X-RateLimit-Limit`: Maximum requests
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset timestamp

## Webhooks

Subscribe to real-time events via Supabase Realtime:

```javascript
const subscription = supabase
  .channel('disasters')
  .on('postgres_changes', 
    { event: '*', schema: 'public', table: 'disasters' },
    (payload) => console.log('Change received!', payload)
  )
  .subscribe()
```

## SDKs & Libraries

### Python
```python
import requests

BASE_URL = "https://api.yourdomain.com"
token = "your-jwt-token"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

response = requests.get(
    f"{BASE_URL}/api/disasters",
    headers=headers
)
```

### JavaScript
```javascript
const BASE_URL = 'https://api.yourdomain.com';
const token = 'your-jwt-token';

const response = await fetch(`${BASE_URL}/api/disasters`, {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const data = await response.json();
```

## Interactive Documentation

Visit `/docs` for interactive Swagger UI documentation where you can:
- Test endpoints
- View request/response schemas
- Generate code samples
- Download OpenAPI specification

---

For more information, see the [GitHub repository](https://github.com/your-repo) or contact support@disaster-management.com.
