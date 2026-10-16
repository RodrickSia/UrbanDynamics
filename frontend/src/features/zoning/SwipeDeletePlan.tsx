import { useRef, useState, type PointerEvent, type ReactNode } from 'react';
import { ChevronLeft } from 'lucide-react';

const REVEAL_PX = 88;

export function SwipeDeletePlan({ name, disabled, onDelete, children }: {
  name: string; disabled: boolean; onDelete: () => void; children: ReactNode;
}) {
  const [revealed, setRevealed] = useState(false);
  const [offset, setOffset] = useState<number | null>(null);
  const start = useRef<{ x: number; y: number; pointerId: number } | null>(null);
  const suppressClick = useRef(false);
  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current || start.current.pointerId !== event.pointerId) return;
    const dx = event.clientX - start.current.x;
    const dy = event.clientY - start.current.y;
    if (Math.abs(dx) > 12 && Math.abs(dx) > Math.abs(dy)) {
      setRevealed(dx < -45 || (revealed && dx < 45));
      suppressClick.current = true;
    }
    start.current = null;
    setOffset(null);
  };
  return <div className="zoning-swipe-delete" data-revealed={revealed} data-dragging={offset !== null}>
    <button type="button" className="zoning-swipe-confirm" disabled={disabled || !revealed}
      tabIndex={revealed ? 0 : -1} aria-hidden={!revealed} onClick={onDelete}>Delete</button>
    <div className="zoning-swipe-content" style={{ width: `calc(100% - ${-(offset ?? (revealed ? -REVEAL_PX : 0))}px)` }}
      onPointerDown={event => { if (!disabled && event.button === 0) start.current = { x: event.clientX, y: event.clientY, pointerId: event.pointerId }; }}
      onPointerMove={event => {
        if (!start.current || start.current.pointerId !== event.pointerId) return;
        const dx = event.clientX - start.current.x;
        const dy = event.clientY - start.current.y;
        if (Math.abs(dx) > 12 && Math.abs(dx) > Math.abs(dy)) {
          event.currentTarget.setPointerCapture(event.pointerId);
          setOffset(Math.max(-REVEAL_PX, Math.min(0, (revealed ? -REVEAL_PX : 0) + dx)));
        }
      }}
      onPointerUp={finish} onPointerCancel={() => { start.current = null; setOffset(null); }}
      onClickCapture={event => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } }}
      onKeyDown={event => { if (event.key === 'Escape' && revealed) { setRevealed(false); event.stopPropagation(); } }}>
      {children}
      <button type="button" className="zoning-swipe-trigger" disabled={disabled}
        aria-label={`${revealed ? 'Hide' : 'Reveal'} delete for ${name}`}
        aria-expanded={revealed} title={revealed ? 'Hide delete' : 'Swipe left to delete'}
        onClick={() => setRevealed(value => !value)}><ChevronLeft size={17} aria-hidden="true"/></button>
    </div>
  </div>;
}
