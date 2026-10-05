import type {
  LayerOpacityState,
  LayerState,
  MapMode,
  UrbanLayerDefinition,
  UrbanLayerId,
} from '../types/map';

export function createInitialLayerState(
  layers: ReadonlyArray<UrbanLayerDefinition>,
): LayerState {
  return Object.fromEntries(layers.map((layer) => [layer.id, layer.enabledByDefault]));
}

export function toggleLayerState(
  current: LayerState,
  layer: UrbanLayerDefinition,
): LayerState {
  if (layer.status !== 'available') return current;
  return { ...current, [layer.id]: !current[layer.id] };
}

export function setMapMode(
  current: LayerState,
  mode: MapMode,
): { mode: MapMode; layers: LayerState } {
  return {
    mode,
    layers: { ...current, 'buildings-3d': mode === '3d' },
  };
}

export function createInitialLayerOpacity(
  layers: ReadonlyArray<UrbanLayerDefinition>,
): LayerOpacityState {
  return Object.fromEntries(layers.filter((layer) => layer.supportsOpacity).map((layer) => [layer.id, 0.8]));
}

export function setLayerOpacity(
  current: LayerOpacityState,
  layerId: UrbanLayerId,
  opacity: number,
): LayerOpacityState {
  return { ...current, [layerId]: Math.min(1, Math.max(0, opacity)) };
}
