import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { CitedText, GeneratedNotice, SourceCards, useElapsed } from './CitedText';

// Printable intervention sheet for one segment. "Données plateforme" sections come from the database
// (template, numbers as stored); "Assistant" sections are generated from the cited guide excerpts.
export default function InterventionSheet({ segment, onClose }) {
  const [sheet, setSheet] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(true);
  const elapsed = useElapsed(running);
  const scope = `sheet-${segment.segment_code}`;

  useEffect(() => {
    let cancelled = false;
    api.interventionSheet(segment.segment_code)
      .then(result => { if (!cancelled) setSheet(result); })
      .catch(err => { if (!cancelled) setError(err.message || 'La fiche n’a pas pu être générée.'); })
      .finally(() => { if (!cancelled) setRunning(false); });
    return () => { cancelled = true; };
  }, [segment.segment_code]);

  useEffect(() => {
    const onKey = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return <div className="sheet-overlay" role="dialog" aria-modal="true" aria-label="Fiche d’intervention">
    <article className="intervention-sheet">
      <header className="sheet-header">
        <div><span className="ministry-kicker">FICHE D’INTERVENTION · {new Date().toLocaleDateString('fr-TN', { dateStyle: 'long' })}</span>
          <h2>{segment.name || 'Segment sans nom'}</h2><p>{segment.segment_code}</p></div>
        <div className="sheet-actions no-print">
          <button type="button" className="ministry-primary" onClick={() => window.print()} disabled={!sheet}>Imprimer</button>
          <button type="button" className="ministry-secondary" onClick={onClose}>Fermer</button>
        </div>
      </header>
      {running && <p className="assistant-waiting" role="status">Analyse des documents… (environ 30 s) · {elapsed} s</p>}
      {error && <p className="ministry-message is-error">{error}</p>}
      {sheet && <>
        {!sheet.assistant_available && <div className="assistant-banner"><div><b>Assistant indisponible</b><span>Seules les données de la plateforme sont affichées ; les conseils issus des guides n’ont pas été générés.</span></div></div>}
        {sheet.sections.map(section => <section className={`sheet-section origin-${section.origin === 'données' ? 'data' : 'assistant'}`} key={section.key}>
          <h3>{section.title}<span>{section.origin === 'données' ? 'Données plateforme' : 'Assistant · guides cités'}</span></h3>
          {section.uncited && <p className="uncited-warning">Sans citation — vérifiez les sources ci-dessous avant d’appliquer ce conseil.</p>}
          {section.origin === 'données'
            ? <div className="sheet-data">{section.text}</div>
            : <CitedText text={section.text} scope={scope} count={sheet.sources.length}/>}
        </section>)}
        {sheet.assistant_available && sheet.sources.length > 0 && <GeneratedNotice/>}
        {sheet.sources.length > 0 && <section className="sheet-section"><h3>Sources<span>{sheet.sources.length} extraits</span></h3><SourceCards sources={sheet.sources} scope={scope}/></section>}
        <p className="assistant-meta">{sheet.model} · {(sheet.latency_ms / 1000).toFixed(0)} s · requête : « {sheet.query} »</p>
      </>}
    </article>
  </div>;
}
