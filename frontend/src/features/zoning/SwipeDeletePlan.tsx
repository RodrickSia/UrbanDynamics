import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react';

const REVEAL_PX = 88;
const OVERDRAG_PX = 24;

export function SwipeDeletePlan({ name, disabled, onDelete, children }: {
  name: string; disabled: boolean; onDelete: () => void; children: ReactNode;
}) {
  const [revealed, setRevealed] = useState(false);
  const [offset, setOffset] = useState<number | null>(null);
  const [jelly, setJelly] = useState(false);
  const start = useRef<{ x: number; y: number; pointerId: number } | null>(null);
  const suppressClick = useRef(false);
  const jellyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (jellyTimer.current) clearTimeout(jellyTimer.current); }, []);
  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current || start.current.pointerId !== event.pointerId) return;
    const dx = event.clientX - start.current.x;
    const dy = event.clientY - start.current.y;
    if (Math.abs(dx) > 12 && Math.abs(dx) > Math.abs(dy)) {
      setRevealed((offset ?? (revealed ? -REVEAL_PX : 0)) < -REVEAL_PX / 2);
      if (offset !== null && offset < -REVEAL_PX - 8) {
        setJelly(true);
        if (jellyTimer.current) clearTimeout(jellyTimer.current);
        jellyTimer.current = setTimeout(() => setJelly(false), 500);
      }
      suppressClick.current = true;
    }
    start.current = null;
    setOffset(null);
  };
  return <div className="zoning-swipe-delete" role="group" aria-label={`Swipe left or press Delete to reveal delete for ${name}`}
    tabIndex={disabled ? -1 : 0} data-revealed={revealed} data-dragging={offset !== null} data-jelly={jelly}
    onKeyDown={event => {
      if (event.key === 'Escape' && revealed) { setRevealed(false); event.stopPropagation(); }
      if ((event.key === 'Delete' || event.key === 'Backspace') && !disabled) {
        event.preventDefault(); setRevealed(true); event.stopPropagation();
      }
    }}>
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
          const next = (revealed ? -REVEAL_PX : 0) + dx;
          setOffset(Math.max(-REVEAL_PX - OVERDRAG_PX, Math.min(0, next < -REVEAL_PX ? -REVEAL_PX + (next + REVEAL_PX) * .22 : next)));
        }
      }}
      onPointerUp={finish} onPointerCancel={() => { start.current = null; setOffset(null); }}
      onClickCapture={event => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } }}>
      {children}
    </div>
  </div>;
}
