import { useEffect, useMemo } from 'react'
import { divIcon } from 'leaflet'
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import { sliceRouteSegments } from './geo'

const RISK_COLORS = {
  Low: '#16a34a',
  Moderate: '#eab308',
  High: '#f97316',
  Severe: '#dc2626',
  'No Travel': '#7f1d1d',
  Unknown: '#64748b',
}

const ROUTE_COLORS = ['#64748b', '#8b5cf6', '#0d9488']

const pinIcon = (letter, kind) =>
  divIcon({
    className: `pin pin-${kind}`,
    html: `<span>${letter}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })

const originIcon = pinIcon('A', 'origin')
const destinationIcon = pinIcon('B', 'destination')

function FitRoutes({ routes }) {
  const map = useMap()
  const signature = routes.map((route) => `${route.id}:${route.distance_miles}`).join('|')

  useEffect(() => {
    const points = routes.flatMap((route) =>
      (route.geometry || []).map(([longitude, latitude]) => [latitude, longitude]),
    )
    if (points.length > 0) {
      map.fitBounds(points, { padding: [28, 28] })
    }
  }, [map, signature, routes])

  return null
}

function FitEndpoints({ routes, origin, destination }) {
  const map = useMap()
  const signature = [origin, destination]
    .filter(Boolean)
    .map((place) => `${place.latitude},${place.longitude}`)
    .join('|')

  useEffect(() => {
    if (routes.length > 0) return
    const points = [origin, destination]
      .filter((place) => place?.latitude != null && place?.longitude != null)
      .map((place) => [place.latitude, place.longitude])
    if (points.length === 2) map.fitBounds(points, { padding: [48, 48], maxZoom: 8 })
    else if (points.length === 1) map.setView(points[0], 8)
  }, [map, routes.length, signature, origin, destination])

  return null
}

function MapClick({ enabled, onPick }) {
  useMapEvents({
    click(event) {
      if (!enabled) return
      onPick({ latitude: event.latlng.lat, longitude: event.latlng.lng })
    },
  })
  return null
}

function PanTo({ point }) {
  const map = useMap()
  useEffect(() => {
    if (!point) return
    map.panTo([point.latitude, point.longitude])
  }, [map, point])
  return null
}

function riskAtHour(timeline, hour, fallback) {
  if (!timeline || timeline.length === 0) return fallback || 'Unknown'
  return timeline[Math.min(hour, timeline.length - 1)] || 'Unknown'
}

function EndpointMarker({ place, icon, title }) {
  if (place?.latitude == null || place?.longitude == null) return null
  return (
    <Marker position={[place.latitude, place.longitude]} icon={icon} zIndexOffset={1000}>
      <Popup>
        <b>{title}</b>
        <p>{place.label}</p>
      </Popup>
    </Marker>
  )
}

export default function RouteMap({ routes, hour, origin, destination, pickTarget, focusPoint, onPick }) {
  const center = routes[0]?.geometry?.length
    ? [routes[0].geometry[0][1], routes[0].geometry[0][0]]
    : [39.5, -98.35]

  const segments = useMemo(
    () =>
      routes.flatMap((route, index) =>
        sliceRouteSegments(route).map((segment) => ({
          ...segment,
          recommended: Boolean(route.is_recommended),
          casing: route.is_recommended ? '#2563eb' : ROUTE_COLORS[index % ROUTE_COLORS.length],
          routeName: route.name,
        })),
      ),
    [routes],
  )

  return (
    <div className={`map-wrap${pickTarget ? ' picking' : ''}`}>
      {pickTarget && (
        <div className="pick-banner">
          Click the map to set {pickTarget === 'origin' ? 'the origin' : 'the destination'}
        </div>
      )}
      <MapContainer center={center} zoom={5} className="map">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapClick enabled={Boolean(pickTarget)} onPick={onPick} />
      <PanTo point={focusPoint} />
      {routes.length > 0 ? <FitRoutes routes={routes} /> : <FitEndpoints routes={routes} origin={origin} destination={destination} />}
      {routes.map((route, index) => (
        <Polyline
          key={`${route.id}-casing`}
          positions={(route.geometry || []).map(([longitude, latitude]) => [latitude, longitude])}
          pathOptions={{
            color: route.is_recommended ? '#2563eb' : ROUTE_COLORS[index % ROUTE_COLORS.length],
            weight: route.is_recommended ? 10 : 7,
            opacity: 0.35,
          }}
        />
      ))}
      {segments.map((segment) => (
        <Polyline
          key={segment.key}
          positions={segment.positions}
          pathOptions={{
            color: RISK_COLORS[riskAtHour(segment.timeline, hour, segment.riskLevel)] || RISK_COLORS.Unknown,
            weight: segment.recommended ? 6 : 4,
            opacity: 0.92,
          }}
        />
      ))}
      {routes.flatMap((route) =>
        (route.checkpoints || []).map((checkpoint) => {
          const forecastRisk = riskAtHour(checkpoint.risk_timeline, hour, checkpoint.risk_level)
          return (
            <CircleMarker
              key={`${route.id}-${checkpoint.sequence}`}
              center={[checkpoint.latitude, checkpoint.longitude]}
              radius={route.is_recommended ? 6 : 5}
              pathOptions={{
                color: '#ffffff',
                weight: 2,
                fillColor: RISK_COLORS[forecastRisk] || RISK_COLORS.Unknown,
                fillOpacity: 0.95,
              }}
            >
              <Popup>
                <b>
                  {route.name} · Checkpoint {checkpoint.sequence + 1}
                </b>
                <p>
                  {checkpoint.distance_miles} miles · arrival risk {checkpoint.risk_level}
                </p>
                <p>Forecast at +{hour}h: {forecastRisk}</p>
                <p>ETA: {new Date(checkpoint.eta).toLocaleString()}</p>
                <p>Wind at ETA: {checkpoint.wind_mph ?? 'N/A'} mph</p>
                <p>Rain at ETA: {checkpoint.rain_in_per_hour ?? 'N/A'} in/hr</p>
                <p>Snow at ETA: {checkpoint.snow_in_per_hour ?? 'N/A'} in/hr</p>
              </Popup>
            </CircleMarker>
          )
        }),
      )}
      <EndpointMarker place={origin} icon={originIcon} title="Origin" />
      <EndpointMarker place={destination} icon={destinationIcon} title="Destination" />
    </MapContainer>
    </div>
  )
}

export { RISK_COLORS }
