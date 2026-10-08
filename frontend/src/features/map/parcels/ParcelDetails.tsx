import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowUpRight, MapPin, MapPinned, RefreshCw, X } from 'lucide-react';
import { gsap, motionDuration, useGSAP } from '../motion';
import { getParcelDetail, sourceLink, type ParcelDetail } from './parcelApi';
import './parcels.css';

const number = (value: number) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(value);
const text = (value: unknown) => value == null || ['null', 'none', ''].includes(String(value).trim().toLowerCase())
  ? 'Not provided' : String(value);
const PRICE_NOTES = {
  unavailable: 'No suitable published road price is available near this plot.',
  ambiguous: 'Several road segments may apply. A single price cannot be assigned to this plot.',
  unverified: 'The nearby road geometry is unreviewed; a price cannot be assigned yet.',
  unsupported_land_use: 'This land-use type has no reliable road-price category.',
  reference: 'Indicative association by proximity to a published road segment. Road frontage is not verified.',
};

export function ParcelDetails({ parcelId, onClose }: { parcelId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [detail, setDetail] = useState<ParcelDetail | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const closing = useRef(false);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  const { contextSafe } = useGSAP({ scope: dialog });
  const close = () => contextSafe(() => {
    if (closing.current) return;
    closing.current = true;
    gsap.to(dialog.current, { autoAlpha: 0, y: 12, scale: 0.98,
      duration: motionDuration(0.18), ease: 'power2.in', onComplete: () => closeRef.current() });
  })();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    closeButton.current?.focus();
    return () => { element.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  useGSAP(() => {
    gsap.fromTo(dialog.current, { autoAlpha: 0, y: 18, scale: 0.97 },
      { autoAlpha: 1, y: 0, scale: 1, duration: motionDuration(0.32), ease: 'power3.out' });
  }, { scope: dialog });
  useEffect(() => {
    const controller = new AbortController();
    void getParcelDetail(parcelId, controller.signal)
      .then(result => { if (!controller.signal.aborted) setDetail(result); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [parcelId, attempt]);
  const retry = useCallback(() => { setError(false); setDetail(null); setAttempt(value => value + 1); }, []);

  return createPortal(
    <dialog ref={dialog} className="parcel-dialog glass-panel" aria-labelledby="parcel-title"
      onCancel={event => { event.preventDefault(); close(); }}
      onClick={event => { if (event.target === event.currentTarget) {
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
      } }}>
      <header className="parcel-dialog-header">
        <span className="parcel-heading-icon"><MapPinned size={22} aria-hidden="true" /></span>
        <div><p className="parcel-eyebrow">LAND PARCEL</p><h2 id="parcel-title">{detail
          ? `Sheet ${text(detail.parcel.to_ban_do)} · Plot ${text(detail.parcel.thua)}` : 'Plot details'}</h2></div>
        <button ref={closeButton} className="quiet-icon-button" onClick={close} aria-label="Close parcel details"><X size={19} /></button>
      </header>
      <div className="parcel-dialog-body" aria-busy={!detail && !error}>
        {!detail && !error && <div className="parcel-loading" role="status"><span className="parcel-skeleton" />Loading plot details…</div>}
        {error && <div className="parcel-empty" role="alert"><p>Plot details could not be loaded.</p>
          <button className="parcel-retry" onClick={retry}><RefreshCw size={15} />Try again</button></div>}
        {detail && <ParcelContent detail={detail} />}
      </div>
    </dialog>, document.body,
  );
}

function ParcelContent({ detail }: { detail: ParcelDetail }) {
  const { parcel, land_use: use, price } = detail;
  const selected = price.selected;
  const source = sourceLink(selected?.properties.source_url);
  const address = [parcel.phuong, parcel.quan, parcel.tinh].filter(value => text(value) !== 'Not provided').join(', ');
  return <>
    <p className="parcel-address"><MapPin size={16} aria-hidden="true" />{address || 'Location not provided'}</p>
    <div className="parcel-summary">
      <div><span className="parcel-caption">Mapped area</span><strong>{number(parcel.area_m2)} <small>m²</small></strong></div>
      <div><span className="parcel-caption">Land use</span><strong className="parcel-use"><i style={{ backgroundColor: /^#[0-9a-f]{6}$/i.test(use.color) ? use.color : '#94a3b8' }} />{use.code ?? 'Unknown'}</strong>
        {(use.label || price.normalized_land_use) && <small>{use.label || price.normalized_land_use}</small>}</div>
    </div>
    <section className="parcel-section"><div className="parcel-section-heading"><h3>Estimated Land Value</h3></div>
      <p className="parcel-category">{price.price_category ?? 'Unmapped land use'}</p>
      <div className="parcel-price"><strong>{price.estimated_land_total_vnd === null ? 'null' : number(price.estimated_land_total_vnd)}</strong>
        {price.estimated_land_total_vnd !== null && <span>₫</span>}</div>
      <div className="parcel-formula" aria-label="Land value calculation">
        <span>{number(parcel.area_m2)} m²</span><span aria-hidden="true">×</span>
        <span>{price.unit_price_vnd_m2 === null ? 'null' : `${number(price.unit_price_vnd_m2)} ₫/m²`}</span>
        <span aria-hidden="true">=</span><strong>{price.estimated_land_total_vnd === null ? 'null' : `${number(price.estimated_land_total_vnd)} ₫`}</strong>
      </div>
      <p className="parcel-fine-print">{PRICE_NOTES[price.status]}</p>
      {selected && <dl className="parcel-source-details">
        {text(selected.properties.road) !== 'Not provided' && <div><dt>Road</dt><dd>{text(selected.properties.road)}</dd></div>}
        {(text(selected.properties.start) !== 'Not provided' || text(selected.properties.end) !== 'Not provided') &&
          <div><dt>Segment</dt><dd>{text(selected.properties.start)} → {text(selected.properties.end)}</dd></div>}
        <div><dt>Distance to plot</dt><dd>{number(selected.distance_m)} m</dd></div>
        {text(selected.properties.effective_from) !== 'Not provided' &&
          <div><dt>Effective from</dt><dd>{text(selected.properties.effective_from)}</dd></div>}
        <div><dt>Road match</dt><dd>{text(price.road_match_status).replaceAll('_', ' ')} · geometry {text(price.geometry_review_status)}</dd></div>
        {price.valuation_confidence && price.valuation_confidence !== 'none' &&
          <div><dt>Confidence</dt><dd>{price.valuation_confidence}</dd></div>}
      </dl>}
      {price.status === 'ambiguous' && <ul className="parcel-candidates">{price.candidates.map((candidate, index) =>
        <li key={`${candidate.feature_id}-${index}`}><span>{text(candidate.properties.road)}</span><span>{number(candidate.distance_m)} m</span></li>)}</ul>}
      {source && <a className="parcel-source-link" href={source} target="_blank" rel="noopener noreferrer">View price source <ArrowUpRight size={14} /></a>}
      {price.estimated_land_total_vnd !== null && <p className="parcel-fine-print">Land component only · indicative road reference.</p>}
    </section>
    <section className="parcel-section"><h3>Planning information</h3>
      {detail.planning.length > 0 ? <div className="parcel-table-wrap"><table><thead><tr><th>Source land use</th><th>Area</th></tr></thead>
        <tbody>{detail.planning.map((row, index) => <tr key={index}><td>{row.label}</td><td>{number(row.area_m2)} m²</td></tr>)}</tbody></table></div>
        : <p className="parcel-fine-print">{text(parcel.loai_dat_qh) === 'Not provided' ? 'No planning breakdown is provided by this source.' : text(parcel.loai_dat_qh)}</p>}
      <dl className="parcel-source-details">{[['Plan', parcel.do_an], ['Decision', parcel.quyet_dinh]].map(([label, value]) =>
        text(value) !== 'Not provided' && <div key={String(label)}><dt>{String(label)}</dt><dd>{text(value)}</dd></div>)}</dl>
      {parcel.conflicting_land_use && <p className="parcel-fine-print">Source fragments have differing land-use codes; a single category has not been verified.</p>}
    </section>
  </>;
}
