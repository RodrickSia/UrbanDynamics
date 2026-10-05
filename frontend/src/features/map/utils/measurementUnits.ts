export type MeasurementUnits = 'metric' | 'imperial';
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

export function formatLength(meters: number, units: MeasurementUnits): string {
  if (units === 'imperial') return `${number.format(meters / 0.3048)} ft`;
  return meters >= 1000 ? `${number.format(meters / 1000)} km` : `${number.format(meters)} m`;
}

export function formatArea(squareMeters: number, units: MeasurementUnits): string {
  if (units === 'imperial') return squareMeters >= 4046.8564224
    ? `${number.format(squareMeters / 4046.8564224)} acre`
    : `${number.format(squareMeters / 0.09290304)} ft²`;
  if (squareMeters >= 1_000_000) return `${number.format(squareMeters / 1_000_000)} km²`;
  if (squareMeters >= 10_000) return `${number.format(squareMeters / 10_000)} ha`;
  return `${number.format(squareMeters)} m²`;
}
