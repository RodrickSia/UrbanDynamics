import { useRef, useState } from 'react';
import { PixelRobot } from './PixelRobot';
import './agentLauncher.css';

export function AgentLauncher({ open, onClick }: { open?: boolean; onClick: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  const [look, setLook] = useState(0);
  const [greeting, setGreeting] = useState(false);
  return <button ref={button} type="button" className="agent-launcher" aria-label="Planning assistant"
    aria-expanded={open} onClick={onClick} data-open={!!open}
    onPointerMove={event => {
      const rect = button.current?.getBoundingClientRect();
      if (rect) setLook(Math.max(-2, Math.min(2, (event.clientX - rect.left - rect.width / 2) / 12)));
    }} onPointerEnter={() => setGreeting(true)} onPointerLeave={() => { setLook(0); setGreeting(false); }}
    onFocus={() => setGreeting(true)} onBlur={() => setGreeting(false)}>
    <span className="agent-walker"><PixelRobot state={greeting ? 'completed' : 'idle'} look={look} walking={!greeting && !open}/></span>
    <span className="agent-launcher-label">Ask AI</span>
  </button>;
}
