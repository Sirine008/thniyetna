import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Printer, TriangleAlert, X } from 'lucide-react';
import { api } from '../lib/api';
import { date, dateTime, distance, number, pct, score } from '../lib/format';
import { apiErrorMessage, conditionLabel, defectTitle, factorEffect, factorName, reportCategoryLabel, reportStateLabel, roadClassLabel, sourceLabel } from '../lib/labels';
import { Badge, Button, DemoBadge, DemoBanner, Notice, PriorityBadge, RiskBadge } from '../ui';
import { CitedText, GeneratedNotice, GeneratingState, SourceCards, useElapsed } from './CitedText';

// Printable intervention sheet for one segment (POST /assistant/intervention/{segment_code}, unchanged).
// « Données plateforme » sections are rendered from the structured `facts` of the response (same values as the
// backend template text, in French, rounded, in Tunisian time); « Assistant » sections are the generated text
// with its [n] citations, shown as received. The sheet renders in a portal so that printing shows only the sheet.
const Origin = ({ data }) => <span className={`sheet-origin${data ? '' : ' is-assistant'}`}>{data ? 'Données plateforme' : 'Assistant · guides cités'}</span>;

function Constat({ facts, noDefect, fallback }) {
  if (!facts) return <div className="sheet-text">{fallback}</div>;
  const { segment, events = [], complaints = [], risk } = facts;
  return <div className="stack-sm">
    <dl className="dl">
      <dt>Segment</dt><dd>{segment.name || 'Segment sans nom'} <span className="t-mono t-sm t-muted">{segment.segment_code}</span></dd>
      <dt>Classe de route</dt><dd>{roadClassLabel(segment.road_class)}</dd>
      {risk && <><dt>État prédit (M2)</dt><dd>{conditionLabel(risk.predicted_condition)}</dd></>}
    </dl>
    {noDefect && <Notice tone="info" title="Aucun défaut ouvert sur ce segment">Aucune détection M1 ouverte et aucun signalement citoyen ouvert à moins de 100 m. Les conseils ci-dessous sont des conseils généraux d’inspection, pas une intervention.</Notice>}
    {events.length > 0 && <table className="table sheet-table"><caption>Détections M1</caption><thead><tr><th>Classe</th><th className="num">Sévérité</th><th className="num">Confiance</th><th>État</th><th>Observée le</th></tr></thead>
      <tbody>{events.map((e, i) => <tr key={i}><td data-label="Classe">{defectTitle(e.event_type)}{e.source ? <span className="cell-sub">{sourceLabel(e.source)}</span> : null}{e.demo && <DemoBadge/>}</td>
        <td className="num" data-label="Sévérité">{pct(e.severity)}</td><td className="num" data-label="Confiance">{pct(e.confidence)}</td><td data-label="État">{e.validated ? 'Validée' : 'Non validée'}</td><td className="t-num" data-label="Observée le">{dateTime(e.observed_at)}</td></tr>)}</tbody></table>}
    {complaints.length > 0 && <table className="table sheet-table"><caption>Signalements citoyens à moins de 100 m</caption><thead><tr><th>Catégorie</th><th className="num">Distance</th><th>Statut</th><th>Reçu le</th></tr></thead>
      <tbody>{complaints.map((c, i) => <tr key={i}><td data-label="Catégorie">{reportCategoryLabel(c.category)}{c.demo && <DemoBadge/>}</td><td className="num" data-label="Distance">{distance(c.distance_m)}</td><td data-label="Statut">{reportStateLabel(c.status)}</td><td className="t-num" data-label="Reçu le">{dateTime(c.created_at)}</td></tr>)}</tbody></table>}
  </div>;
}

function Priority({ risk, fallback }) {
  if (risk === undefined) return <div className="sheet-text">{fallback}</div>;
  if (!risk) return <p>Aucun score de risque M2 valide pour ce segment : priorité non déterminée.</p>;
  return <div className="stack-sm">
    <div className="row"><PriorityBadge priority={risk.maintenance_priority}/><RiskBadge level={risk.risk_level}/><span className="t-sm">Score de risque <b className="t-num">{score(risk.risk_score)}</b> sur 1</span></div>
    <p className="t-sm t-muted">Modèle {risk.model_version || 'inconnu'} · calculé le {dateTime(risk.computed_at)}{risk.valid_until ? ` · valable jusqu’au ${dateTime(risk.valid_until)}` : ''}</p>
    {risk.top_factors?.length > 0 && <table className="table sheet-table"><caption>Facteurs principaux du modèle</caption><thead><tr><th>Facteur</th><th>Effet</th><th className="num">Valeur</th><th className="num">Contribution</th></tr></thead>
      <tbody>{risk.top_factors.map((f, i) => <tr key={i}><td data-label="Facteur">{factorName(f)}</td><td data-label="Effet">{factorEffect(f)}</td><td className="num" data-label="Valeur">{number(f.value, Number.isInteger(Number(f.value)) ? 0 : 2)}</td><td className="num" data-label="Contribution">{score(f.contribution)}</td></tr>)}</tbody></table>}
  </div>;
}

function Missing({ text, facts }) {
  const lines = text.split('\n').map(l => l.replace(/^-\s*/, '').trim()).filter(Boolean)
    .map(l => (l.startsWith('Dernier passage d’inspection') || l.startsWith("Dernier passage d'inspection")) && facts?.last_inspection_at ? `Dernier passage d’inspection : ${dateTime(facts.last_inspection_at)}.` : l);
  return <ul className="sheet-list">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul>;
}

export default function InterventionSheet({ segment, onClose }) {
  const [sheet, setSheet] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(true);
  const elapsed = useElapsed(running);
  const scope = `sheet-${segment.segment_code}`;
  const ref = useRef();

  useEffect(() => {
    let cancelled = false;
    api.interventionSheet(segment.segment_code)
      .then(result => { if (!cancelled) setSheet(result); })
      .catch(err => { if (!cancelled) setError(apiErrorMessage(err.message || 'La fiche n’a pas pu être générée.')); })
      .finally(() => { if (!cancelled) setRunning(false); });
    return () => { cancelled = true; };
  }, [segment.segment_code]);

  useEffect(() => {
    const opener = document.activeElement;
    document.body.classList.add('sheet-open');
    ref.current?.focus();
    const onKey = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); document.body.classList.remove('sheet-open'); opener?.focus?.(); };
  }, [onClose]);

  const facts = sheet?.facts;
  const demo = Boolean(facts && [...(facts.events || []), ...(facts.complaints || [])].some(r => r.demo));
  const body = section => {
    if (section.origin !== 'données') return <CitedText text={section.text} scope={scope} count={sheet.sources.length}/>;
    if (section.key === 'constat') return <Constat facts={facts} noDefect={sheet.no_defect} fallback={section.text}/>;
    if (section.key === 'priorite') return <Priority risk={facts ? facts.risk : undefined} fallback={section.text}/>;
    if (section.key === 'manquant') return <Missing text={section.text} facts={facts}/>;
    return <div className="sheet-text">{section.text}</div>;
  };

  return createPortal(<div className="sheet-wrap" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
    <article className="sheet-page" ref={ref} tabIndex={-1}>
      <header className="sheet-head">
        <div>
          <p className="sheet-kicker">Fiche d’intervention · {date(new Date())} · Ministère de l’Équipement</p>
          <h2 id="sheet-title">{segment.name || 'Segment sans nom'}</h2>
          <p className="t-mono t-sm t-muted">{segment.segment_code}</p>
        </div>
        <div className="row no-print">
          <Button variant="primary" icon={Printer} onClick={() => window.print()} disabled={!sheet}>Imprimer</Button>
          <Button icon={X} onClick={onClose}>Fermer</Button>
        </div>
      </header>
      {demo && <DemoBanner>La fiche s’appuie sur au moins une donnée de démonstration.</DemoBanner>}
      {running && <GeneratingState elapsed={elapsed} what="Génération de la fiche : lecture des données et des guides"/>}
      {error && <Notice tone="error" title="La fiche n’a pas pu être générée.">{error}</Notice>}
      {sheet && <>
        {!sheet.assistant_available && <Notice tone="warning" title="Assistant indisponible">Seules les données de la plateforme sont affichées ; les conseils issus des guides n’ont pas été générés.</Notice>}
        {sheet.sections.map(section => <section className={`sheet-section${section.origin === 'données' ? '' : ' is-assistant'}`} key={section.key} aria-labelledby={`sheet-${section.key}`}>
          <h3 id={`sheet-${section.key}`}>{section.title}<Origin data={section.origin === 'données'}/></h3>
          {section.uncited && <p className="uncited"><TriangleAlert aria-hidden="true"/>Sans citation : vérifiez les sources ci-dessous avant d’appliquer ce conseil.</p>}
          {body(section)}
        </section>)}
        {sheet.assistant_available && sheet.sources.length > 0 && <GeneratedNotice/>}
        {sheet.sources.length > 0 && <section className="sheet-section"><h3>Sources<Badge>{sheet.sources.length} extraits</Badge></h3><SourceCards sources={sheet.sources} scope={scope}/></section>}
        <p className="sheet-meta">Modèle de langage {sheet.model} · {number(sheet.latency_ms / 1000)} s · requête : « {sheet.query} »</p>
      </>}
    </article>
  </div>, document.body);
}
