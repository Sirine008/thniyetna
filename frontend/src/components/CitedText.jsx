import React, { useEffect, useState } from 'react';
import { FileText, Info } from 'lucide-react';

// Shared pieces for generated answers: clickable citations [n], source list with the exact excerpt,
// the verification notice, and an elapsed-seconds counter for the 30–100 s CPU answers.

export const GENERATED_NOTICE = 'Réponse générée à partir des guides cités — vérifiez les extraits avant d’agir.';
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

const sourceId = (scope, n) => `${scope}-src-${n}`;

function focusSource(scope, n) {
  const card = document.getElementById(sourceId(scope, n));
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.focus({ preventScroll: true });
  card.classList.add('is-cited');
  setTimeout(() => card.classList.remove('is-cited'), 1600);
}

// Text with [n] / [1, 2] turned into buttons that scroll to the matching source.
export function CitedText({ text, scope, count }) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const numbers = match[1].split(',').map(n => Number(n.trim()));
    parts.push(<span className="citation-group" key={match.index}>[{numbers.map((n, i) => <React.Fragment key={n}>{i > 0 && ', '}{n >= 1 && n <= count
      ? <button type="button" className="citation-link" title={`Voir la source ${n}`} aria-label={`Source ${n}`} onClick={() => focusSource(scope, n)}>{n}</button>
      : n}</React.Fragment>)}]</span>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <div className="cited-text">{parts}</div>;
}

/** Sources: document title + page, the exact excerpt; each one is the target of its [n] citations. */
export function SourceCards({ sources, scope }) {
  if (!sources?.length) return null;
  return <ol className="sources">{sources.map(source => <li className="source-item" id={sourceId(scope, source.n)} key={source.n} tabIndex={-1}>
    <div className="source-head"><span className="source-number">[{source.n}]</span><FileText aria-hidden="true"/><b>{source.title}</b><span className="t-sm t-muted">{source.page ? `page ${source.page}` : 'page non précisée'}</span></div>
    <blockquote>{source.excerpt || source.snippet}</blockquote>
  </li>)}</ol>;
}

export function GeneratedNotice() {
  return <p className="generated-notice"><Info aria-hidden="true"/>{GENERATED_NOTICE}</p>;
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

/** Generation in progress: spinner, elapsed time, usual duration. No invented percentage. */
export function GeneratingState({ elapsed, what = 'Analyse des documents', usual = 'habituellement 30 à 100 s sur ce serveur' }) {
  return <div className="generating" role="status" aria-live="polite">
    <span className="spinner spinner-lg" aria-hidden="true"/>
    <div><p className="t-strong">{what}…</p><p className="t-sm t-muted"><span className="t-num">{elapsed}</span> s écoulées · {usual}</p>
      <div className="indeterminate" aria-hidden="true"><span/></div></div>
  </div>;
}
