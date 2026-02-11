#!/usr/bin/env node
/**
 * Frontend API Integration Smoke Test
 * Verifies that the frontend can communicate with the local backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8004';

async function testFrontendBackendIntegration() {
  console.log(`Testing Frontend ↔ Backend Integration`);
  console.log(`Backend URL: ${API_URL}\n`);

  let passed = 0;
  let failed = 0;

  // Test 1: Health check
  try {
    console.log('[1] Testing /health endpoint...');
    const res = await fetch(`${API_URL}/health`);
    if (res.status === 200) {
      const data = await res.json();
      if (data.status === 'healthy' && data.ml_models_loaded === true) {
        console.log('✅ Health check passed\n');
        passed++;
      } else {
        console.log('❌ Unexpected health data:', data, '\n');
        failed++;
      }
    } else {
      console.log(`❌ Health check failed with status ${res.status}\n`);
      failed++;
    }
  } catch (e) {
    console.log(`❌ Health check error: ${e.message}\n`);
    failed++;
  }

  // Test 2: Create prediction
  try {
    console.log('[2] Testing POST /api/predictions...');
    const payload = {
      location_id: 'integration-test',
      prediction_type: 'severity',
      features: {
        temperature: 25,
        humidity: 60,
        wind_speed: 8,
        pressure: 1010,
      },
    };

    const res = await fetch(`${API_URL}/api/predictions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.status === 201) {
      const data = await res.json();
      if (data.id && data.location_id === payload.location_id) {
        console.log(`✅ Prediction created: ${data.id}\n`);
        passed++;
      } else {
        console.log(`❌ Unexpected response data: ${JSON.stringify(data)}\n`);
        failed++;
      }
    } else {
      console.log(`❌ Create prediction failed with status ${res.status}\n`);
      failed++;
    }
  } catch (e) {
    console.log(`❌ Create prediction error: ${e.message}\n`);
    failed++;
  }

  // Test 3: Fetch predictions
  try {
    console.log('[3] Testing GET /api/predictions...');
    const res = await fetch(`${API_URL}/api/predictions?location_id=integration-test`);
    if (res.status === 200) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        console.log(`✅ Fetched ${data.length} prediction(s)\n`);
        passed++;
      } else {
        console.log(`❌ Expected array with data, got: ${JSON.stringify(data)}\n`);
        failed++;
      }
    } else {
      console.log(`❌ Fetch predictions failed with status ${res.status}\n`);
      failed++;
    }
  } catch (e) {
    console.log(`❌ Fetch predictions error: ${e.message}\n`);
    failed++;
  }

  // Summary
  console.log('─'.repeat(50));
  console.log(`Results: ${passed} passed, ${failed} failed`);
  console.log('─'.repeat(50));

  if (failed === 0) {
    console.log(`\n✅ Frontend ↔ Backend integration is working!`);
    console.log(`Frontend: http://localhost:3000`);
    console.log(`Backend:  ${API_URL}`);
    process.exit(0);
  } else {
    console.log(`\n❌ Integration test failed.`);
    process.exit(1);
  }
}

testFrontendBackendIntegration();
