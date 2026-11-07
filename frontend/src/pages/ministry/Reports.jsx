import React, { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Save } from 'lucide-react';
import { PointMap } from '../../components/LeafletMap';
import { api } from '../../lib/api';
import { coords, dateTime, plural } from '../../lib/format';
import { REPORT_STATES, REPORT_TARGET_STATES, apiErrorMessage, reportCategoryLabel, reportStateLabel } from '../../lib/labels';
import { Button, Card, DataTable, DefinitionList, DemoBadge, DemoBanner, EmptyState, Field, Loading, Notice, ReportStateBadge, SidePanel, SkeletonRows, Timeline, Toolbar } from '../../ui';
import { matches, useUrlFilter } from './filters';

const OPEN = s => !['resolved', 'rejected'].includes(s);
export const STATE_FILTERS = [['tous', 'Tous', () => true], ['a-traiter', 'À traiter (non clos)', c => OPEN(c.status)],
  ...Object.keys(REPORT_STATES).map(s => [s, reportStateLabel(s), c => c.status === s])];

/** History of a report: received, then every status change (GET /platform/complaints/{id}/history). */
function ReportHistory({ complaint, version }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    setRows(null); setError('');
    api.complaintHistory(complaint.id).then(r => alive && setRows(r)).catch(e => alive && setError(apiErrorMessage(e.message)));
    return () => { alive = false; };
  }, [complaint.id, version]);
  if (error) return <Notice tone="error" title="Historique indisponible">{error}</Notice>;
  if (!rows) return <Loading label="Chargement de l’historique…"/>;
  const items = [{ title: 'Reçu', meta: dateTime(complaint.created_at) },
    ...rows.map(h => ({ title: reportStateLabel(h.new_status), meta: `${dateTime(h.changed_at)}${h.changed_by ? ` · ${h.changed_by}` : ''}`, note: h.note || null }))];
  items[items.length - 1].state = 'current';
  return <Timeline label="Historique du signalement" items={items}/>;
}

function ReportPanel({ complaint, w, onClose }) {
  // Pre-selected status: same default as before (a new report goes to « En analyse »)
  const initial = { status: complaint.status === 'open' ? 'under_review' : complaint.status, note: '' };
  const [draft, setDraft] = useState(initial);
  const [version, setVersion] = useState(0);
  useEffect(() => { setDraft({ status: complaint.status === 'open' ? 'under_review' : complaint.status, note: '' }); }, [complaint.id, complaint.status]);
  const save = async event => {
    event.preventDefault();
    if (await w.updateComplaint(complaint, draft)) { setDraft(d => ({ ...d, note: '' })); setVersion(v => v + 1); }
  };
  return <SidePanel title="Signalement citoyen" subtitle={`Reçu le ${dateTime(complaint.created_at)}`} onClose={onClose}>
    {complaint.demo && <DemoBanner/>}
    <div className="panel-section">
      <p style={{ fontSize: 'var(--fs-lg)', lineHeight: 'var(--lh-lg)' }}>{complaint.description}</p>
      <div className="row"><ReportStateBadge status={complaint.status}/><span className="t-sm t-muted">{reportCategoryLabel(complaint.category)}</span></div>
    </div>
    <div className="panel-section"><h3>Photo</h3>
      {complaint.image_url
        ? <a href={complaint.image_url} target="_blank" rel="noreferrer" className="row" style={{ alignItems: 'flex-start', flexDirection: 'column', gap: 4 }}>
            <img src={complaint.image_url} alt={`Photo du signalement : ${complaint.description}`} style={{ maxBlockSize: 260, border: 'var(--border)', borderRadius: 'var(--radius-sm)' }}/>
            <span className="t-sm row" style={{ gap: 4 }}>Ouvrir l’image<ExternalLink size={14} aria-hidden="true"/></span></a>
        : <p className="t-sm t-muted">Aucune photo jointe.</p>}
    </div>
    <div className="panel-section"><h3>Position</h3>
      <PointMap lat={Number(complaint.latitude)} lon={Number(complaint.longitude)} label={`Position du signalement : ${coords(complaint.latitude, complaint.longitude)}`}/>
      <DefinitionList items={[['Coordonnées', <span className="t-num">{coords(complaint.latitude, complaint.longitude)}</span>], ['Catégorie', reportCategoryLabel(complaint.category)]]}/>
    </div>
    <div className="panel-section"><h3>Historique</h3><ReportHistory complaint={complaint} version={version}/></div>
    <form className="panel-section" onSubmit={save}><h3>Traitement</h3>
      <Field label="Nouveau statut"><select className="select" value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}>
        {REPORT_TARGET_STATES.map(s => <option key={s} value={s}>{reportStateLabel(s)}</option>)}</select></Field>
      <Field label="Note de traitement" help="Visible dans l’historique du signalement."><textarea className="textarea" rows={3} value={draft.note} onChange={e => setDraft({ ...draft, note: e.target.value })}/></Field>
      <div><Button type="submit" variant="primary" icon={Save} loading={w.saving === complaint.id}>Enregistrer le statut</Button></div>
    </form>
  </SidePanel>;
}

export default function Reports({ w }) {
  const [state, setState] = useUrlFilter('statut', 'tous'); // all reports by default, as before
  const [query, setQuery] = useUrlFilter('q', '');
  const [origin, setOrigin] = useUrlFilter('donnees', 'toutes');
  const [openId, setOpenId] = useUrlFilter('signalement', '');
  const filter = (STATE_FILTERS.find(f => f[0] === state) || STATE_FILTERS[0])[2];
  const rows = useMemo(() => w.complaints.filter(c => filter(c) && matches(query, c.description, reportCategoryLabel(c.category))
    && (origin === 'toutes' || (origin === 'demo') === Boolean(c.demo))), [w.complaints, state, query, origin]); // eslint-disable-line react-hooks/exhaustive-deps
  const open = w.complaints.find(c => c.id === openId);
  const toProcess = w.complaints.filter(c => OPEN(c.status)).length;

  const columns = [
    { key: 'created_at', label: 'Reçu le', render: c => <span className="t-num">{dateTime(c.created_at)}</span>, sort: c => c.created_at, width: 170 },
    { key: 'description', label: 'Signalement', render: c => <><span className="cell-title clamp-2">{c.description}</span><span className="cell-sub">{reportCategoryLabel(c.category)}{c.image_url ? ' · photo jointe' : ''}</span>{c.demo && <DemoBadge/>}</>, sort: c => c.description },
    { key: 'status', label: 'Statut', render: c => <ReportStateBadge status={c.status}/>, sort: c => Object.keys(REPORT_STATES).indexOf(c.status), width: 190 },
    { key: 'open', label: '', sort: false, render: c => <div className="cell-actions"><Button size="sm" onClick={e => { e.stopPropagation(); setOpenId(c.id); }}>Traiter</Button></div>, width: 100 },
  ];
  return <>
    <p className="t-muted">{plural(toProcess, 'signalement à traiter', 'signalements à traiter')} sur {plural(w.complaints.length, 'reçu', 'reçus')}.</p>
    <Card bodyClass={null}>
      <Toolbar count={w.loaded ? plural(rows.length, 'résultat') : 'Chargement…'}>
        <Field label="Rechercher" className="field-grow"><input className="input" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Texte du signalement"/></Field>
        <Field label="Statut"><select className="select" value={state} onChange={e => setState(e.target.value)}>{STATE_FILTERS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Données"><select className="select" value={origin} onChange={e => setOrigin(e.target.value)}><option value="toutes">Toutes</option><option value="reelles">Réelles uniquement</option><option value="demo">Démo uniquement</option></select></Field>
      </Toolbar>
      {!w.loaded && w.loading ? <SkeletonRows rows={6} cols={4}/>
        : <DataTable caption="Signalements citoyens" rowKey={c => c.id} rows={rows} columns={columns} initialSort={{ key: 'created_at', dir: 'desc' }}
          onRowClick={c => setOpenId(c.id)} selectedKey={openId} rowLabel={c => `Ouvrir le signalement : ${c.description}`}
          empty={<EmptyState title={w.complaints.length ? 'Aucun signalement ne correspond aux filtres.' : 'Aucun signalement reçu.'}
            action={w.complaints.length ? <Button onClick={() => { setState('tous'); setQuery(''); setOrigin('toutes'); }}>Afficher tous les signalements</Button> : null}>
            {w.complaints.length ? null : 'Les signalements envoyés par les citoyens apparaissent ici.'}</EmptyState>}/>}
    </Card>
    {open && <ReportPanel complaint={open} w={w} onClose={() => setOpenId('')}/>}
  </>;
}
