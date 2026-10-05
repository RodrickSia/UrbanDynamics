import { useGSAP } from '@gsap/react';
import { gsap } from 'gsap';

gsap.registerPlugin(useGSAP);

export function motionDuration(seconds: number): number {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : seconds;
}

export { gsap, useGSAP };
