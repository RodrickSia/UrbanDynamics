import { Layers3, X } from 'lucide-react';
import { useRef } from 'react';

import { URBAN_LAYERS } from '../layers/layerRegistry';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { LayerOpacityState, LayerState, UrbanLayerDefinition } from '../types/map';

interface LayerPanelProps {
  layers: LayerState;
  opacityByLayer: LayerOpacityState;
  onClose: () => void;
  onToggleLayer: (layer: UrbanLayerDefinition) => void;
  onOpacityChange: (layer: UrbanLayerDefinition, opacity: number) => void;
}

export function LayerPanel(props: LayerPanelProps) {
  const panelRef = useRef<HTMLElement>(null);

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

  return (
    <aside ref={panelRef} className="right-workspace layer-workspace glass-panel" role="region" aria-label="Data layers">
      <header className="workspace-heading">
        <span className="workspace-icon" aria-hidden="true"><Layers3 size={20} /></span>
        <h2>Data layers</h2>
        <button className="quiet-icon-button" type="button" onClick={props.onClose} aria-label="Close data layers">
          <X aria-hidden="true" size={17} />
        </button>
      </header>
      <div className="layer-list">
        {URBAN_LAYERS.map((layer) => {
          const available = layer.status === 'available';
          const active = Boolean(props.layers[layer.id]);
          return (
            <div className="layer-item" key={layer.id}>
              <label>
                <span className="layer-copy">
                  <strong>{layer.label}</strong>
                  {!available && <small>Unavailable</small>}
                </span>
                <input
                  type="checkbox"
                  aria-label={layer.label}
                  checked={active}
                  disabled={!available}
                  onChange={() => props.onToggleLayer(layer)}
                />
                <span className="switch" aria-hidden="true" />
              </label>
              {available && active && layer.supportsOpacity && (
                <label className="opacity-control">
                  <span>Opacity</span>
                  <input
                    type="range"
                    min="20"
                    max="100"
                    step="5"
                    value={Math.round((props.opacityByLayer[layer.id] ?? 0.8) * 100)}
                    onChange={(event) => props.onOpacityChange(layer, Number(event.target.value) / 100)}
                    aria-label={`${layer.label} opacity`}
                  />
                  <output>{Math.round((props.opacityByLayer[layer.id] ?? 0.8) * 100)}%</output>
                </label>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
