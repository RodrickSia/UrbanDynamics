import type { Geometry, Position } from 'geojson';
import type { LayerSpecification } from 'maplibre-gl';

export type SnapSource = 'parcel' | 'road-centerline' | 'road-polygon' | 'water-polygon';
export interface SnapGeometry { geometry: Geometry; source: SnapSource | 'zoning' }
export interface ScreenPoint { x: number; y: number }
export interface SnapResult { coordinate: Position; source: SnapGeometry['source']; distance: number; kind: 'vertex' | 'edge' }

export function snapSource(layer: LayerSpecification): SnapSource | null {
  if (layer.id === 'zoning-plan-parcels-outline') return 'parcel';
  if (layer.type !== 'line' && layer.type !== 'fill') return null;
  if (layer.id.startsWith('zoning-') || layer.id.startsWith('dataset-')) return null;
  const name = `${layer.id} ${'source-layer' in layer ? layer['source-layer'] ?? '' : ''}`.toLowerCase();
  if (/(water|river|canal|stream|lake)/.test(name)) return layer.type === 'fill' ? 'water-polygon' : null;
  if (/(road|street|highway|motorway|transport|bridge)/.test(name))
    return layer.type === 'line' ? 'road-centerline' : 'road-polygon';
  return null;
}

function lines(geometry: Geometry): Position[][] {
  switch (geometry.type) {
    case 'LineString': return [geometry.coordinates];
    case 'MultiLineString': return geometry.coordinates;
    case 'Polygon': return geometry.coordinates;
    case 'MultiPolygon': return geometry.coordinates.flat();
    case 'GeometryCollection': return geometry.geometries.flatMap(lines);
    default: return [];
  }
}

export function nearestSnap(pointer: ScreenPoint, candidates: SnapGeometry[], project: (position: Position) => ScreenPoint,
  radius = 10): SnapResult | null {
  let bestVertex: SnapResult | null = null;
  let bestEdge: SnapResult | null = null;
  for (const candidate of candidates) for (const line of lines(candidate.geometry)) {
    if (!line.length) continue;
    const projected = line.map(project);
    for (let index = 0; index < line.length; index++) {
      const vertex = projected[index];
      const vertexDistance = Math.hypot(vertex.x - pointer.x, vertex.y - pointer.y);
      if (vertexDistance <= radius && (!bestVertex || vertexDistance < bestVertex.distance)) {
        bestVertex = { coordinate: line[index], source: candidate.source, distance: vertexDistance, kind: 'vertex' };
      }
      if (!index) continue;
      const start = projected[index - 1];
      const dx = vertex.x - start.x, dy = vertex.y - start.y;
      const lengthSquared = dx * dx + dy * dy;
      if (!lengthSquared) continue;
      const fraction = Math.max(0, Math.min(1, ((pointer.x - start.x) * dx + (pointer.y - start.y) * dy) / lengthSquared));
      const x = start.x + fraction * dx, y = start.y + fraction * dy;
      const distance = Math.hypot(x - pointer.x, y - pointer.y);
      if (distance < radius && (!bestEdge || distance < bestEdge.distance)) {
        bestEdge = { coordinate: [line[index - 1][0] + fraction * (line[index][0] - line[index - 1][0]),
          line[index - 1][1] + fraction * (line[index][1] - line[index - 1][1])],
          source: candidate.source, distance, kind: 'edge' };
      }
    }
  }
  return bestVertex && bestVertex.distance <= 4 ? bestVertex : bestEdge ?? bestVertex;
}
