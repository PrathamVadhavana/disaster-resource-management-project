# Development Guide

Guide for developers contributing to the Disaster Management System.

## Development Environment Setup

### Required Tools

- Node.js 20+ and npm
- Python 3.11+
- Git
- Docker Desktop (optional but recommended)
- VS Code (recommended) or your preferred IDE

### Recommended VS Code Extensions

```json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "bradlc.vscode-tailwindcss",
    "streetsidesoftware.code-spell-checker",
    "eamodio.gitlens"
  ]
}
```

## Code Style & Standards

### TypeScript/JavaScript

- Use TypeScript for all new files
- Follow Airbnb style guide
- Use functional components with hooks
- Prefer async/await over promises
- Use meaningful variable names

**Example:**
```typescript
// Good
const fetchDisasterData = async (disasterId: string): Promise<Disaster> => {
  const response = await supabase
    .from('disasters')
    .select('*')
    .eq('id', disasterId)
    .single();
  
  if (response.error) throw response.error;
  return response.data;
};

// Avoid
const getData = async (id) => {
  const res = await supabase.from('disasters').select('*').eq('id', id).single();
  return res.data;
};
```

### Python

- Follow PEP 8 style guide
- Use type hints
- Write docstrings for functions
- Use async/await for I/O operations
- Keep functions focused and small

**Example:**
```python
# Good
async def get_disaster_by_id(disaster_id: str) -> Dict[str, Any]:
    """
    Retrieve a disaster by its ID.
    
    Args:
        disaster_id: UUID of the disaster
        
    Returns:
        Dictionary containing disaster data
        
    Raises:
        HTTPException: If disaster not found
    """
    response = supabase.table("disasters").select("*").eq("id", disaster_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Disaster not found")
    
    return response.data[0]
```

## Project Structure Guidelines

### Frontend

```
src/
├── app/              # Next.js app router
│   ├── (auth)/      # Auth route group
│   ├── (dashboard)/ # Dashboard route group
│   └── api/         # API routes
├── components/
│   ├── ui/          # Reusable UI components
│   ├── features/    # Feature-specific components
│   └── layout/      # Layout components
├── lib/             # Utilities, helpers
├── hooks/           # Custom React hooks
└── types/           # TypeScript types
```

### Backend

```
app/
├── routers/         # API route handlers
├── services/        # Business logic
├── models/          # Database models (if using ORM)
├── schemas/         # Pydantic schemas
├── utils/           # Helper functions
└── middleware/      # Custom middleware
```

## Component Development

### Creating a New Component

1. Create component file in appropriate directory
2. Add TypeScript types
3. Write component logic
4. Add tests
5. Export from index file

**Template:**
```typescript
// components/features/disaster-card.tsx
import { FC } from 'react';
import { Disaster } from '@/types/supabase';

interface DisasterCardProps {
  disaster: Disaster;
  onClick?: (id: string) => void;
}

export const DisasterCard: FC<DisasterCardProps> = ({ disaster, onClick }) => {
  return (
    <div 
      className="p-4 border rounded-lg cursor-pointer hover:shadow-lg transition"
      onClick={() => onClick?.(disaster.id)}
    >
      <h3 className="font-bold text-lg">{disaster.title}</h3>
      <p className="text-muted-foreground">{disaster.type}</p>
      {/* ... */}
    </div>
  );
};
```

### Component Best Practices

- Keep components small and focused
- Use composition over inheritance
- Extract reusable logic into hooks
- Memoize expensive computations
- Handle loading and error states
- Make components accessible (ARIA labels)

## State Management

### Client State (React Query)

```typescript
// hooks/use-disasters.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';

export const useDisasters = () => {
  return useQuery({
    queryKey: ['disasters'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('disasters')
        .select('*')
        .order('created_at', { ascending: false });
      
      if (error) throw error;
      return data;
    },
  });
};

export const useCreateDisaster = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (disaster: DisasterCreate) => {
      const { data, error } = await supabase
        .from('disasters')
        .insert(disaster)
        .select()
        .single();
      
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['disasters'] });
    },
  });
};
```

### Server State (Supabase)

Use Supabase for:
- Authentication state
- Database subscriptions
- Real-time updates

## API Development

### Creating a New Endpoint

1. Define Pydantic schema
2. Create router function
3. Add error handling
4. Write tests
5. Document in OpenAPI

**Example:**
```python
# app/routers/locations.py
from fastapi import APIRouter, HTTPException
from app.schemas import Location, LocationCreate

router = APIRouter()

@router.post("/", response_model=Location)
async def create_location(location: LocationCreate):
    """Create a new location."""
    try:
        response = supabase.table("locations").insert(
            location.model_dump()
        ).execute()
        
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create")
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Testing

### Frontend Tests

```typescript
// __tests__/components/disaster-card.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { DisasterCard } from '@/components/features/disaster-card';

describe('DisasterCard', () => {
  const mockDisaster = {
    id: '123',
    title: 'Test Disaster',
    type: 'earthquake',
    severity: 'high',
    // ...
  };

  it('renders disaster information', () => {
    render(<DisasterCard disaster={mockDisaster} />);
    
    expect(screen.getByText('Test Disaster')).toBeInTheDocument();
    expect(screen.getByText('earthquake')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const handleClick = jest.fn();
    render(<DisasterCard disaster={mockDisaster} onClick={handleClick} />);
    
    fireEvent.click(screen.getByText('Test Disaster'));
    expect(handleClick).toHaveBeenCalledWith('123');
  });
});
```

### Backend Tests

```python
# tests/test_disasters.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_disasters():
    response = client.get("/api/disasters")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_disaster():
    disaster_data = {
        "type": "earthquake",
        "severity": "high",
        "title": "Test Earthquake",
        "location_id": "uuid",
        "start_date": "2024-01-01T00:00:00Z"
    }
    
    response = client.post("/api/disasters", json=disaster_data)
    assert response.status_code == 201
    assert response.json()["title"] == "Test Earthquake"
```

## Git Workflow

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation updates

### Commit Messages

Follow conventional commits:

```
type(scope): subject

body

footer
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

**Examples:**
```
feat(disasters): add severity filter to disaster list

Added ability to filter disasters by severity level in the disaster
list component. Includes UI controls and API parameter support.

Closes #123
```

### Pull Request Process

1. Create feature branch
2. Make changes with descriptive commits
3. Write/update tests
4. Update documentation
5. Create PR with description
6. Address review comments
7. Squash and merge

## Database Migrations

### Creating a Migration

1. Make schema changes in Supabase SQL Editor
2. Export migration:
```sql
-- Save as migrations/YYYYMMDD_description.sql
ALTER TABLE disasters ADD COLUMN new_field TEXT;
```

3. Document in migration log
4. Test on development database
5. Apply to production

## Performance Optimization

### Frontend

- Use `React.memo` for expensive components
- Implement virtual scrolling for large lists
- Lazy load routes and components
- Optimize images (use Next.js Image component)
- Minimize bundle size

```typescript
// Lazy loading
const HeavyComponent = dynamic(() => import('./HeavyComponent'), {
  loading: () => <Skeleton />,
  ssr: false
});
```

### Backend

- Use database indexes
- Implement caching (Redis)
- Batch database operations
- Use async operations
- Profile slow endpoints

```python
# Caching example
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_location_cached(location_id: str):
    # Expensive operation
    pass
```

## Security Best Practices

### Frontend

- Never expose secret keys
- Sanitize user input
- Use HTTPS only
- Implement CSRF protection
- Validate on client AND server

### Backend

- Use parameterized queries
- Validate all inputs
- Implement rate limiting
- Hash passwords properly
- Use environment variables for secrets
- Keep dependencies updated

## Debugging

### Frontend Debugging

```typescript
// Use React DevTools
// Add breakpoints in browser DevTools
// Use console.log strategically

if (process.env.NODE_ENV === 'development') {
  console.log('Debug info:', data);
}
```

### Backend Debugging

```python
# Use pdb for debugging
import pdb; pdb.set_trace()

# Or use logging
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Processing disaster: {disaster_id}")
```

## Code Review Checklist

- [ ] Code follows style guide
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No hardcoded secrets
- [ ] Error handling implemented
- [ ] Performance considered
- [ ] Accessibility checked
- [ ] Security reviewed

## Resources

- [Next.js Docs](https://nextjs.org/docs)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Supabase Docs](https://supabase.com/docs)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Python Best Practices](https://peps.python.org/pep-0008/)

## Getting Help

- Check existing issues on GitHub
- Review documentation
- Ask in project Discord/Slack
- Create detailed bug reports

---

Happy coding! 🚀
