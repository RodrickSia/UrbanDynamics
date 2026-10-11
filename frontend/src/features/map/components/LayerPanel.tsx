import { ChevronDown, Layers3, RefreshCw, X } from 'lucide-react';
import { useRef } from 'react';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { LayerOpacityState, LayerState, UrbanLayerDefinition } from '../types/map';
import type { BackendLayers } from '../datasets/useBackendLayers';
import { isDataLayer, type DataLayerId } from '../datasets/datasets';
import { DatasetDates } from '../datasets/DatasetControls';
import { LayerItem } from './LayerItem';
import { MotionIconButton } from './MotionIconButton';

interface LayerPanelProps {
  backend?: BackendLayers;
  layers: LayerState;
  opacityByLayer: LayerOpacityState;
  onClose: () => void;
  onToggleLayer: (layer: UrbanLayerDefinition) => void;
  onOpacityChange: (layer: UrbanLayerDefinition, opacity: number) => void;
}
const DATASET_ORDER: DataLayerId[] = [
  'population',
  'flood-history',
  'flood-satellite',
  'flood',
  'land-price',
  'parcels',
];
export function LayerPanel(props: LayerPanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const definitions = props.backend?.definitions ?? URBAN_LAYERS;
  const datasets = DATASET_ORDER.flatMap((id) => definitions.filter((layer) => layer.id === id));
  const display = definitions.filter((layer) => layer.id === 'poi' || layer.id === 'buildings-3d');
  const future = definitions.filter((layer) => !isDataLayer(layer.id) && !display.includes(layer));
  const available = datasets.filter((layer) => layer.status === 'available').length;
  const active = datasets.filter(
    (layer) => layer.status === 'available' && props.layers[layer.id],
  ).length;
  const connecting = datasets.some((layer) => layer.status === 'loading');
  const offline = datasets.some((layer) => layer.status === 'error');
  useGSAP(
    () => {
      gsap.fromTo(
        panelRef.current,
        { xPercent: 100, autoAlpha: 0 },
        { xPercent: 0, autoAlpha: 1, duration: motionDuration(0.38), ease: 'power3.out' },
      );
    },
    { scope: panelRef },
  );
  const row = (layer: UrbanLayerDefinition) => (
    <LayerItem
      key={layer.id}
      layer={layer}
      active={Boolean(props.layers[layer.id])}
      opacity={props.opacityByLayer[layer.id] ?? 0.8}
      backend={props.backend}
      onToggle={props.onToggleLayer}
      onOpacity={props.onOpacityChange}
    />
  );
  return (
    <aside
      ref={panelRef}
      className="right-workspace layer-workspace solid-panel dataset-panel"
      role="region"
      aria-label="Data layers"
    >
      <header className="workspace-heading dataset-panel-heading">
        <span className="workspace-icon" aria-hidden="true">
          <Layers3 size={20} />
        </span>
        <div>
          <h2>Data layers</h2>
          <p>{active} active</p>
        </div>
        {props.backend && (
          <MotionIconButton
            className="quiet-icon-button"
            title="Refresh data sources"
            aria-label="Refresh data sources"
            onClick={props.backend.retry}
          >
            <RefreshCw size={16} aria-hidden="true" />
          </MotionIconButton>
        )}
        <MotionIconButton
          className="quiet-icon-button"
          aria-label="Close data layers"
          onClick={props.onClose}
        >
          <X size={18} aria-hidden="true" />
        </MotionIconButton>
      </header>
      <div className="dataset-panel-body">
        <section role="group" aria-labelledby="dataset-section-heading" className="layer-section">
          <div className="layer-section-heading">
            <h3 id="dataset-section-heading">Datasets</h3>
            <span role="status">{connecting ? 'Connecting…' : `${available} available`}</span>
          </div>
          {offline && (
            <p className="dataset-connection-note" role="status">
              {available ? 'Some data sources are offline' : 'Could not connect to data sources'}
            </p>
          )}
          <div className="layer-list">{datasets.map(row)}</div>
          {props.backend &&
            ['flood', 'flood-history', 'flood-satellite'].some(
              (id) => props.layers[id as keyof LayerState],
            ) && <DatasetDates data={props.backend} />}
        </section>
        <section role="group" aria-labelledby="display-section-heading" className="layer-section">
          <div className="layer-section-heading">
            <h3 id="display-section-heading">Map display</h3>
          </div>
          <div className="layer-list">{display.map(row)}</div>
        </section>
        <details className="future-layers">
          <summary>
            <span>More layers</span>
            <span className="future-layer-count">{future.length}</span>
            <ChevronDown size={15} aria-hidden="true" />
          </summary>
          <div className="layer-list">{future.map(row)}</div>
        </details>
      </div>
    </aside>
  );
}
