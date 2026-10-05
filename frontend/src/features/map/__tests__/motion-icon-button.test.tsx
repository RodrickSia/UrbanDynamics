import { fireEvent, render, screen } from '@testing-library/react';
import { Plus } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';

import { MotionIconButton } from '../components/MotionIconButton';

const { animateTo } = vi.hoisted(() => ({ animateTo: vi.fn() }));

vi.mock('../motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../motion')>();
  return {
    ...actual,
    gsap: { ...actual.gsap, to: animateTo },
    motionDuration: (seconds: number) => seconds,
  };
});

describe('MotionIconButton', () => {
  it('animates its icon on hover and restores it when the pointer leaves', () => {
    render(
      <MotionIconButton aria-label="Zoom in">
        <Plus aria-hidden="true" />
      </MotionIconButton>,
    );

    const button = screen.getByRole('button', { name: 'Zoom in' });
    const icon = button.querySelector('.motion-icon');
    expect(icon).not.toBeNull();

    fireEvent.mouseEnter(button);
    expect(animateTo).toHaveBeenCalledWith(
      icon,
      expect.objectContaining({ y: -2, scale: 1.08, overwrite: 'auto' }),
    );

    fireEvent.mouseLeave(button);
    expect(animateTo).toHaveBeenLastCalledWith(
      icon,
      expect.objectContaining({ y: 0, scale: 1, overwrite: 'auto' }),
    );
  });
});
