# Disaster Management System

A comprehensive AI-powered disaster management platform with real-time monitoring, prediction, and resource allocation capabilities.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Browser                           │
│              (Next.js 14 + TypeScript + Tailwind)           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ HTTPS/WebSocket
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                  Supabase Platform                           │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   Auth     │  │  Database  │  │  Realtime  │            │
│  │  (JWT)     │  │ (Postgres) │  │  (WebSock) │            │
│  └────────────┘  └────────────┘  └────────────┘            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ REST API
                   │
┌──────────────────▼──────────────────────────────────────────┐
│              FastAPI Backend Server                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  ML Models │  │  Resource  │  │   Auth     │            │
│  │ (Sklearn)  │  │ Allocation │  │  Middleware│            │
│  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

## ✨ Features

### Core Features
- **Real-time Disaster Monitoring**: Interactive map with live disaster updates
- **AI Prediction Engine**: Machine learning models for disaster severity, spread, and impact prediction
- **Resource Management**: Intelligent resource allocation and optimization
- **Authentication & Authorization**: Secure user management with role-based access
- **Real-time Updates**: WebSocket-based live data streaming
- **Responsive Design**: Mobile-first, accessible interface

### Technical Features
- Server-side rendering for optimal performance
- Type-safe development with TypeScript
- Real-time data synchronization
- Geospatial data handling with PostGIS
- RESTful API with OpenAPI documentation
- Docker containerization for easy deployment

## 🚀 Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker & Docker Compose (optional)
- Supabase account (free tier available)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd disaster-management-system
```

### 2. Setup Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Run the SQL schema from `database/schema.sql` in the SQL Editor
3. Copy your project URL and anon key from Settings > API

### 3. Configure Environment Variables

#### Frontend (.env.local)

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAPBOX_TOKEN=your-mapbox-token (optional)
```

#### Backend (.env)

Create `backend/.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_PASSWORD=your-db-password
DATABASE_URL=postgresql+asyncpg://postgres:password@db.your-project.supabase.co:5432/postgres
ALLOWED_ORIGINS=http://localhost:3000,https://your-domain.com
DEBUG=true
```

### 4. Install Dependencies

#### Frontend

```bash
cd frontend
npm install
```

#### Backend

```bash
cd backend
pip install -r requirements.txt
```

### 5. Run Development Servers

#### Option A: Using Docker Compose (Recommended)

```bash
docker-compose up
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

#### Option B: Manual Setup

Terminal 1 (Frontend):
```bash
cd frontend
npm run dev
```

Terminal 2 (Backend):
```bash
cd backend
uvicorn main:app --reload
```

## 📁 Project Structure

```
disaster-management-system/
├── frontend/                 # Next.js application
│   ├── src/
│   │   ├── app/             # App router pages
│   │   ├── components/      # React components
│   │   │   ├── ui/         # Base UI components
│   │   │   ├── map/        # Map-related components
│   │   │   ├── dashboard/  # Dashboard components
│   │   │   └── auth/       # Authentication components
│   │   ├── lib/            # Utilities and configurations
│   │   ├── hooks/          # Custom React hooks
│   │   └── types/          # TypeScript types
│   ├── public/             # Static assets
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── Dockerfile
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── routers/        # API route handlers
│   │   │   ├── disasters.py
│   │   │   ├── predictions.py
│   │   │   ├── resources.py
│   │   │   └── auth.py
│   │   ├── services/       # Business logic
│   │   │   └── ml_service.py
│   │   ├── database.py     # Database configuration
│   │   └── schemas.py      # Pydantic models
│   ├── models/             # ML model files (.pkl)
│   ├── tests/              # Test files
│   ├── main.py             # Application entry point
│   ├── requirements.txt
│   └── Dockerfile
├── database/
│   └── schema.sql          # Database schema
├── docs/                   # Additional documentation
├── docker-compose.yml
└── README.md
```

## 🗄️ Database Schema

### Tables

- **locations**: Geographic locations with coordinates
- **disasters**: Disaster events and details
- **resources**: Available resources and their status
- **predictions**: ML model predictions
- **users**: User profiles and roles

### Key Relationships

```
locations ─┬─< disasters
           └─< resources
                  └─< predictions

disasters ──< resources (allocated)
```

## 🔌 API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout user

### Disasters
- `GET /api/disasters` - List all disasters
- `GET /api/disasters/{id}` - Get disaster by ID
- `POST /api/disasters` - Create disaster
- `PATCH /api/disasters/{id}` - Update disaster
- `GET /api/disasters/{id}/resources` - Get disaster resources

### Predictions
- `POST /api/predictions` - Create prediction
- `GET /api/predictions` - List predictions
- `POST /api/predictions/batch` - Batch predictions

### Resources
- `GET /api/resources` - List resources
- `POST /api/resources` - Create resource
- `PATCH /api/resources/{id}` - Update resource
- `POST /api/resources/allocate` - Allocate resources
- `POST /api/resources/{id}/deallocate` - Deallocate resource

Full API documentation available at: `http://localhost:8000/docs`

## 🤖 Machine Learning Models

### Severity Predictor
Predicts disaster severity based on environmental factors:
- Temperature
- Wind speed
- Humidity
- Atmospheric pressure

### Spread Predictor
Estimates disaster spread area:
- Current affected area
- Wind direction and speed
- Terrain type

### Impact Predictor
Forecasts disaster impact:
- Estimated casualties
- Economic damage
- Affected population

### Model Training

```python
# Example: Train severity predictor
from sklearn.ensemble import RandomForestClassifier
import pandas as pd
import joblib

# Load training data
data = pd.read_csv('disaster_historical_data.csv')

# Features and target
X = data[['temperature', 'wind_speed', 'humidity', 'pressure']]
y = data['severity']

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X, y)

# Save model
joblib.dump(model, 'models/severity_predictor.pkl')
```

## 🔒 Security

### Authentication
- JWT-based authentication via Supabase Auth
- Secure password hashing with bcrypt
- Token refresh mechanism

### Authorization
- Row Level Security (RLS) in Supabase
- Role-based access control (RBAC)
- API rate limiting

### Data Protection
- HTTPS encryption in production
- Environment variable management
- CORS configuration
- Input validation and sanitization

## 🧪 Testing

### Frontend Tests

```bash
cd frontend
npm test
```

### Backend Tests

```bash
cd backend
pytest
pytest --cov=app tests/  # With coverage
```

### E2E Tests

```bash
npm run test:e2e
```

## 🚢 Deployment

### Vercel (Frontend)

1. Connect your GitHub repository to Vercel
2. Configure environment variables
3. Deploy automatically on push

### Railway/Fly.io (Backend)

```bash
# Using Railway
railway login
railway init
railway up

# Using Fly.io
flyctl launch
flyctl deploy
```

### Supabase (Database)

Already hosted on Supabase cloud - configure connection strings in your deployment platform.

## 📊 Monitoring

### Application Monitoring
- Sentry for error tracking
- LogRocket for session replay
- Custom analytics dashboard

### Performance Monitoring
- Next.js Analytics
- FastAPI built-in profiling
- Supabase dashboard metrics

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📝 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Next.js team for the amazing framework
- FastAPI for the high-performance backend framework
- Supabase for the complete backend platform
- OpenStreetMap for map data

## 📞 Support

For support, email support@disaster-management.com or join our Slack channel.

## 🗺️ Roadmap

- [ ] Mobile application (React Native)
- [ ] Advanced ML models (deep learning)
- [ ] Integration with weather APIs
- [ ] SMS/Email notification system
- [ ] Multi-language support
- [ ] Offline mode
- [ ] Advanced data visualization
- [ ] Drone integration for real-time monitoring

---

**Built with ❤️ for disaster preparedness and response**
