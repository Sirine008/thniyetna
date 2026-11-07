import React, { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import BottomNav from '../components/BottomNav';
import { api } from '../lib/api';
import { dateTime, plural } from '../lib/format';
import { REPORT_FLOW, apiErrorMessage, reportCategoryLabel, reportStateLabel } from '../lib/labels';
import { ButtonLink, DemoBadge, EmptyState, Loading, Notice, ReportStateBadge, Timeline } from '../ui';

// « Mes contributions »: the citizen's reports with the progress of their current status.
// Only the reception date is known here (the status history is reserved to the ministry), so later steps have no date.
const CITIZEN_LABELS = { open: 'Reçu' };
const stepLabel = s => CITIZEN_LABELS[s] || reportStateLabel(s);

export function claimSteps(item) {
  if (item.status === 'rejected') return [{ title: 'Reçu', meta: dateTime(item.created_at) }, { title: 'Rejeté', state: 'current' }];
  const at = Math.max(0, REPORT_FLOW.indexOf(item.status));
  return REPORT_FLOW.map((s, i) => ({ title: stepLabel(s), meta: i === 0 ? dateTime(item.created_at) : null, state: i < at ? 'done' : i === at ? 'current' : 'pending' }));
}

export default function Claims() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api.myClaims().then(setItems).catch(err => { setItems([]); setError(apiErrorMessage(err.message)); }); }, []);
  const open = (items || []).filter(i => !['resolved', 'rejected'].includes(i.status)).length;
  return <div className="m-shell">
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <header className="m-header"><span className="wordmark">THNIYETNA</span><ButtonLink to="/citizen/report" variant="primary" size="sm" icon={Plus}>Signaler</ButtonLink></header>
    <main id="contenu" className="m-content">
      <div><h1>Mes contributions</h1>{items && <p className="t-muted">{plural(items.length, 'signalement envoyé', 'signalements envoyés')}{items.length ? ` · ${plural(open, 'en cours de traitement', 'en cours de traitement')}` : ''}</p>}</div>
      {error && <Notice tone="error" title="Signalements indisponibles">{error}</Notice>}
      {!items && <Loading label="Chargement de vos signalements…"/>}
      {items && !items.length && !error && <EmptyState title="Aucun signalement envoyé." action={<ButtonLink to="/citizen/report" variant="primary" icon={Plus}>Signaler un défaut</ButtonLink>}>Vos signalements et leur état de traitement apparaissent ici.</EmptyState>}
      {items && items.length > 0 && <ol className="claim-feed">{items.map(item => <li key={item.id} className="claim-entry">
        <div className="claim-head">
          {item.image_url && <img src={item.image_url} alt="" className="claim-thumb" loading="lazy"/>}
          <div className="claim-main">
            <div className="row"><ReportStateBadge status={item.status} label={stepLabel(item.status)}/>{item.demo && <DemoBadge/>}</div>
            <h2>{item.description}</h2>
            <p className="t-sm t-muted">{reportCategoryLabel(item.category)} · envoyé le {dateTime(item.created_at)}</p>
          </div>
        </div>
        <details className="claim-progress"><summary>Suivi du traitement</summary><Timeline label={`Suivi du signalement : ${item.description}`} items={claimSteps(item)}/></details>
      </li>)}</ol>}
    </main>
    <BottomNav kind="citizen"/>
  </div>;
}
