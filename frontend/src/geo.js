const EARTH_MILES = 3958.7613

export function haversineMiles(start, end) {
  const [lon1, lat1] = start
  const [lon2, lat2] = end
  const toRadians = (degrees) => (degrees * Math.PI) / 180
  const deltaLat = toRadians(lat2 - lat1)
  const deltaLon = toRadians(lon2 - lon1)
  const chord =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(deltaLon / 2) ** 2
  return 2 * EARTH_MILES * Math.atan2(Math.sqrt(chord), Math.sqrt(Math.max(0, 1 - chord)))
}

export function sliceRouteSegments(route) {
  const coordinates = route.geometry || []
  const checkpoints = route.checkpoints || []
  if (coordinates.length < 2 || checkpoints.length < 2 || !route.distance_miles) {
    return []
  }

  const cumulative = [0]
  for (let index = 1; index < coordinates.length; index += 1) {
    cumulative.push(cumulative[index - 1] + haversineMiles(coordinates[index - 1], coordinates[index]))
  }
  const total = cumulative[cumulative.length - 1]
  if (total <= 0) return []

  const segments = []
  for (let index = 0; index < checkpoints.length - 1; index += 1) {
    const start = checkpoints[index].distance_miles / route.distance_miles
    const end = checkpoints[index + 1].distance_miles / route.distance_miles
    const positions = positionsBetween(coordinates, cumulative, total, start, end)
    if (positions.length < 2) continue
    segments.push({
      key: `${route.id}-${checkpoints[index].sequence}`,
      positions,
      timeline: checkpoints[index].risk_timeline,
      riskLevel: checkpoints[index].risk_level,
    })
  }
  return segments
}

function positionsBetween(coordinates, cumulative, total, startFraction, endFraction) {
  const start = clamp(startFraction) * total
  const end = clamp(endFraction) * total
  const positions = [toLatLng(pointAtDistance(coordinates, cumulative, start))]
  for (let index = 1; index < coordinates.length - 1; index += 1) {
    if (cumulative[index] > start && cumulative[index] < end) {
      positions.push(toLatLng(coordinates[index]))
    }
  }
  positions.push(toLatLng(pointAtDistance(coordinates, cumulative, end)))
  return positions
}

function pointAtDistance(coordinates, cumulative, distance) {
  if (distance <= 0) return coordinates[0]
  const last = cumulative.length - 1
  if (distance >= cumulative[last]) return coordinates[last]

  let index = 1
  while (index < cumulative.length && cumulative[index] < distance) index += 1
  const span = cumulative[index] - cumulative[index - 1]
  const share = span === 0 ? 0 : (distance - cumulative[index - 1]) / span
  const start = coordinates[index - 1]
  const end = coordinates[index]
  return [
    start[0] + (end[0] - start[0]) * share,
    start[1] + (end[1] - start[1]) * share,
  ]
}

function toLatLng(point) {
  return [point[1], point[0]]
}

function clamp(value) {
  return Math.max(0, Math.min(1, value))
}
