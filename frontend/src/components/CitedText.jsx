import React, { useEffect, useState } from 'react';

// Shared pieces for generated answers: clickable citations [n], source cards with the exact excerpt,
// the verification notice, and an elapsed-seconds counter for the 30–40 s CPU answers.

export const GENERATED_NOTICE = 'Réponse générée à partir des guides cités — vérifiez les extraits avant d’agir.';
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

const sourceId = (scope, n) => `${scope}-src-${n}`;

function focusSource(scope, n) {
  const card = document.getElementById(sourceId(scope, n));
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.classList.add('is-cited');
  setTimeout(() => card.classList.remove('is-cited'), 1600);
}

// Text with [n] / [1, 2] turned into buttons that scroll to the matching source card.
export function CitedText({ text, scope, count }) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const numbers = match[1].split(',').map(n => Number(n.trim()));
    parts.push(<span className="citation-group" key={match.index}>[{numbers.map((n, i) => <React.Fragment key={n}>{i > 0 && ', '}{n >= 1 && n <= count
      ? <button type="button" className="citation-link" title={`Voir la source ${n}`} onClick={() => focusSource(scope, n)}>{n}</button>
      : n}</React.Fragment>)}]</span>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <div className="cited-text">{parts}</div>;
}

export function SourceCards({ sources, scope }) {
  if (!sources?.length) return null;
  return <div className="source-cards">{sources.map(source => <article className="source-card" id={sourceId(scope, source.n)} key={source.n}>
    <header><span className="source-number">[{source.n}]</span><b>{source.title}</b><span>{source.page ? `p. ${source.page}` : 'page non précisée'}</span></header>
    <blockquote>{source.excerpt || source.snippet}</blockquote>
  </article>)}</div>;
}

export function GeneratedNotice() {
  return <p className="generated-notice">{GENERATED_NOTICE}</p>;
}

// Seconds since `running` became true (0 when idle).
export function useElapsed(running) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) { setSeconds(0); return undefined; }
    const start = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return seconds;
}
