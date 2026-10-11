import { useEffect, useRef, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';

export function ZoningDialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className="zoning-dialog solid-panel zoning-ui" aria-label={title} onCancel={onClose}>
    <header><h2>{title}</h2><button className="quiet-icon-button" onClick={onClose} aria-label="Close dialog"><X size={18}/></button></header>
    {children}
  </dialog>;
}

export function ActionDialog({ title, message, initial, onClose, onConfirm, busy, error }: {
  title: string; message?: string; initial?: string; onClose: () => void;
  onConfirm: (value: string) => Promise<boolean>; busy: boolean; error?: string;
}) {
  const [value, setValue] = useState(initial ?? '');
  return <ZoningDialog title={title} onClose={() => { if (!busy) onClose(); }}>
    <form onSubmit={async e => { e.preventDefault(); if (await onConfirm(value)) onClose(); }}>
      {message && <p>{message}</p>}
      {initial !== undefined && <label>Name<input autoFocus required disabled={busy} maxLength={120} value={value} onChange={e => setValue(e.target.value)}/></label>}
      {error && <p role="alert">{error}</p>}
      <footer><button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="zoning-primary" disabled={busy}>{busy ? 'Saving…' : 'Confirm'}</button></footer>
    </form>
  </ZoningDialog>;
}
