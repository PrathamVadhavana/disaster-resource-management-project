/**
 * Frontend → Backend API Integration Test
 * Tests that the frontend can successfully communicate with the local FastAPI backend
 */

describe('Frontend API Integration', () => {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8004';

  test('backend health check endpoint responds', async () => {
    const response = await fetch(`${API_URL}/health`);
    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.status).toBe('healthy');
    expect(data.ml_models_loaded).toBe(true);
  });

  test('create prediction endpoint accepts severity prediction', async () => {
    const payload = {
      location_id: 'test-loc-frontend',
      prediction_type: 'severity',
      features: {
        temperature: 24,
        humidity: 58,
        wind_speed: 10,
        pressure: 1011,
      },
    };

    const response = await fetch(`${API_URL}/api/predictions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    expect(response.status).toBe(201);
    const data = await response.json();
    expect(data.location_id).toBe(payload.location_id);
    expect(data.prediction_type).toBe(payload.prediction_type);
    expect(data.id).toBeDefined();
  });

  test('fetch predictions by location_id', async () => {
    const locationId = 'test-loc-frontend';

    const response = await fetch(`${API_URL}/api/predictions?location_id=${locationId}`, {
      method: 'GET',
    });

    expect(response.status).toBe(200);
    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
    // Should have at least one from the previous test
    expect(data.length).toBeGreaterThan(0);
  });
});
