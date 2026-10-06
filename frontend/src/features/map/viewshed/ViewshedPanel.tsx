import { Check, Eye, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { gsap, motionDuration, useGSAP } from '../motion';
import { MotionIconButton } from '../components/MotionIconButton';
import { clamp, direction, moveObserver, setDirection } from './math';
import { MAX_VIEWSHEDS, type ViewshedAction, type ViewshedState } from './state';
import './viewshed.css';

function NumericField({
  label,
  value,
  min,
  max,
  change,
  step,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  change: (n: number) => void;
  step: number;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <label className="viewshed-field">
      <span>{label}</span>
      <input
        aria-label={label}
        type="number"
        step={step}
        min={min}
        max={max}
        value={draft ?? Number(value.toFixed(step < 0.001 ? 5 : 1))}
        onChange={(e) => {
          setDraft(e.target.value);
          const n = e.target.valueAsNumber;
          if (Number.isFinite(n) && n >= min && n <= max) change(n);
        }}
        onBlur={() => {
          if (draft?.trim() && Number.isFinite(Number(draft)))
            change(clamp(Number(draft), min, max));
          setDraft(null);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
          if (e.key === 'Escape') {
            e.stopPropagation();
            setDraft(null);
          }
        }}
      />
    </label>
  );
}

export function ViewshedPanel({
  state,
  onAction,
  status,
}: {
  state: ViewshedState;
  onAction: (action: ViewshedAction) => void;
  status: string;
}) {
  const root = useRef<HTMLElement>(null),
    [confirmClear, setConfirmClear] = useState(false);
  const selected = state.items.find((v) => v.id === state.selectedId);
  const d = selected ? direction(selected) : null;
  useGSAP(
    () => {
      gsap.fromTo(
        root.current,
        { opacity: 0, y: 12 },
        {
          opacity: 1,
          y: 0,
          duration: motionDuration(0.25),
          ease: 'power3.out',
        },
      );
    },
    { scope: root },
  );
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented)
        onAction({ type: state.phase === 'editing' ? 'done' : 'cancel' });
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [state.phase, onAction]);
  const numeric = (
    label: string,
    value: number,
    min: number,
    max: number,
    change: (n: number) => void,
    step = 1,
  ) => (
    <NumericField
      key={`${selected?.id}:${label}`}
      label={label}
      value={value}
      min={min}
      max={max}
      change={change}
      step={step}
    />
  );
  return (
    <section className="viewshed-panel glass-panel" aria-label="Viewshed analysis" ref={root}>
      <header>
        <span>
          <Eye size={18} aria-hidden="true" /> Viewshed
        </span>
        <MotionIconButton
          className="quiet-icon-button"
          aria-label="Close viewshed editing"
          onClick={() => onAction({ type: 'done' })}
        >
          <X size={17} />
        </MotionIconButton>
      </header>
      {state.phase === 'observer' && <p role="status">Click to place the observer.</p>}
      {state.phase === 'target' && <p role="status">Click to set direction.</p>}
      {selected && d && (
        <>
          <div className="viewshed-summary">
            {numeric('Distance (m)', d.distance, 1, 2000, (n) =>
              onAction({
                type: 'update',
                view: setDirection(selected, { distance: n }),
              }),
            )}
            <span title="Horizontal × vertical field of view">
              {Math.round(selected.horizontalFov)}° × {Math.round(selected.verticalFov)}°
            </span>
          </div>
          <details className="viewshed-settings">
            <summary>Adjust view</summary>
            <div className="viewshed-fields">
              {numeric(
                'Observer elevation (m)',
                selected.observer.elevationMeters,
                -500,
                9000,
                (n) =>
                  onAction({
                    type: 'update',
                    view: moveObserver(selected, {
                      ...selected.observer,
                      elevationMeters: n,
                    }),
                  }),
                0.5,
              )}
              {numeric('Heading (°)', (Math.round(d.heading * 10) / 10) % 360, 0, 360, (n) =>
                onAction({
                  type: 'update',
                  view: setDirection(selected, { heading: n }),
                }),
              )}
              {numeric('Tilt (°)', d.tilt, -89, 89, (n) =>
                onAction({
                  type: 'update',
                  view: setDirection(selected, { tilt: n }),
                }),
              )}
              {numeric('Horizontal FOV (°)', selected.horizontalFov, 5, 120, (n) =>
                onAction({
                  type: 'update',
                  view: { ...selected, horizontalFov: n },
                }),
              )}
              {numeric('Vertical FOV (°)', selected.verticalFov, 5, 120, (n) =>
                onAction({
                  type: 'update',
                  view: { ...selected, verticalFov: n },
                }),
              )}
            </div>
            <details>
              <summary>Observer coordinates</summary>
              <div className="viewshed-fields">
                {numeric(
                  'Longitude',
                  selected.observer.longitude,
                  -180,
                  180,
                  (n) =>
                    onAction({
                      type: 'update',
                      view: moveObserver(selected, {
                        ...selected.observer,
                        longitude: n,
                      }),
                    }),
                  0.00001,
                )}
                {numeric(
                  'Latitude',
                  selected.observer.latitude,
                  -85,
                  85,
                  (n) =>
                    onAction({
                      type: 'update',
                      view: moveObserver(selected, {
                        ...selected.observer,
                        latitude: n,
                      }),
                    }),
                  0.00001,
                )}
              </div>
            </details>
          </details>
          <div className="viewshed-legend">
            <span>● Visible</span>
            <span>▨ Obstructed</span>
          </div>
        </>
      )}
      {selected && (
        <details className="viewshed-quality">
          <summary role="status">
            {status.startsWith('Loaded scene')
              ? 'Approximate · loaded scene'
              : status.startsWith('Visibility unavailable')
                ? 'Visibility unavailable'
                : status.includes('unavailable') || status.includes('Incomplete')
                  ? 'Incomplete coverage'
                  : status.startsWith('Terrain only')
                    ? 'Terrain only · approximate'
                    : status || 'Preparing scene…'}
          </summary>
          <p>{status || 'Preparing loaded scene…'}</p>
        </details>
      )}
      {state.items.length >= MAX_VIEWSHEDS && (
        <p>Limit: {MAX_VIEWSHEDS} analyses. Delete one to add another.</p>
      )}
      {state.items.length > 1 && (
        <label className="viewshed-select">
          Analysis
          <select
            aria-label="Select viewshed"
            value={state.selectedId ?? ''}
            onChange={(e) => onAction({ type: 'select', id: e.target.value })}
          >
            <option value="" disabled>
              Select…
            </option>
            {state.items.map((v, i) => (
              <option value={v.id} key={v.id}>
                Viewshed {i + 1}
              </option>
            ))}
          </select>
        </label>
      )}
      <footer>
        {state.phase === 'observer' || state.phase === 'target' ? (
          <button className="secondary-button" onClick={() => onAction({ type: 'cancel' })}>
            Cancel
          </button>
        ) : (
          <button
            className="secondary-button"
            onClick={() => onAction({ type: 'start' })}
            disabled={state.items.length >= MAX_VIEWSHEDS}
          >
            <Plus size={15} />
            New
          </button>
        )}
        {selected && state.phase === 'editing' && (
          <MotionIconButton
            className="quiet-icon-button"
            aria-label="Delete selected viewshed"
            onClick={() => onAction({ type: 'delete' })}
          >
            <Trash2 size={16} />
          </MotionIconButton>
        )}
        {state.phase === 'editing' && (
          <button className="primary-button" onClick={() => onAction({ type: 'done' })}>
            <Check size={15} />
            Done
          </button>
        )}
      </footer>
      {state.items.length > 1 && (
        <div className="viewshed-clear">
          {confirmClear ? (
            <>
              <span>Remove all {state.items.length}?</span>
              <button
                onClick={() => {
                  onAction({ type: 'clear' });
                  setConfirmClear(false);
                }}
              >
                Clear all
              </button>
              <button onClick={() => setConfirmClear(false)}>Keep</button>
            </>
          ) : (
            <button onClick={() => setConfirmClear(true)}>Clear all viewsheds</button>
          )}
        </div>
      )}
    </section>
  );
}
