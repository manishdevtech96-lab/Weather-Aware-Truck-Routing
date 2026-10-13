import { useState } from 'react'
import { analyzeTrip, reversePlace } from './api'
import PlaceField from './PlaceField'
import RouteMap, { RISK_COLORS } from './RouteMap'

const durationLabel = (seconds) =>
  `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`

function toOffsetIso(localValue) {
  const parsed = new Date(localValue)
  const offsetMinutes = -parsed.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absolute = Math.abs(offsetMinutes)
  const hours = String(Math.floor(absolute / 60)).padStart(2, '0')
  const minutes = String(absolute % 60).padStart(2, '0')
  return `${localValue}:00${sign}${hours}:${minutes}`
}

const CHICAGO = { label: 'Chicago, Illinois, United States', latitude: 41.878113, longitude: -87.629799 }
const INDIANAPOLIS = { label: 'Indianapolis, Indiana, United States', latitude: 39.768403, longitude: -86.158068 }

export default function App() {
  const [origin, setOrigin] = useState(CHICAGO)
  const [destination, setDestination] = useState(INDIANAPOLIS)
  const [form, setForm] = useState({
    departure_time: '',
    load_weight_lb: '45000',
    checkpoint_interval_miles: '25',
  })
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [hour, setHour] = useState(0)
  const [pickTarget, setPickTarget] = useState(null)
  const [focusPoint, setFocusPoint] = useState(null)

  const change = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  function rememberPlace(place) {
    setFocusPoint({ ...place, key: Date.now() })
  }

  async function handleMapPick(point) {
    if (!pickTarget) return
    const target = pickTarget
    try {
      const place = await reversePlace(point.latitude, point.longitude)
      if (target === 'origin') setOrigin(place)
      else setDestination(place)
      rememberPlace(place)
      setPickTarget(target === 'origin' ? 'destination' : null)
      setError('')
    } catch (err) {
      setError(err.response?.data?.error || 'Could not identify that map point.')
    }
  }

  async function submit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setData(null)
    try {
      if (!form.departure_time) {
        throw new Error('Please select a departure date and time.')
      }
      const result = await analyzeTrip({
        ...form,
        origin: origin.label,
        destination: destination.label,
        ...(origin.latitude != null && origin.longitude != null
          ? { origin_latitude: origin.latitude, origin_longitude: origin.longitude }
          : {}),
        ...(destination.latitude != null && destination.longitude != null
          ? { destination_latitude: destination.latitude, destination_longitude: destination.longitude }
          : {}),
        departure_time: toOffsetIso(form.departure_time),
        load_weight_lb: Number(form.load_weight_lb),
        checkpoint_interval_miles: Number(form.checkpoint_interval_miles),
      })
      setHour(0)
      setData(result)
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Request failed.')
    } finally {
      setLoading(false)
    }
  }

  const routes = data?.routes || []

  return (
    <main className="shell">
      <header>
        <div className="logo">WR</div>
        <div>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Forecast-aware route planning for safer journeys</p>
        </div>
        <span className="pill">ROUTE SAFETY</span>
      </header>

      <section className="intro">
        <span>TRIP PLANNER</span>
        <h2>Find a safer way forward.</h2>
        <p>Compare route alternatives using weather, load weight, and estimated arrival times.</p>
      </section>

      <div className="layout">
        <aside className="panel sidebar">
          <h3>Trip details</h3>
          <p className="sub">Enter your journey information</p>
          <form onSubmit={submit}>
            <PlaceField
              label="Origin"
              value={origin.label}
              onChange={(label) => setOrigin({ label, latitude: null, longitude: null })}
              onSelect={(place) => {
                setOrigin(place)
                rememberPlace(place)
              }}
            />
            <PlaceField
              label="Destination"
              value={destination.label}
              onChange={(label) => setDestination({ label, latitude: null, longitude: null })}
              onSelect={(place) => {
                setDestination(place)
                rememberPlace(place)
              }}
            />
            <div className="pick-row">
              <button
                type="button"
                className={pickTarget === 'origin' ? 'active' : ''}
                onClick={() => setPickTarget(pickTarget === 'origin' ? null : 'origin')}
              >
                Set origin on map
              </button>
              <button
                type="button"
                className={pickTarget === 'destination' ? 'active' : ''}
                onClick={() => setPickTarget(pickTarget === 'destination' ? null : 'destination')}
              >
                Set destination on map
              </button>
            </div>
            <p className="pick-hint">
              {pickTarget === 'origin'
                ? 'Click the map to drop the origin. The next click sets the destination.'
                : pickTarget === 'destination'
                  ? 'Click the map to drop the destination.'
                  : 'Type for suggestions, or choose a pin and click the map. A is origin, B is destination.'}
            </p>
            <label>
              Departure date & time
              <input
                required
                type="datetime-local"
                value={form.departure_time}
                onChange={(event) => change('departure_time', event.target.value)}
              />
            </label>
            <label>
              Load weight (lb)
              <input
                required
                type="number"
                min="0"
                value={form.load_weight_lb}
                onChange={(event) => change('load_weight_lb', event.target.value)}
              />
            </label>
            <label>
              Checkpoint interval
              <select
                value={form.checkpoint_interval_miles}
                onChange={(event) => change('checkpoint_interval_miles', event.target.value)}
              >
                <option value="10">Every 10 miles</option>
                <option value="25">Every 25 miles</option>
                <option value="50">Every 50 miles</option>
              </select>
            </label>
            <button className="primary" disabled={loading}>
              {loading ? 'Analyzing routes…' : 'Analyze routes'} <b>→</b>
            </button>
          </form>
          {error && <div className="error">{error}</div>}
          {data?.warnings && (
            <details className="warning">
              <summary>Forecast notes</summary>
              <ul>
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          <h4>Risk legend</h4>
          <div className="legend">
            {Object.entries(RISK_COLORS).map(([level, color]) => (
              <span key={level}>
                <i style={{ background: color }} />
                {level}
              </span>
            ))}
          </div>
        </aside>

        <section className="content">
          <div className="panel map-panel">
            <div className="panel-head">
              <div>
                <h3>Route overview</h3>
                <p>{data ? `${routes.length} routes analyzed` : 'Your route options will appear here'}</p>
              </div>
              <span className="live">● Interactive map</span>
            </div>
            <RouteMap
              routes={routes}
              hour={hour}
              origin={origin}
              destination={destination}
              pickTarget={pickTarget}
              focusPoint={routes.length > 0 ? focusPoint : null}
              onPick={handleMapPick}
            />
            <div className="map-legend">
              <span>A origin</span>
              <span>B destination</span>
              <span>Blue casing: recommended route</span>
              <span>Corridor color: forecast risk at +{hour}h</span>
            </div>
          </div>

          <div className="panel forecast">
            <div className="panel-head">
              <div>
                <h3>Weather forecast timeline</h3>
                <p>Color the trip corridor by conditions from departure through 48 hours</p>
              </div>
              <b>+{hour} hours</b>
            </div>
            <input
              type="range"
              min="0"
              max="48"
              value={hour}
              onChange={(event) => setHour(Number(event.target.value))}
            />
            <div className="slider-labels">
              <span>Departure · 0h</span>
              <span>24h</span>
              <span>48h</span>
            </div>
            <p className="note">
              Route scores use weather at each checkpoint&apos;s estimated arrival. Drag the slider to
              see how risk along the same corridor changes over the next 48 hours.
            </p>
          </div>

          <div className="results-head">
            <div>
              <h3>Route comparison</h3>
              <p>Severe miles, then high miles, then average risk, then travel time</p>
            </div>
          </div>

          {!data && (
            <div className="panel empty">
              <h3>Your route analysis will show here</h3>
              <p>Submit trip details to compare route risk, distance, and travel time.</p>
            </div>
          )}

          <div className="cards">
            {routes.map((route, index) => (
              <article key={route.id} className={`panel route-card ${route.is_recommended ? 'best' : ''}`}>
                <div className="card-top">
                  <span>ROUTE 0{index + 1}</span>
                  <b>{route.is_recommended ? 'BEST MATCH' : 'ALTERNATIVE'}</b>
                </div>
                <h3>{route.name}</h3>
                <p>
                  {route.distance_miles} miles · {durationLabel(route.duration_seconds)}
                </p>
                <div className="metrics">
                  <div>
                    <span>Severe miles</span>
                    <b>{route.summary.severe_miles}</b>
                  </div>
                  <div>
                    <span>High miles</span>
                    <b>{route.summary.high_miles}</b>
                  </div>
                  <div>
                    <span>Average risk</span>
                    <b>{route.summary.average_risk_score ?? 'N/A'}</b>
                  </div>
                  <div>
                    <span>No Travel</span>
                    <b className={route.summary.no_travel_miles ? 'danger' : ''}>
                      {route.summary.no_travel_miles} mi
                    </b>
                  </div>
                </div>
                <div className="coverage">
                  <span>Forecast coverage</span>
                  <b>{route.summary.forecast_coverage_percent}%</b>
                </div>
                <div className="track">
                  <i style={{ width: `${route.summary.forecast_coverage_percent}%` }} />
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
      <footer>Assignment prototype · Forecasts are estimates, not a safety guarantee.</footer>
    </main>
  )
}
