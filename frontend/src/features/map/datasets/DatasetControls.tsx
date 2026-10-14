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
  const [sumoWeekday, setSumoWeekday] = useState(data.trafficSchedule.weekday);
  const [sumoPeriod, setSumoPeriod] = useState(data.trafficSchedule.period);
  const [sumoSubmitting, setSumoSubmitting] = useState(false);
  const [sumoSubmitError, setSumoSubmitError] = useState('');
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
          <div className="dataset-legend">
            {[
              ['A', '#168a58'], ['B', '#71ad45'], ['C', '#d2b83f'],
              ['D', '#e58b32'], ['E', '#d9583c'], ['F', '#8c3047'],
            ].map(([grade, color]) => <Legend key={grade} color={color} label={grade} />)}
          </div>
          <DatasetNote>
            Historical typical level for this weekday and half-hour, computed from matched
            traffic observations. Not live traffic, a validated future forecast, or a SUMO
            vehicle-count simulation. Confidence reflects historical sample count and agreement.
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
          <form
            className="dataset-dates"
            onSubmit={async (event) => {
              event.preventDefault();
              setSumoSubmitting(true);
              setSumoSubmitError('');
              try {
                await data.runSumo({ weekday: sumoWeekday, period: sumoPeriod });
              } catch (error) {
                setSumoSubmitError(error instanceof Error ? error.message : 'Could not queue SUMO run');
              } finally {
                setSumoSubmitting(false);
              }
            }}
          >
            <strong>Run SUMO congestion scenario</strong>
            <div className="dataset-fields">
              <label>
                Historical weekday
                <select
                  aria-label="SUMO prediction day of week"
                  value={sumoWeekday}
                  onChange={(event) => setSumoWeekday(Number(event.target.value))}
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
                  aria-label="SUMO prediction time of day"
                  value={sumoPeriod}
                  onChange={(event) => setSumoPeriod(event.target.value)}
                />
              </label>
            </div>
            <button type="submit" disabled={sumoSubmitting || data.sumoRunStatus === 'queued' || data.sumoRunStatus === 'running'}>
              {sumoSubmitting || data.sumoRunStatus === 'queued' || data.sumoRunStatus === 'running'
                ? `SUMO ${data.sumoRunStatus ?? 'queueing'}…`
                : 'Run separate SUMO simulation'}
            </button>
          </form>
          {data.sumoRunStatus === 'failed' && (
            <p className="dataset-status" role="alert">SUMO run failed: {data.sumoRunError ?? 'unknown error'}</p>
          )}
          {data.sumoRunStatus === 'completed' && (
            <p className="dataset-status" role="status">
              SUMO simulation complete · {String(data.sumoRunMetadata?.features ?? 0)} road edges
            </p>
          )}
          {sumoSubmitError && <p className="dataset-status" role="alert">{sumoSubmitError}</p>}
          <div className="dataset-legend">
            {[
              ['A', '#168a58'], ['B', '#71ad45'], ['C', '#d2b83f'],
              ['D', '#e58b32'], ['E', '#d9583c'], ['F', '#8c3047'],
            ].map(([grade, color]) => <Legend key={grade} color={color} label={grade} />)}
          </div>
          <DatasetNote>
            This is a separate SUMO run. Demand is estimated from historical LOS, not measured
            vehicle counts or an observed origin–destination matrix. Results are modeled scenarios,
            not live traffic or a validated forecast.
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
