import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
  timeout: 120000,
})

export async function analyzeTrip(payload) {
  const response = await client.post('/trips/analyze/', payload)
  return response.data
}

export async function suggestPlaces(query) {
  const response = await client.get('/places/suggest/', { params: { q: query } })
  return response.data.places
}

export async function reversePlace(latitude, longitude) {
  const response = await client.get('/places/reverse/', { params: { latitude, longitude } })
  return response.data
}
