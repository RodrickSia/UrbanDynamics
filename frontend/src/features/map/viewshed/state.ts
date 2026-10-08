import { aimAt, createViewshed, type GeoPoint, type Viewshed } from './math';

export interface ViewshedState {
  items: Viewshed[];
  selectedId: string | null;
  phase: 'idle' | 'observer' | 'target' | 'editing';
}
export const initialViewsheds: ViewshedState = { items: [], selectedId: null, phase: 'idle' };
export const MAX_VIEWSHEDS = 8;
export type ViewshedAction =
  | { type: 'start' | 'done' | 'cancel' | 'delete' | 'clear' }
  | { type: 'place'; point: GeoPoint; id: string }
  | { type: 'preview'; point: GeoPoint }
  | { type: 'select'; id: string }
  | { type: 'update'; view: Viewshed };
export function viewshedReducer(state: ViewshedState, action: ViewshedAction): ViewshedState {
  const update = (view: Viewshed) => ({
    ...state,
    items: state.items.map((v) => (v.id === view.id ? view : v)),
  });
  switch (action.type) {
    case 'start': {
      const clean = viewshedReducer(state, { type: 'cancel' });
      return clean.items.length >= MAX_VIEWSHEDS
        ? { ...clean, selectedId: clean.items[0].id, phase: 'editing' }
        : { ...clean, phase: 'observer' };
    }
    case 'clear':
      return initialViewsheds;
    case 'cancel':
      return {
        items:
          state.phase === 'target'
            ? state.items.filter((v) => v.id !== state.selectedId)
            : state.items,
        selectedId: null,
        phase: 'idle',
      };
    case 'done':
      return state.phase === 'target' || state.phase === 'observer'
        ? viewshedReducer(state, { type: 'cancel' })
        : { ...state, selectedId: null, phase: 'idle' };
    case 'delete':
      return {
        items: state.items.filter((v) => v.id !== state.selectedId),
        selectedId: null,
        phase: 'idle',
      };
    case 'select': {
      if (state.phase === 'target' && state.selectedId === action.id) return state;
      const clean = viewshedReducer(state, { type: 'cancel' });
      return clean.items.some((v) => v.id === action.id)
        ? { ...clean, selectedId: action.id, phase: 'editing' }
        : state;
    }
    case 'update':
      return update(action.view);
    case 'place':
      if (state.phase === 'observer')
        return {
          items: [...state.items, createViewshed(action.id, action.point)],
          selectedId: action.id,
          phase: 'target',
        };
      if (state.phase === 'target')
        return {
          ...state,
          items: state.items.map((v) => (v.id === state.selectedId ? aimAt(v, action.point) : v)),
          phase: 'editing',
        };
      return state;
    case 'preview':
      return state.phase === 'target'
        ? {
            ...state,
            items: state.items.map((v) => (v.id === state.selectedId ? aimAt(v, action.point) : v)),
          }
        : state;
  }
}
