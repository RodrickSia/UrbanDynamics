import { useState, type CSSProperties } from 'react';
import { CircleAlert, Info, LoaderCircle, MapPinOff } from 'lucide-react';
import { dateQuery, type Palette } from '../../../services/api';
import type { BackendLayers } from './useBackendLayers';
import { type DataLayerId, PALETTE_STOPS, RISK_COLORS } from './datasets';
import './data.css';

export function DatasetControls({ id, data }: { id: DataLayerId; data: BackendLayers }) {
  const report = data.reports[id];
  const [trafficWeekday, setTrafficWeekday] = useState(data.trafficSchedule.weekday);
  const [trafficPeriod, setTrafficPeriod] = useState(data.trafficSchedule.period);
  const sumoVolumeMax = Math.max(
    0,
    Math.floor(Number(data.sumoRunMetadata?.max_simulated_vehicles_6h ?? 0)),
  );
  const sumoVolumeTicks = [...new Set([0, 0.25, 0.5, 0.75, 1].map((fraction) => Math.round(sumoVolumeMax * fraction)))];
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
      {id === 'parcels' && (
        <>
          <Legend color="#e85430" label="Land-use colors" />
          <DatasetNote>
            Colors follow source land-use codes; grey means unknown. Small plots appear as you
            zoom in. Select a plot to see its source attributes and nearby road-price references.
          </DatasetNote>
        </>
      )}
      {id === 'synthetic-buildings' && (
        <DatasetNote>
          Estimated parcel-based extrusions. Footprints are inset from residential parcel
          boundaries, and heights are sampled from observed GBA residential buildings; they are
          not surveyed building outlines or heights.
        </DatasetNote>
      )}
      {id === 'traffic' && (
        <>
          <form
            className="dataset-dates"
            onSubmit={(event) => {
              event.preventDefault();
              data.setTrafficSchedule({ weekday: trafficWeekday, period: trafficPeriod });
            }}
          >
            <strong>Typical conditions <small>30-minute historical slot</small></strong>
            <div className="dataset-fields">
              <label>
                Day of week
                <select
                  aria-label="Traffic prediction day of week"
                  value={trafficWeekday}
                  onChange={(event) => setTrafficWeekday(Number(event.target.value))}
                >
                  {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day, index) => (
                    <option key={day} value={index + 1}>{day}</option>
                  ))}
                </select>
              </label>
              <label>
                Time of day (HCMC)
                <input
                  type="time"
                  step={1800}
                  aria-label="Traffic prediction time of day"
                  value={trafficPeriod}
                  onChange={(event) => setTrafficPeriod(event.target.value)}
                />
              </label>
            </div>
            <button type="submit">Apply</button>
          </form>
          <div className="traffic-score-legend" role="group" aria-label="Historical congestion score from 0 to 100">
            <small>Estimated congestion score · low to high</small>
            <div className="traffic-score-ramp" aria-hidden="true" />
            <div className="traffic-score-ticks">
              {[0, 25, 50, 75, 100].map((score) => <span key={score}>{score}</span>)}
            </div>
          </div>
          <DatasetNote>
            Colors cover the loaded road network. Directly matched roads use historical
            observations; uncovered roads are estimated from a nearby observed road, then the
            same road type or network average for the selected time/day. If that half-hour has
            no data, the estimate falls back to other observations from that weekday. Select a
            road to see its estimate basis and confidence. Not live traffic or a SUMO
            vehicle-count simulation.
          </DatasetNote>
        </>
      )}
      {id === 'sumo-network' && (
        <>
          <Legend color="#647987" label="SUMO network edge" />
          <DatasetNote>
            Roads come from the loaded HCMC SUMO network. This layer shows network geometry and
            attributes only; it is not a SUMO run or a congestion prediction. Turn on the
            historical traffic or SUMO congestion simulation layer for traffic results.
          </DatasetNote>
        </>
      )}
      {id === 'sumo-simulation' && (
        <>
          {data.sumoRunStatus === 'loading' && (
            <p className="dataset-status" role="status">Loading the latest precomputed SUMO layer…</p>
          )}
          {data.sumoRunStatus === 'empty' && (
            <p className="dataset-status" role="status">No precomputed six-hour SUMO layer is available.</p>
          )}
          {data.sumoRunStatus === 'error' && (
            <p className="dataset-status" role="alert">SUMO layer unavailable: {data.sumoRunError ?? 'unknown error'}</p>
          )}
          {data.sumoRunStatus === 'completed' && (
            <p className="dataset-status" role="status">
              Latest precomputed scenario · weekday {String(data.sumoRunMetadata?.weekday ?? '')},
              {' '}start {String(data.sumoRunMetadata?.period ?? '')} HCMC · six hours
            </p>
          )}
          <div className="sumo-volume-legend" role="group" aria-label="Simulated vehicle passages, including motorcycles, per road over six hours">
            <small>Simulated vehicle passages · six hours</small>
            <div className="sumo-volume-ramp" aria-hidden="true" />
            {data.sumoRunStatus === 'completed' ? (
              <div className="sumo-volume-ticks">
                {sumoVolumeTicks.map((tick, index) => (
                  <span key={`${tick}-${index}`}>{tick.toLocaleString()}</span>
                ))}
              </div>
            ) : (
              <small>Scale appears when a cached scenario is available.</small>
            )}
          </div>
          <DatasetNote>
            This is a precomputed data layer; enabling it never starts a simulation. The fast
            synthetic run uses 360 planned trips over six hours (252 motorcycles and 108 cars),
            so it is not representative of real city demand and will generally understate
            congestion. The latest workflow-published scenario is shown as a six-hour aggregate,
            not live traffic or a validated forecast. Road colors show total simulated vehicle
            passages, including motorcycles; the feature details separate cars from motorcycles.
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
