import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BuildingFloorEditor } from './BuildingFloorEditor';
import type { BuildingInput } from './developmentTypes';

describe('per-floor editing', () => {
  it('edits only the chosen floor, preserves other overrides, and resets to defaults', () => {
    const onChange = vi.fn();
    const second = { floor: 2, floor_height: 4, space_use_id: 'office', counts_gfa: true, counts_far: false };
    const draft = { floors: 3, floor_height: 3.2, space_use_id: 'residential', counts_gfa: true, counts_far: true,
      floor_overrides: [second] } as BuildingInput;
    render(<BuildingFloorEditor draft={draft} onChange={onChange} catalog={{ version: 1, building_types: [], space_uses: [
      { id: 'residential', name: 'Residential', color: '#D79B8C', default_floor_height: 3.2 },
      { id: 'commercial', name: 'Commercial', color: '#C18EAD', default_floor_height: 4 },
      { id: 'office', name: 'Office', color: '#86A5C5', default_floor_height: 3.6 },
    ] }}/>);
    fireEvent.change(screen.getByLabelText('Floor use'), { target: { value: 'commercial' } });
    expect(onChange).toHaveBeenLastCalledWith({ floor_overrides: [
      { floor: 1, floor_height: 3.2, space_use_id: 'commercial', counts_gfa: true, counts_far: true }, second,
    ] });
    fireEvent.change(screen.getByLabelText('Edit floor'), { target: { value: '2' } });
    expect((screen.getByLabelText('Floor height (m)') as HTMLInputElement).value).toBe('4');
    expect((screen.getByLabelText('FAR') as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Reset floor' }));
    expect(onChange).toHaveBeenLastCalledWith({ floor_overrides: [] });
  });
});
