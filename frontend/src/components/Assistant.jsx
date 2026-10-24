import React, { useEffect, useRef, useState } from 'react';
import { RefreshCw, Send, TriangleAlert } from 'lucide-react';
import { api } from '../lib/api';
import { number, plural } from '../lib/format';
import { apiErrorMessage } from '../lib/labels';
import { Button, Card, EmptyState, Notice } from '../ui';
import { CitedText, GeneratedNotice, GeneratingState, SourceCards, useElapsed } from './CitedText';

// « Assistant » section (both ministries): questions in French over the field guides, answers with cited excerpts.
// Same requests as before (GET /assistant/status, POST /assistant/ask); the last 5 Q&A stay in sessionStorage
// (same key and format, newest first), shown here in reading order.
const HISTORY_SIZE = 5;
const historyKey = ministry => `thniyetna.assistant.${ministry}`;
const HAS_CITATION = /\[\d+(?:\s*,\s*\d+)*\]/;

function loadHistory(ministry) {
  try { return JSON.parse(sessionStorage.getItem(historyKey(ministry)) || '[]').slice(0, HISTORY_SIZE); }
  catch { return []; }
}

function saveHistory(ministry, items) {
  try { sessionStorage.setItem(historyKey(ministry), JSON.stringify(items)); } catch { /* storage unavailable */ }
}

function Exchange({ entry }) {
  const scope = `qa-${entry.id}`;
  const cited = HAS_CITATION.test(entry.answer || '');
  return <article className="chat-exchange" aria-label={`Question : ${entry.question}`}>
    <div className="chat-question"><span className="chat-who">Question</span><p>{entry.question}</p></div>
    <div className="chat-answer">
      <span className="chat-who">Réponse</span>
      <CitedText text={entry.answer} scope={scope} count={entry.sources?.length || 0}/>
      {!cited && <p className="uncited"><TriangleAlert aria-hidden="true"/>Sans citation : cette réponse ne renvoie à aucun extrait des guides. Ne l’appliquez pas sans vérifier les sources ci-dessous.</p>}
      <GeneratedNotice/>
      {entry.sources?.length > 0 && <details className="chat-sources" open={!cited || undefined}>
        <summary>{plural(entry.sources.length, 'source')} : {[...new Set(entry.sources.map(s => s.title))].join(' ; ')}</summary>
        <SourceCards sources={entry.sources} scope={scope}/>
      </details>}
      <p className="chat-meta">{entry.model} · {number((entry.latency_ms || 0) / 1000)} s</p>
    </div>
  </article>;
}

export default function Assistant({ ministry }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState(() => loadHistory(ministry));
  const [status, setStatus] = useState({ state: 'checking' });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [asked, setAsked] = useState('');
  const elapsed = useElapsed(running);
  const end = useRef();

  async function checkStatus() {
    setStatus({ state: 'checking' });
    try {
      const info = await api.assistantStatus();
      setStatus(info.ollama?.reachable ? { state: 'ok', info } : { state: 'down', detail: info.ollama?.error });
    } catch (err) { setStatus({ state: 'down', detail: apiErrorMessage(err.message) }); }
  }

  useEffect(() => { void checkStatus(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [history.length, running]);

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (text.length < 3 || running) return;
    setRunning(true); setError(''); setAsked(text);
    try {
      const result = await api.ask(text);
      const entry = { id: Date.now(), question: text, answer: result.answer, sources: result.sources, latency_ms: result.latency_ms, model: result.model };
      const next = [entry, ...history].slice(0, HISTORY_SIZE);
      setHistory(next); saveHistory(ministry, next); setQuestion('');
    } catch (err) {
      setError(apiErrorMessage(err.message || 'La question n’a pas pu être traitée.'));
      if (/Ollama|injoignable/i.test(err.message || '')) setStatus({ state: 'down', detail: err.message });
    } finally { setRunning(false); setAsked(''); }
  }

  const down = status.state === 'down';
  const statusText = status.state === 'ok' ? `${plural(status.info.documents, 'guide')} · ${plural(status.info.chunks, 'extrait')} indexés` : status.state === 'checking' ? 'Vérification du service…' : 'Service indisponible';
  return <Card className="chat" bodyClass={null} title="Guides techniques" actions={<span className="t-sm t-muted" role="status">{statusText}</span>}>
    {down && <div className="card-body"><Notice tone="warning" title="Assistant indisponible" action={<Button size="sm" icon={RefreshCw} onClick={checkStatus}>Vérifier à nouveau</Button>}>Le service de langage ne répond pas ; les réponses reprendront dès son retour.</Notice></div>}
    <div className="chat-log" aria-live="polite">
      {!history.length && !running && <EmptyState title="Posez une question sur les guides de terrain.">Réparation des chaussées, signalisation de chantier, déviations. Les réponses citent les extraits utilisés ; les 5 dernières restent affichées pendant la session.</EmptyState>}
      {[...history].reverse().map(entry => <Exchange key={entry.id} entry={entry}/>)}
      {running && <article className="chat-exchange"><div className="chat-question"><span className="chat-who">Question</span><p>{asked}</p></div>
        <GeneratingState elapsed={elapsed} what="Analyse des documents" usual="environ 30 s, jusqu’à 90 s sur ce serveur"/></article>}
      <div ref={end}/>
    </div>
    {error && <div className="card-body" style={{ paddingBlockEnd: 0 }}><Notice tone="error" title="La question n’a pas été traitée.">{error}</Notice></div>}
    <form className="chat-composer" onSubmit={submit}>
      <label htmlFor="assistant-question" className="field-label">Votre question</label>
      <textarea id="assistant-question" className="textarea" rows={2} maxLength={1000} value={question} placeholder="Ex. : À quelle température poser un enrobé chaud ?"
        onChange={e => setQuestion(e.target.value)} disabled={running}
        onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(e); }} aria-describedby="assistant-help"/>
      <div className="row-between">
        <span id="assistant-help" className="field-help">Ctrl + Entrée pour envoyer · {question.trim().length < 3 ? '3 caractères minimum' : `${question.length} / 1000`}</span>
        <Button type="submit" variant="primary" icon={Send} loading={running} disabled={down || question.trim().length < 3}>Envoyer la question</Button>
      </div>
    </form>
  </Card>;
}
