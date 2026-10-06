import { useState, type CSSProperties } from 'react';
import { CircleAlert, Info, LoaderCircle, MapPinOff } from 'lucide-react';
import { dateQuery, type Palette } from '../../../services/api';
import type { BackendLayers } from './useBackendLayers';
import { type DataLayerId, PALETTE_STOPS, RISK_COLORS } from './datasets';
import './data.css';

export function DatasetControls({ id, data }: { id: DataLayerId; data: BackendLayers }) {
  const report = data.reports[id];
  const StatusIcon =
    report?.status === 'error'
      ? CircleAlert
      : report?.status === 'empty'
        ? MapPinOff
        : LoaderCircle;
  return (
    <div className="dataset-controls" data-state={report?.status ?? 'loading'}>
      {id === 'population' && (
        <>
          <div className="dataset-fields">
            <label>
              Year
              <select
                aria-label="Population year"
                value={data.year}
                onChange={(event) => data.setYear(Number(event.target.value))}
              >
                {data.years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Palette
              <select
                aria-label="Population palette"
                value={data.palette}
                onChange={(event) => data.setPalette(event.target.value as Palette)}
              >
                <option value="pseudocolor">Population</option>
                <option value="greyscale">Greyscale</option>
                <option value="fire">Fire</option>
              </select>
            </label>
          </div>
          <div className="population-legend" aria-label="Population legend">
            <div
              className="population-legend-ramp"
              aria-hidden="true"
              style={
                {
                  '--population-ramp': `linear-gradient(to right, ${PALETTE_STOPS[data.palette].map(([, color]) => color).join(',')})`,
                } as CSSProperties
              }
            />
            <div className="population-legend-values">
              {PALETTE_STOPS[data.palette].map(([value]) => (
                <span key={value}>{value === 1000 ? '1,000+' : value}</span>
              ))}
            </div>
          </div>
          <small>
            People / cell <span aria-hidden="true">·</span> 100 m nominal
          </small>
          <DatasetNote>
            WorldPop · people per source cell, not density per km². Display interpolated; values use
            original cells. No-data remains transparent.
          </DatasetNote>
        </>
      )}
      {id === 'flood-history' && (
        <>
          <Legend color="#2877dc" label="Reported flood location" />
          <DatasetNote>
            Historical names from reports. Pins may represent an area or street, not an exact
            address. No report does not mean no flood.
          </DatasetNote>
        </>
      )}
      {id === 'flood-satellite' && (
        <>
          <Legend color="#267bcc" label="Classified flood pixels" />
          <DatasetNote>Satellite classification, not water depth.</DatasetNote>
        </>
      )}
      {id === 'flood' && (
        <>
          <div className="dataset-legend">
            <Legend color={RISK_COLORS.alert} label="Rain alert" />
            <Legend color={RISK_COLORS.below} label="Below threshold" />
            <Legend color={RISK_COLORS.unknown} label="Unknown" />
          </div>
          <DatasetNote>
            Rainfall threshold indicator, not flood extent or a safety assessment.
          </DatasetNote>
        </>
      )}
      {id === 'land-price' && (
        <>
          <Legend color="#f59e0b" label="Official road reference" />
          <DatasetNote>
            Official reference · VND/m² · not transaction prices. Automatic matches cover whole
            named roads, not verified price-segment boundaries.
          </DatasetNote>
        </>
      )}
      {data.catalog[id]?.stale && (
        <small className="dataset-warning">Source expired · historical values</small>
      )}
      {!(report?.status === 'ready' && report.message === 'Data available in this area') && (
        <p className="dataset-status" role="status" data-state={report?.status ?? 'loading'}>
          <StatusIcon size={13} aria-hidden="true" />
          <span>{report?.message ?? 'Loading…'}</span>
          {report?.status === 'error' && (
            <button type="button" onClick={data.retry}>
              Retry
            </button>
          )}
        </p>
      )}
    </div>
  );
}
function DatasetNote({ children }: { children: string }) {
  return (
    <details className="dataset-note">
      <summary>
        <Info size={12} aria-hidden="true" />
        Details
      </summary>
      <small>{children}</small>
    </details>
  );
}
function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="dataset-legend-item">
      <i style={{ background: color }} />
      {label}
    </span>
  );
}
export function DatasetDates({ data }: { data: BackendLayers }) {
  const [start, setStart] = useState(data.dates.start?.slice(0, 10) ?? '');
  const [end, setEnd] = useState(data.dates.end?.slice(0, 10) ?? '');
  const [error, setError] = useState('');
  return (
    <form
      className="dataset-dates"
      onSubmit={(event) => {
        event.preventDefault();
        try {
          data.setDates(dateQuery(start, end));
          setError('');
        } catch (error) {
          setError(error instanceof Error ? error.message : 'Invalid dates');
        }
      }}
    >
      <strong>
        Flood dates <small>UTC · end exclusive</small>
      </strong>
      <div className="dataset-fields">
        <label>
          From
          <input
            type="date"
            aria-label="Flood start date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </label>
        <label>
          Until
          <input
            type="date"
            aria-label="Flood end date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
      </div>
      <div className="dataset-date-actions">
        <button type="submit">Apply</button>
        <button
          type="button"
          onClick={() => {
            setStart('');
            setEnd('');
            data.setDates({});
            setError('');
          }}
        >
          All dates
        </button>
      </div>
      {(error || data.dates.start || data.dates.end) && (
        <small role="status">{error || 'Date filter applied'}</small>
      )}
    </form>
  );
}
