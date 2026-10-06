import {
  Box,
  CloudRain,
  Layers3,
  MapPin,
  Route,
  Satellite,
  UsersRound,
  Waves,
  type LucideIcon,
} from 'lucide-react';
import type { BackendLayers } from '../datasets/useBackendLayers';
import { isDataLayer } from '../datasets/datasets';
import { DatasetControls } from '../datasets/DatasetControls';
import type { UrbanLayerDefinition } from '../types/map';

const ICONS: Partial<Record<UrbanLayerDefinition['id'], LucideIcon>> = {
  population: UsersRound,
  'flood-history': Waves,
  'flood-satellite': Satellite,
  flood: CloudRain,
  'land-price': Route,
  poi: MapPin,
  'buildings-3d': Box,
};
export function LayerItem({
  layer,
  active,
  opacity,
  backend,
  onToggle,
  onOpacity,
}: {
  layer: UrbanLayerDefinition;
  active: boolean;
  opacity: number;
  backend?: BackendLayers;
  onToggle: (layer: UrbanLayerDefinition) => void;
  onOpacity: (layer: UrbanLayerDefinition, opacity: number) => void;
}) {
  const available = layer.status === 'available';
  const Icon = ICONS[layer.id] ?? Layers3;
  const loading = layer.status === 'loading';
  const status = loading
    ? 'Connecting'
    : layer.status === 'error'
      ? 'Offline'
      : available
        ? null
        : 'Unavailable';
  return (
    <div
      className="layer-item dataset-row"
      data-active={active && available}
      data-loading={loading}
    >
      <label className="dataset-toggle-row">
        <span className="dataset-row-icon" aria-hidden="true">
          <Icon size={18} strokeWidth={1.75} />
        </span>
        <span className="layer-copy">
          <strong>{layer.label}</strong>
        </span>
        {status && (
          <span
            className="layer-availability"
            data-state={status.toLowerCase()}
            title={layer.id === 'land-price' ? 'No published road prices available' : undefined}
          >
            {status}
          </span>
        )}
        <input
          type="checkbox"
          aria-label={layer.label}
          checked={active}
          disabled={!available && !active}
          onChange={() => onToggle(active ? { ...layer, status: 'available' } : layer)}
        />
        <span className="switch" aria-hidden="true" />
      </label>
      {active && available && (layer.supportsOpacity || (backend && isDataLayer(layer.id))) && (
        <div className="dataset-row-details">
          {backend && isDataLayer(layer.id) && <DatasetControls id={layer.id} data={backend} />}
          {layer.supportsOpacity && (
            <label className="opacity-control">
              <span>Opacity</span>
              <input
                type="range"
                min="20"
                max="100"
                step="5"
                value={Math.round(opacity * 100)}
                onChange={(event) => onOpacity(layer, Number(event.target.value) / 100)}
                aria-label={`${layer.label} opacity`}
              />
              <output>{Math.round(opacity * 100)}%</output>
            </label>
          )}
        </div>
      )}
    </div>
  );
}
