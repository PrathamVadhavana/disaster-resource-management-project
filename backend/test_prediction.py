import httpx

payload = {
    'location_id': 'loc-test',
    'prediction_type': 'severity',
    'features': {
        'temperature': 30,
        'humidity': 60,
        'wind_speed': 15,
        'pressure': 1013
    }
}

r = httpx.post('http://127.0.0.1:8000/api/predictions', json=payload, timeout=30)
print(r.status_code)
print(r.text)
