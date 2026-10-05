import {
  type ButtonHTMLAttributes,
  useRef,
} from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';

type MotionIconButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function MotionIconButton({
  children,
  type = 'button',
  ...buttonProps
}: MotionIconButtonProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const iconRef = useRef<HTMLSpanElement>(null);

  useGSAP(
    (_context, contextSafe) => {
      const button = buttonRef.current;
      const icon = iconRef.current;
      if (!button || !icon || !contextSafe) return;

      const animateIn = contextSafe(() => {
        const duration = motionDuration(0.18);
        if (!duration) return;
        gsap.to(icon, {
          y: -2,
          scale: 1.08,
          rotation: -4,
          duration,
          ease: 'power2.out',
          overwrite: 'auto',
        });
      });
      const animateOut = contextSafe(() => {
        const duration = motionDuration(0.2);
        if (!duration) return;
        gsap.to(icon, {
          y: 0,
          scale: 1,
          rotation: 0,
          duration,
          ease: 'power2.out',
          overwrite: 'auto',
          clearProps: 'transform',
        });
      });

      button.addEventListener('mouseenter', animateIn);
      button.addEventListener('mouseleave', animateOut);
      button.addEventListener('focus', animateIn);
      button.addEventListener('blur', animateOut);
      return () => {
        button.removeEventListener('mouseenter', animateIn);
        button.removeEventListener('mouseleave', animateOut);
        button.removeEventListener('focus', animateIn);
        button.removeEventListener('blur', animateOut);
      };
    },
    { scope: buttonRef },
  );

  return (
    <button
      {...buttonProps}
      ref={buttonRef}
      type={type}
    >
      <span ref={iconRef} className="motion-icon">
        {children}
      </span>
    </button>
  );
}
