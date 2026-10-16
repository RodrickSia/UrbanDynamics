import type { CSSProperties } from 'react';
import './pixelRobot.css';

export type RobotState = 'idle' | 'thinking' | 'speaking' | 'completed';

/** Integer-grid artwork stays crisp at every supported avatar size. */
export function PixelRobot({ state = 'idle', look = 0, walking = false }: {
  state?: RobotState; look?: number; walking?: boolean;
}) {
  return <span className="pixel-robot" data-state={state} data-walking={walking}
    style={{ '--robot-look': `${look}px` } as CSSProperties} aria-hidden="true">
    <svg viewBox="0 0 40 44" fill="none" shapeRendering="crispEdges" focusable="false">
      <ellipse className="robot-shadow" cx="20" cy="41" rx="11" ry="2" fill="#163954" opacity=".16"/>
      <g className="robot-body">
        <g className="robot-head">
          <path d="M19 5h2v5h-2z" fill="#3978A5"/><path className="robot-beacon" d="M18 2h4v4h-4z" fill="#50D5EB"/>
          <path d="M9 10h22v2h3v17h-3v2H9v-2H6V12h3z" fill="#234E72"/>
          <path d="M9 12h22v2h1v13h-3v2H11v-2H8V14h1z" fill="#B8DDF2"/>
          <path d="M11 13h18v2H11z" fill="#F3FBFF"/>
          <path d="M10 17h20v10H10z" fill="#102E48"/>
          <g className="robot-face">
            <g className="robot-eyes"><path d="M13 19h4v4h-4zM23 19h4v4h-4z" fill="#65EDFF"/><path d="M13 19h2v2h-2zM23 19h2v2h-2z" fill="#DAFFFF"/></g>
            <path className="robot-mouth" d="M18 24h4v1h-4z" fill="#65EDFF"/>
            <path className="robot-smile" d="M17 23h2v1h2v-1h2v2h-6z" fill="#65EDFF"/>
          </g>
          <path d="M3 17h3v8H3zM34 17h3v8h-3z" fill="#6EA9D0"/>
        </g>
        <path d="M12 31h16v7H12z" fill="#3978A5"/><path d="M14 31h12v5H14z" fill="#B8DDF2"/>
        <path className="robot-heart" d="M18 32h4v3h-4z" fill="#50D5EB"/>
        <path className="robot-arm robot-arm-left" d="M8 31h3v6H8z" fill="#6EA9D0"/>
        <path className="robot-arm robot-arm-right" d="M29 31h3v6h-3z" fill="#6EA9D0"/>
        <path className="robot-foot robot-foot-left" d="M12 38h6v3h-6z" fill="#234E72"/>
        <path className="robot-foot robot-foot-right" d="M22 38h6v3h-6z" fill="#234E72"/>
      </g>
      <g className="robot-thoughts" fill="#1689C9"><path d="M29 5h2v2h-2z"/><path d="M33 3h2v2h-2z"/><path d="M37 5h2v2h-2z"/></g>
      <path className="robot-spark" d="M3 6h2v2h2v2H5v2H3v-2H1V8h2z" fill="#FFD078"/>
    </svg>
  </span>;
}
