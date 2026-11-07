import React, { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, CircleX, FileText, Info, Send, TriangleAlert, Wrench, X } from 'lucide-react';
import { api } from '../lib/api';
import { dateTime, number, plural, time } from '../lib/format';
import { agentActionStateLabel, agentArgLabel, agentToolLabel, agentToolSetLabel, apiErrorMessage, conditionLabel, defectTitle, priorityLabel,
  reportCategoryLabel, reportStateLabel, roadClassLabel, sourceLabel } from '../lib/labels';
import { Badge, Button, Card, DemoBadge, EmptyState, Notice, PriorityBadge, RiskBadge } from '../ui';
import { ImageBoxes } from '../ui/ImageBoxes';
import { CitedText, GeneratingState, SourceCards, useElapsed } from './CitedText';

// « Agent » section (Équipement): the model chooses tools (POST /assistant/agent), then answers.
// Shown in order: the question, each tool call, the answer, the PROPOSED ACTIONS (cards « Confirmer » / « Ignorer »:
// nothing runs before a human confirms), the raw tool results (the real numbers, as returned by the API) and a
// « Fiche d'intervention complète » button for each segment named in the answer.
const HISTORY_SIZE = 3;
const HISTORY_KEY = 'thniyetna.agent.equipment';
const AGENT_NOTICE = 'Réponse rédigée par l’agent à partir des outils ci-dessus — comparez les chiffres avec les données avant d’agir.';
const DASHBOARD_LABELS = { open_complaints: 'Signalements ouverts', unvalidated_events: 'Détections à valider',
  events_24h: 'Événements des dernières 24 h', active_inspections: 'Inspections en cours' };

function loadHistory() {
  try { return JSON.parse(sessionStorage.getItem(HISTORY_KEY) || '[]').slice(0, HISTORY_SIZE); } catch { return []; }
}
function saveHistory(items) {
  try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(items)); } catch { /* storage unavailable */ }
}

const argsText = args => Object.entries(args || {}).map(([k, v]) => `${agentArgLabel(k)} : ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ');
// Numbers exactly as returned by the API (no rounding), so they can be compared with the answer.
const raw = value => (value === null || value === undefined || value === '' ? '—' : String(value));

function Step({ step }) {
  const Icon = step.ok ? CircleCheck : CircleX;
  return <li className="row" style={{ alignItems: 'flex-start', gap: 8 }}>
    <Icon aria-hidden="true" style={{ flex: 'none', marginBlockStart: 2 }}/>
    <div>
      <p className="t-sm"><span className="t-strong">Outil appelé : {agentToolLabel(step.tool)}</span>{argsText(step.arguments) && <span className="t-muted"> ({argsText(step.arguments)})</span>}</p>
      <p className={`t-sm ${step.ok ? 't-muted' : ''}`}>{step.result_summary} · <span className="t-num">{number(step.ms)}</span> ms</p>
    </div>
  </li>;
}

function SegmentsTable({ result }) {
  if (!result.segments?.length) return <p className="t-sm t-muted">Aucun segment de priorité {result.priorities.join(', ')}.{result.hint ? ' L’outil a proposé d’élargir à P3.' : ''}</p>;
  return <div className="table-wrap"><table className="table">
    <caption className="t-sm t-muted">Segments renvoyés par l’outil (valeurs de la base, non arrondies)</caption>
    <thead><tr><th>Priorité</th><th>Segment</th><th>Classe</th><th>État prédit</th><th>Défauts ouverts</th><th>Risque M2</th></tr></thead>
    <tbody>{result.segments.map(s => <tr key={s.segment_code}>
      <td data-label="Priorité"><PriorityBadge priority={s.maintenance_priority}/></td>
      <td data-label="Segment"><span className="cell-title">{s.name || 'Segment sans nom'}</span><span className="cell-sub t-mono">{s.segment_code}</span>{s.demo && <DemoBadge/>}</td>
      <td data-label="Classe">{roadClassLabel(s.road_class)}</td>
      <td data-label="État prédit">{conditionLabel(s.predicted_condition)}</td>
      <td data-label="Défauts ouverts" className="t-num">{raw(s.open_defects)}</td>
      <td data-label="Risque M2"><span className="row" style={{ gap: 6 }}><RiskBadge level={s.risk_level}/><span className="t-num t-sm">{raw(s.risk_score)}</span></span></td>
    </tr>)}</tbody>
  </table></div>;
}

function Facts({ result }) {
  const risk = result.risk;
  return <>
    <p className="t-sm"><span className="t-mono">{result.segment.segment_code}</span> · {result.segment.name || 'Segment sans nom'} {result.demo && <DemoBadge/>}</p>
    <dl className="dl">
      <dt>Détections M1 ouvertes</dt><dd className="t-num">{result.events.length}</dd>
      <dt>Signalements à moins de 100 m</dt><dd className="t-num">{result.complaints.length}</dd>
      <dt>Priorité · risque M2</dt><dd>{risk ? <>{priorityLabel(risk.maintenance_priority)} · <span className="t-num">{raw(risk.risk_score)}</span></> : 'Aucun score M2 valide'}</dd>
      <dt>Dernier passage d’inspection</dt><dd>{result.last_inspection_at ? dateTime(result.last_inspection_at) : 'Aucun'}</dd>
    </dl>
  </>;
}

function ToolResult({ item, scope }) {
  const { tool, result } = item;
  let body = null;
  if (tool === 'list_priority_segments') body = <SegmentsTable result={result}/>;
  else if (tool === 'get_segment_facts') body = <Facts result={result}/>;
  else if (tool === 'get_intervention_sheet') body = <>
    {result.demo && <DemoBadge/>}
    {result.sections.map(s => <div key={s.title}><p className="t-strong t-sm">{s.title}</p><div className="sheet-text t-sm">{s.text}</div></div>)}
    <p className="t-xs t-muted">{result.note}</p></>;
  else if (tool === 'search_guides') body = result.excerpts.length ? <SourceCards sources={result.excerpts} scope={scope}/> : <p className="t-sm t-muted">Aucun extrait pertinent.</p>;
  else if (tool === 'get_equipment_dashboard') body = <dl className="dl">{Object.entries(result).map(([k, v]) => <React.Fragment key={k}><dt>{DASHBOARD_LABELS[k] || k}</dt><dd className="t-num">{raw(v)}</dd></React.Fragment>)}</dl>;
  return <details className="chat-sources" open>
    <summary>{agentToolLabel(tool)}{item.arguments?.segment_code ? ` · ${item.arguments.segment_code}` : ''}</summary>
    <div className="stack-sm">{body}</div>
  </details>;
}

const ACTION_TOOLS = new Set(['plan_intervention', 'notify_transport', 'generate_full_sheet', 'propose_validation']);
const STATE_TONE = { proposed: 'primary', confirmed: 'green', rejected: 'neutral', expired: 'neutral', failed: 'red' };

function Evidence({ action }) {
  const ev = action.evidence || {};
  if (action.type === 'propose_validation' && ev.event) {
    const e = ev.event;
    return <div className="stack-sm">
      <ImageBoxes src={ev.frame?.media_uri || e.media_uri} alt={`Photo de la détection : ${defectTitle(e.event_type)}`} maxHeight={260}/>
      <dl className="dl">
        <dt>Classe</dt><dd>{defectTitle(e.event_type)}</dd>
        <dt>Confiance du modèle M1</dt><dd className="t-num">{raw(ev.frame?.confidence ?? e.confidence)}</dd>
        <dt>Sévérité (indice visuel)</dt><dd className="t-num">{raw(e.severity)}</dd>
        <dt>Source · date</dt><dd>{sourceLabel(e.source)} · {dateTime(e.observed_at)}</dd>
      </dl>
    </div>;
  }
  if (action.type === 'plan_intervention' && ev.complaints?.length) {
    return <ul className="stack-sm" style={{ paddingInlineStart: 18 }}>{ev.complaints.map(c => <li key={c.id} className="t-sm">
      {reportCategoryLabel(c.category)} · {reportStateLabel(c.status)} · « {c.description} » {c.demo && <DemoBadge/>}</li>)}</ul>;
  }
  return null;
}

function ActionResult({ action }) {
  const r = action.result || {};
  if (action.status === 'failed') return <Notice tone="error" title="L’exécution a échoué.">{r.error}</Notice>;
  if (action.status === 'rejected') return <p className="t-sm t-muted">Action ignorée : elle ne sera pas exécutée.</p>;
  if (action.status === 'expired') return <p className="t-sm t-muted">Proposition expirée : relancez l’agent.</p>;
  if (action.status !== 'confirmed') return null;
  if (action.type === 'plan_intervention') return <Notice tone="success" title="Intervention planifiée.">{plural(r.count, 'signalement')} passé(s) à « Intervention planifiée » · note : « {r.note} ».</Notice>;
  if (action.type === 'notify_transport') return <Notice tone="success" title="Message envoyé au superviseur Transport."/>;
  if (action.type === 'propose_validation') return <Notice tone="success" title="Détection validée."/>;
  if (action.type === 'generate_full_sheet' && r.sheet) return <div className="stack-sm">
    <Notice tone="success" title={`Fiche générée en ${number((r.sheet.latency_ms || 0) / 1000)} s.`}/>
    {r.sheet.sections.map(s => <div key={s.key}><p className="t-strong t-sm">{s.title}</p><div className="sheet-text t-sm">{s.text}</div></div>)}
    {r.sheet.sources?.length > 0 && <SourceCards sources={r.sheet.sources} scope={`action-${action.id}`}/>}
  </div>;
  return null;
}

function ActionCard({ action, onDecided }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const elapsed = useElapsed(busy === 'confirm');
  async function decide(kind) {
    setBusy(kind); setError('');
    try {
      const out = await (kind === 'confirm' ? api.confirmAgentAction(action.id) : api.rejectAgentAction(action.id));
      onDecided({ status: out.status, result: out.result, decided_by: out.decided_by, decided_at: out.decided_at });
    } catch (err) {
      const msg = apiErrorMessage(err.message);
      setError(msg);
      if (/expirée/i.test(msg)) onDecided({ status: 'expired' });
    } finally { setBusy(''); }
  }
  const open = action.status === 'proposed' && action.id;
  return <section className="card" aria-label={`Action proposée : ${agentToolLabel(action.type)}`} style={{ padding: 12 }}>
    <div className="row-between">
      <span className="t-strong">{agentToolLabel(action.type)}</span>
      <span className="row" style={{ gap: 6 }}>{action.demo && <DemoBadge/>}<Badge tone={STATE_TONE[action.status] || 'neutral'}>{agentActionStateLabel(action.status)}</Badge></span>
    </div>
    <p>{action.summary}</p>
    <p className="t-sm t-strong">Ce qui changera :</p>
    <ul className="stack-sm" style={{ paddingInlineStart: 18 }}>{(action.changes || []).map(c => <li key={c} className="t-sm">{c}</li>)}</ul>
    <Evidence action={action}/>
    {open && <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      <Button variant="primary" icon={Check} loading={busy === 'confirm'} disabled={Boolean(busy)} onClick={() => decide('confirm')}>Confirmer</Button>
      <Button icon={X} loading={busy === 'reject'} disabled={Boolean(busy)} onClick={() => decide('reject')}>Ignorer</Button>
      {action.expires_at && <span className="t-xs t-muted">Expire à {time(action.expires_at)} · rien n’est exécuté sans votre confirmation</span>}
    </div>}
    {busy === 'confirm' && action.type === 'generate_full_sheet' && <GeneratingState elapsed={elapsed} what="Génération de la fiche complète" usual="environ 100 s sur ce serveur"/>}
    {!action.id && <p className="t-xs t-muted">Proposition non enregistrée : elle ne peut pas être confirmée.</p>}
    {error && <Notice tone="error" title="Décision refusée.">{error}</Notice>}
    <ActionResult action={action}/>
  </section>;
}

function Exchange({ entry, onSheet, onAction }) {
  const scope = `agent-${entry.id}`;
  const r = entry.result;
  const actions = r.actions || [];
  const data = r.tool_results.filter(item => !ACTION_TOOLS.has(item.tool));
  return <article className="chat-exchange" aria-label={`Question : ${entry.question}`}>
    <div className="chat-question"><span className="chat-who">Question</span><p>{entry.question}</p></div>
    {r.steps.length > 0 && <ol className="stack-sm" aria-label="Outils appelés" style={{ listStyle: 'none', padding: 0 }}>{r.steps.map((s, i) => <Step key={i} step={s}/>)}</ol>}
    <div className="chat-answer">
      <span className="chat-who">Réponse de l’agent</span>
      <CitedText text={r.answer} scope={scope} count={Math.max(0, ...r.sources.map(s => s.n))}/>
      {r.warnings.map(w => <p className="uncited" key={w}><TriangleAlert aria-hidden="true"/>{w}</p>)}
      <p className="generated-notice"><Info aria-hidden="true"/>{AGENT_NOTICE}</p>
      {r.segments.length > 0 && <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>{r.segments.map(s =>
        <Button key={s.segment_code} size="sm" icon={FileText} onClick={() => onSheet(s)} aria-label={`Fiche d’intervention complète : ${s.name || s.segment_code}`}>
          Fiche d’intervention complète · {s.segment_code}</Button>)}</div>}
      {actions.length > 0 && <div className="stack-sm"><p className="t-strong t-sm">Actions proposées ({actions.length}) — à confirmer ou ignorer</p>
        {actions.map((a, i) => <ActionCard key={a.id || i} action={a} onDecided={patch => onAction(entry.id, i, patch)}/>)}</div>}
      {data.length > 0 && <div className="stack-sm"><p className="t-strong t-sm">Données utilisées ({plural(data.length, 'résultat')} d’outil)</p>
        {data.map((item, i) => <ToolResult key={i} item={item} scope={scope}/>)}</div>}
      <p className="chat-meta">{r.model}{r.tool_set ? ` · ${agentToolSetLabel(r.tool_set)}` : ''} · {plural(r.rounds, 'série')} d’outils · {number((r.latency_ms || 0) / 1000)} s
        {r.calls?.length > 0 && <> · appels au modèle : {r.calls.map(c => `${number(c.llm_ms / 1000, 1)} s`).join(' + ')}</>}</p>
    </div>
  </article>;
}

export default function Agent({ onSheet }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState(loadHistory);
  const [running, setRunning] = useState(false);
  const [asked, setAsked] = useState('');
  const [error, setError] = useState('');
  const elapsed = useElapsed(running);
  const end = useRef();

  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [history.length, running]);

  // On opening: refresh the proposals still « À confirmer » (the server marks those older than 30 min expired).
  useEffect(() => {
    const open = history.flatMap(e => (e.result.actions || []).filter(a => a.id && a.status === 'proposed').map(a => a.id));
    if (!open.length) return;
    api.agentActions(open).then(rows => {
      const byId = Object.fromEntries(rows.map(r => [r.id, r]));
      setHistory(current => {
        const next = current.map(e => ({ ...e, result: { ...e.result, actions: (e.result.actions || []).map(a =>
          (byId[a.id] ? { ...a, status: byId[a.id].status, result: byId[a.id].result, decided_by: byId[a.id].decided_by } : a)) } }));
        saveHistory(next);
        return next;
      });
    }).catch(() => { /* keep the stored state; a decision would still be checked by the server */ });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Store the human decision on the proposal (kept in the session history, like the answers).
  function updateAction(entryId, index, patch) {
    setHistory(current => {
      const next = current.map(e => (e.id !== entryId ? e : { ...e, result: { ...e.result,
        actions: e.result.actions.map((a, i) => (i === index ? { ...a, ...patch } : a)) } }));
      saveHistory(next);
      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (text.length < 3 || running) return;
    setRunning(true); setError(''); setAsked(text);
    try {
      const result = await api.agent(text);
      const next = [{ id: Date.now(), question: text, result }, ...history].slice(0, HISTORY_SIZE);
      setHistory(next); saveHistory(next); setQuestion('');
    } catch (err) {
      setError(apiErrorMessage(err.message || 'La question n’a pas pu être traitée.'));
    } finally { setRunning(false); setAsked(''); }
  }

  return <Card className="chat" bodyClass={null} title="Agent de l’Équipement" actions={<span className="t-sm t-muted">Lecture seule · actions sur confirmation · modèle local</span>}>
    <div className="chat-log" aria-live="polite">
      {!history.length && !running && <EmptyState title="Demandez à l’agent de préparer votre travail.">
        Il choisit lui-même les outils (segments prioritaires, faits d’un segment, fiche, guides, tableau de bord), puis résume en français. Il peut aussi proposer des actions (planifier, prévenir le Transport, générer la fiche, valider une détection) : rien n’est exécuté tant que vous n’avez pas confirmé.</EmptyState>}
      {[...history].reverse().map(entry => <Exchange key={entry.id} entry={entry} onSheet={onSheet} onAction={updateAction}/>)}
      {running && <article className="chat-exchange"><div className="chat-question"><span className="chat-who">Question</span><p>{asked}</p></div>
        <GeneratingState elapsed={elapsed} what="L’agent consulte les outils" usual="souvent 1 à 3 min sur ce serveur (plusieurs appels au modèle)"/></article>}
      <div ref={end}/>
    </div>
    {error && <div className="card-body" style={{ paddingBlockEnd: 0 }}><Notice tone="error" title="La question n’a pas été traitée.">{error}</Notice></div>}
    <form className="chat-composer" onSubmit={submit}>
      <label htmlFor="agent-question" className="field-label">Votre demande</label>
      <textarea id="agent-question" className="textarea" rows={2} maxLength={1000} value={question} disabled={running}
        placeholder="Ex. : Quels segments dois-je traiter en priorité cette semaine et que faut-il faire ?"
        onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(e); }} aria-describedby="agent-help"/>
      <div className="row-between">
        <span id="agent-help" className="field-help"><Wrench aria-hidden="true" style={{ inlineSize: 14, blockSize: 14, verticalAlign: 'middle' }}/> Ctrl + Entrée pour envoyer · l’agent propose, vous décidez</span>
        <Button type="submit" variant="primary" icon={Send} loading={running} disabled={question.trim().length < 3}>Envoyer</Button>
      </div>
    </form>
  </Card>;
}
