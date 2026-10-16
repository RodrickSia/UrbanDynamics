import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from 'react';

export function useDraggableChat() {
  const panel = useRef<HTMLElement>(null);
  const drag = useRef<{ id: number; x: number; y: number; left: number; top: number } | null>(null);
  const place = (left: number, top: number) => {
    const node = panel.current, parent = node?.offsetParent;
    if (!node || !(parent instanceof HTMLElement)) return;
    node.style.left = `${Math.max(8, Math.min(left, parent.clientWidth - node.offsetWidth - 8))}px`;
    node.style.top = `${Math.max(8, Math.min(top, parent.clientHeight - node.offsetHeight - 8))}px`;
  };
  useEffect(() => {
    const node = panel.current, parent = node?.offsetParent;
    if (!node || !(parent instanceof HTMLElement)) return;
    const observer = new ResizeObserver(() => {
      if (node.dataset.moved) place(node.offsetLeft, node.offsetTop);
    });
    observer.observe(parent); observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !panel.current) return;
    event.preventDefault();
    const node = panel.current;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, left: node.offsetLeft, top: node.offsetTop };
    event.currentTarget.setPointerCapture(event.pointerId);
    node.dataset.dragging = 'true'; node.dataset.moved = 'true';
  };
  const onPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const current = drag.current;
    if (current?.id === event.pointerId) place(current.left + event.clientX - current.x, current.top + event.clientY - current.y);
  };
  const release = () => {
    drag.current = null;
    if (panel.current) delete panel.current.dataset.dragging;
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const node = panel.current;
    if (!node) return;
    if (event.key === 'Home') {
      event.preventDefault(); node.style.removeProperty('left'); node.style.removeProperty('top'); delete node.dataset.moved;
    }
    const directions: Record<string, number[]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const delta = directions[event.key];
    if (delta) {
      event.preventDefault(); node.dataset.moved = 'true';
      place(node.offsetLeft + delta[0] * 24, node.offsetTop + delta[1] * 24);
    }
  };
  return { panel, handle: { onPointerDown, onPointerMove, onPointerUp: release, onPointerCancel: release, onLostPointerCapture: release, onKeyDown } };
}
