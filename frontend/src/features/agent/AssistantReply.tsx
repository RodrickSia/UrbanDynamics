import { useEffect, useState } from 'react';
import { PixelRobot, type RobotState } from './PixelRobot';

export function AssistantText({ text }: { text: string }) {
  return <p>{text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => part.startsWith('**')
    ? <strong key={i}>{part.slice(2, -2)}</strong> : part.startsWith('`')
      ? <code key={i}>{part.slice(1, -1)}</code> : part)}</p>;
}

export function AssistantReply({ text, animate = false }: { text: string; animate?: boolean }) {
  const [count, setCount] = useState(animate ? 0 : text.length);
  const [state, setState] = useState<RobotState>(animate ? 'speaking' : 'idle');
  useEffect(() => {
    if (!animate) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let timer: ReturnType<typeof setTimeout>;
    let shown = 0;
    const step = Math.max(2, Math.ceil(text.length / 100));
    const reveal = () => {
      shown = reduced ? text.length : Math.min(text.length, shown + step);
      setCount(shown);
      if (shown < text.length) timer = setTimeout(reveal, 32);
      else {
        setState(reduced ? 'idle' : 'completed');
        timer = setTimeout(() => setState('idle'), 900);
      }
    };
    timer = setTimeout(reveal, 32);
    return () => clearTimeout(timer);
  }, [animate, text]);
  return <article data-role="assistant" className="assistant-reply">
    <PixelRobot state={animate ? state : 'idle'}/>
    <div className="assistant-bubble"><strong>Assistant</strong>
      <div aria-hidden={animate || undefined}><AssistantText text={animate ? text.slice(0, count) : text}/></div>
      {animate && <span className="sr-only">{text}</span>}
    </div>
  </article>;
}
