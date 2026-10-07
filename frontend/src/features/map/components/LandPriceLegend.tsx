import type { LandPriceProperties, LandPriceStatus } from '../layers/landPrice';
import { PRICE_COLORS, priceText, matchLabel } from '../layers/landPrice';

function safeSource(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined; }
  catch { return undefined; }
}

export function LandPriceLegend({ status, selected, onClose, onRetry }: {
  status: LandPriceStatus; selected: LandPriceProperties | null; onClose: () => void; onRetry: () => void;
}) {
  const source = selected ? safeSource(selected.source_url) : undefined;
  return (
    <aside className="land-price-legend glass-panel" aria-label="Land price legend">
      <strong>Official reference land price</strong>
      {status.state === 'loading' && <p role="status">Loading land-price data…</p>}
      {status.state === 'error' && <p role="alert">{status.message} <button type="button" onClick={onRetry}>Retry</button></p>}
      {status.state === 'ready' && <>
        <div className="land-price-scale" aria-hidden="true" style={{ background: `linear-gradient(to right, ${PRICE_COLORS[0]} 0%, ${PRICE_COLORS[1]} 6.67%, ${PRICE_COLORS[2]} 33.33%, ${PRICE_COLORS[3]} 100%)` }} />
        <div className="land-price-scale-labels"><span>0</span><span>20</span><span>100</span><span>300+</span></div>
        <small>Million ₫/m² · residential · zoom in to see roads</small>
        <p>{status.matched?.toLocaleString()} mapped / {status.sourceRows?.toLocaleString()} source rows. {status.pending?.toLocaleString()} awaiting a verified match.</p>
        <small>Partial coverage. Blank areas have no mapped price. These are official reference prices, not transaction prices.</small>
      </>}
      {selected && <section aria-label="Land price details" className="land-price-details">
        <button type="button" className="land-price-close" onClick={onClose} aria-label="Close land price details">×</button>
        <strong>{String(selected.road ?? 'Road segment')}</strong>
        <p>{String(selected.ward ?? '')} · {String(selected.start ?? '')} → {String(selected.end ?? '')}</p>
        <dl>
          <dt>Residential</dt><dd>{priceText(selected.residential_vnd_m2)}</dd>
          <dt>Commercial</dt><dd>{priceText(selected.commercial_vnd_m2)}</dd>
          <dt>Other non-agricultural</dt><dd>{priceText(selected.other_nonagricultural_vnd_m2)}</dd>
        </dl>
        <p>{matchLabel(selected)}</p>
        <small>{selected.geometry_coverage === 'partial_city_clipped_segment' ? 'Partial segment clipped to the analytical city boundary' : selected.geometry_coverage === 'partial_published_segment' ? 'Partial published segment' : selected.geometry_coverage === 'whole_named_road_proxy' ? 'Full named-road proxy; endpoints not clipped' : 'OSM geometry; legal segment limits require verification'}</small>
        <p>Effective {String(selected.effective_from ?? 'unknown')} · PDF page {String(selected.pdf_page ?? 'unknown')}{source && <> · <a href={source} target="_blank" rel="noopener noreferrer">Source</a></>}</p>
      </section>}
    </aside>
  );
}
