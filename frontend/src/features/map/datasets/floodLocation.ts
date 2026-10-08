/** Display provenance, not reverse-geocoded guesses or administrative renames. */
function text(value: unknown): string {
  return typeof value === 'string'
    ? value
        .normalize('NFC')
        .replace(/\s+/gu, ' ')
        .replace(/\s*,\s*/gu, ', ')
        .trim()
    : '';
}
export function floodLocationDetails(properties: Record<string, unknown>): Record<string, unknown> {
  const parts = text(properties.location)
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  for (const field of ['reported_ward', 'reported_district']) {
    const value = text(properties[field]);
    if (
      value &&
      !parts.some((part) => part.toLocaleLowerCase('vi') === value.toLocaleLowerCase('vi'))
    ) {
      parts.push(value);
    }
  }
  const method = text(properties.geocoding_method).toLowerCase();
  const precision = text(properties.spatial_precision).toLowerCase();
  const description =
    method === 'area point'
      ? 'Approximate area'
      : method === 'street point'
        ? 'Approximate street location'
        : method === 'exact point'
          ? 'Source-reported point'
          : 'Location accuracy unknown';
  return {
    ...properties,
    location: parts.join(', ') || 'Unspecified location',
    current_admin_unit: text(properties.current_admin_unit) || undefined,
    location_accuracy: `${description}${['low', 'medium', 'high'].includes(precision) ? ` · ${precision} precision` : ''}`,
    spatial_precision: undefined,
  };
}
