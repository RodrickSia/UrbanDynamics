export function createLocationMarkerElement(kind: 'selected' | 'user'): HTMLDivElement {
  const marker = document.createElement('div');
  marker.className = `location-marker location-marker--${kind}`;
  marker.setAttribute('role', 'img');
  marker.setAttribute('aria-label', kind === 'user' ? 'Your location' : 'Selected location');
  const glyph = document.createElement('span');
  glyph.className = 'location-marker-glyph';
  marker.append(glyph);
  return marker;
}
