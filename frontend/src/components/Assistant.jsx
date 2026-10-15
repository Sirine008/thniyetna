import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { CitedText, GeneratedNotice, SourceCards, useElapsed } from './CitedText';

// "Assistant" tab (both ministries): questions in French over the field guides, answers with cited excerpts.
// The last 5 Q&A are kept for the browser session (sessionStorage), so they survive tab switches.
const HISTORY_SIZE = 5;
const historyKey = ministry => `thniyetna.assistant.${ministry}`;

function loadHistory(ministry) {
  try { return JSON.parse(sessionStorage.getItem(historyKey(ministry)) || '[]').slice(0, HISTORY_SIZE); }
  catch { return []; }
}

function saveHistory(ministry, items) {
  try { sessionStorage.setItem(historyKey(ministry), JSON.stringify(items)); } catch { /* storage unavailable */ }
}

export default function Assistant({ ministry }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState(() => loadHistory(ministry));
  const [status, setStatus] = useState({ state: 'checking' });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const elapsed = useElapsed(running);

  async function checkStatus() {
    setStatus({ state: 'checking' });
    try {
      const info = await api.assistantStatus();
      setStatus(info.ollama?.reachable ? { state: 'ok', info } : { state: 'down', detail: info.ollama?.error });
    } catch (err) { setStatus({ state: 'down', detail: err.message }); }
  }

  useEffect(() => { void checkStatus(); }, []);

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (text.length < 3 || running) return;
    setRunning(true); setError('');
    try {
      const result = await api.ask(text);
      const entry = { id: Date.now(), question: text, answer: result.answer, sources: result.sources, latency_ms: result.latency_ms, model: result.model };
      const next = [entry, ...history].slice(0, HISTORY_SIZE);
      setHistory(next); saveHistory(ministry, next); setQuestion('');
    } catch (err) {
      setError(err.message || 'La question n’a pas pu être traitée.');
      if (/Ollama|injoignable/i.test(err.message || '')) setStatus({ state: 'down', detail: err.message });
    } finally { setRunning(false); }
  }

  const down = status.state === 'down';
  return <section className="ministry-panel assistant-panel">
    <div className="ministry-panel-heading"><div><span className="ministry-kicker">GUIDES TECHNIQUES</span><h2>Assistant documentaire</h2></div>
      <span>{status.state === 'ok' ? `${status.info.documents} guides · ${status.info.chunks} extraits` : status.state === 'checking' ? 'Vérification…' : 'Hors service'}</span></div>
    {down && <div className="assistant-banner"><div><b>Assistant indisponible</b><span>Le service de langage ne répond pas. Les réponses reprendront dès son retour.</span></div><button type="button" className="ministry-secondary" onClick={checkStatus}>Vérifier à nouveau</button></div>}
    <form className="assistant-form" onSubmit={submit}>
      <label htmlFor="assistant-question">Votre question</label>
      <textarea id="assistant-question" rows={3} maxLength={1000} value={question} placeholder="Ex. : À quelle température poser un enrobé chaud ?" onChange={e => setQuestion(e.target.value)} disabled={running}/>
      <div className="assistant-actions">
        <button className="ministry-primary" disabled={running || down || question.trim().length < 3}>Demander</button>
        {running && <span className="assistant-waiting" role="status">Analyse des documents… (environ 30 s) · {elapsed} s</span>}
      </div>
    </form>
    {error && <p className="ministry-message is-error">{error}</p>}
    {history.length ? <div className="assistant-history">{history.map(entry => <article className="assistant-qa" key={entry.id}>
      <h3>{entry.question}</h3>
      <CitedText text={entry.answer} scope={`qa-${entry.id}`} count={entry.sources?.length || 0}/>
      <GeneratedNotice/>
      <SourceCards sources={entry.sources} scope={`qa-${entry.id}`}/>
      <p className="assistant-meta">{entry.model} · {(entry.latency_ms / 1000).toFixed(0)} s</p>
    </article>)}</div> : <p className="ministry-empty">Posez une question sur la réparation des chaussées, la signalisation des chantiers ou les déviations. Les 5 dernières réponses restent affichées pendant la session.</p>}
  </section>;
}
