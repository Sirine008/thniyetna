import React, { useState } from 'react';
import { Check, Plus, Printer, Trash2 } from 'lucide-react';
import {
  AlertBadge, Badge, Button, Card, ConfirmModal, ConfirmedBadge, DataTable, DefinitionList, DemoBadge, DemoBanner, EmptyState,
  EventStateBadge, Field, KpiTile, Loading, MapLegend, Modal, Notice, PageHeader, PriorityBadge, ReportStateBadge, RiskBadge,
  SidePanel, SkeletonRows, Spinner, Tabs, Timeline, Toolbar, useToast,
} from '../ui';
import { dateTime, distance, pct, score } from '../lib/format';
import { REPORT_STATES } from '../lib/labels';

// Reference page of the design system (supervisor roles). Sample values below are typography and layout
// examples only — no figure on this page comes from or stands for platform data.
const COLOURS = [
  ['Accent (petrol)', ['--c-primary', '--c-primary-hover', '--c-primary-soft', '--c-primary-line', '--c-focus']],
  ['Neutres', ['--c-gray-25', '--c-gray-50', '--c-gray-100', '--c-gray-200', '--c-gray-300', '--c-gray-400', '--c-gray-500', '--c-gray-600', '--c-gray-700', '--c-gray-800', '--c-gray-900']],
  ['Risque faible / résolu', ['--c-green', '--c-green-bg', '--c-green-line', '--c-green-solid']],
  ['Risque moyen / en analyse', ['--c-yellow', '--c-yellow-bg', '--c-yellow-line', '--c-yellow-solid']],
  ['Risque élevé / à traiter', ['--c-orange', '--c-orange-bg', '--c-orange-line', '--c-orange-solid']],
  ['Risque critique / danger', ['--c-red', '--c-red-bg', '--c-red-line', '--c-red-solid']],
];
const TYPE = [['--fs-2xl', 'Titre de page'], ['--fs-xl', 'Titre de section'], ['--fs-lg', 'Titre de carte'], ['--fs-md', 'Texte courant et tableaux'], ['--fs-sm', 'Libellés de champ, textes secondaires'], ['--fs-xs', 'Badges, en-têtes de tableau, métadonnées']];
const SPACES = ['--sp-1', '--sp-2', '--sp-3', '--sp-4', '--sp-6', '--sp-8'];
const SAMPLE_ROWS = [
  { id: 'a', name: 'Exemple de ligne A', level: 'high', priority: 'P2', value: 0.4 },
  { id: 'b', name: 'Exemple de ligne B', level: 'low', priority: 'P4', value: 0.1 },
  { id: 'c', name: 'Exemple de ligne C', level: 'critical', priority: 'P1', value: 0.8 },
];

export default function DesignSystem() {
  const [tab, setTab] = useState('a');
  const [panel, setPanel] = useState(false);
  const [modal, setModal] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  const section = (title, children) => <Card title={title} headingLevel={2}>{children}</Card>;

  return <main className="design-page" id="contenu">
    <PageHeader kicker="Référence interne" title="Système de conception THNIYETNA" description="Jetons, composants et règles d’usage. Les valeurs affichées ici sont des exemples de mise en page, pas des données."/>

    {section('Couleurs', <div className="stack">{COLOURS.map(([name, vars]) => <div key={name}><h3 className="t-sm t-muted" style={{ marginBlockEnd: 8 }}>{name}</h3>
      <div className="swatches">{vars.map(v => <div className="swatch" key={v}><span style={{ background: `var(${v})` }}/><code>{v}</code></div>)}</div></div>)}
      <p className="t-sm t-muted">Le rouge, l’orange, le jaune et le vert sont réservés aux niveaux de risque, priorités et états ; toujours accompagnés d’un texte ou d’une icône.</p></div>)}

    {section('Typographie — IBM Plex Sans / IBM Plex Sans Arabic', <div className="stack-sm">{TYPE.map(([v, use]) => <div className="row" key={v} style={{ alignItems: 'baseline' }}>
      <code className="t-xs t-muted" style={{ inlineSize: 80 }}>{v}</code><span style={{ fontSize: `var(${v})`, fontWeight: v.includes('xl') ? 600 : 400 }}>{use}</span></div>)}
      <p dir="rtl" lang="ar" style={{ fontSize: 'var(--fs-lg)' }}>منزل بورقيبة — بنزرت</p></div>)}

    {section('Espacements, rayons, bordures', <div className="row" style={{ alignItems: 'flex-end', gap: 24 }}>{SPACES.map(v => <div key={v} className="stack-sm" style={{ alignItems: 'center' }}>
      <span style={{ inlineSize: `var(${v})`, blockSize: `var(${v})`, background: 'var(--c-primary)' }}/><code className="t-xs">{v}</code></div>)}
      <div className="stack-sm"><span className="card" style={{ inlineSize: 64, blockSize: 40, borderRadius: 'var(--radius-sm)' }}/><code className="t-xs">--radius-sm 4px</code></div>
      <div className="stack-sm"><span className="card" style={{ inlineSize: 64, blockSize: 40 }}/><code className="t-xs">--radius-md 6px</code></div></div>)}

    {section('Boutons', <div className="stack"><div className="row">
      <Button variant="primary" icon={Check}>Valider la détection</Button><Button icon={Printer}>Imprimer</Button>
      <Button variant="danger" icon={Trash2}>Désactiver le compte</Button><Button variant="ghost" icon={Plus}>Ajouter</Button>
      <Button variant="primary" loading>Enregistrement…</Button><Button disabled>Indisponible</Button></div>
      <div className="row"><Button size="sm">Petit</Button><Button>Normal</Button><Button size="lg" variant="primary">Grand (44 px, mobile)</Button></div></div>)}

    {section('Badges', <div className="stack-sm">
      <div className="row">{['low', 'medium', 'high', 'critical'].map(l => <RiskBadge key={l} level={l}/>)}</div>
      <div className="row">{['P1', 'P2', 'P3', 'P4'].map(p => <PriorityBadge key={p} priority={p}/>)}</div>
      <div className="row">{Object.keys(REPORT_STATES).map(s => <ReportStateBadge key={s} status={s}/>)}</div>
      <div className="row"><EventStateBadge validated={false}/><EventStateBadge validated/><AlertBadge topic="driver.reroute.alert"/><AlertBadge topic="driver.route.warning"/><AlertBadge superseded/><AlertBadge topic="route.assignment"/><ConfirmedBadge count={3}/><DemoBadge/><Badge>Neutre</Badge></div>
    </div>)}

    {section('Indicateurs (KPI)', <><div className="grid-kpi"><KpiTile label="Libellé d’un compteur" value="—" to="/design"/><KpiTile label="Sans lien" value="—"/></div>
      <p className="t-sm t-muted" style={{ marginBlockStart: 8 }}>Uniquement pour des comptes renvoyés par l’API ; chaque tuile mène à sa liste filtrée.</p></>)}

    {section('Messages', <div className="stack-sm">
      <Notice tone="info" title="Information">Texte d’explication.</Notice><Notice tone="success" title="Statut enregistré."/>
      <Notice tone="warning" title="Avertissement">À vérifier avant d’agir.</Notice><Notice tone="error" title="Erreur">Message renvoyé par l’API.</Notice>
      <DemoBanner/>
      <div className="row"><Button onClick={() => toast.push('Statut enregistré.')}>Afficher un toast</Button><Button onClick={() => toast.push('Échec de l’enregistrement.', 'error')}>Toast d’erreur</Button></div>
    </div>)}

    {section('Formulaires', <div className="form-grid">
      <Field label="Identifiant" help="Lettres, chiffres, . _ -" required><input className="input"/></Field>
      <Field label="Statut"><select className="select"><option>En analyse</option></select></Field>
      <Field label="Champ en erreur" error="Au moins 8 caractères."><input className="input" defaultValue="abc"/></Field>
      <Field label="Note de traitement"><textarea className="textarea"/></Field>
    </div>)}

    {section('Onglets', <><Tabs label="Exemple" value={tab} onChange={setTab} tabs={[{ key: 'a', label: 'Premier', count: 3 }, { key: 'b', label: 'Second' }, { key: 'c', label: 'Troisième' }]}/>
      <p className="t-sm t-muted" style={{ marginBlockStart: 8 }}>Flèches gauche / droite pour changer d’onglet.</p></>)}

    {section('Tableau (tri, pagination, lignes empilées sur mobile)', <Card bodyClass={null} className="card-flat">
      <Toolbar count={`${SAMPLE_ROWS.length} lignes`}><Field label="Recherche" className="field-grow"><input className="input" type="search"/></Field></Toolbar>
      <DataTable rowKey={r => r.id} rows={SAMPLE_ROWS} pageSize={2} initialSort={{ key: 'value', dir: 'desc' }} onRowClick={() => setPanel(true)} rowLabel={r => `Ouvrir ${r.name}`}
        columns={[{ key: 'name', label: 'Nom' }, { key: 'level', label: 'Risque', render: r => <RiskBadge level={r.level}/>, sort: r => ['low', 'medium', 'high', 'critical'].indexOf(r.level) },
          { key: 'priority', label: 'Priorité', render: r => <PriorityBadge priority={r.priority}/> }, { key: 'value', label: 'Score', num: true, render: r => score(r.value) }]}/>
    </Card>)}

    {section('États de chargement et vides', <div className="stack"><Loading/><Spinner label="Analyse des documents…"/><SkeletonRows rows={2} cols={4}/>
      <EmptyState title="Aucun signalement à traiter." action={<Button>Réinitialiser les filtres</Button>}>Les nouveaux signalements apparaissent ici.</EmptyState></div>)}

    {section('Panneau latéral, modale, confirmation', <div className="row"><Button onClick={() => setPanel(true)}>Ouvrir le panneau</Button><Button onClick={() => setModal(true)}>Ouvrir une modale</Button><Button variant="danger" onClick={() => setConfirm(true)}>Confirmation</Button></div>)}

    {section('Frise (historique)', <Timeline label="Exemple" items={[{ title: 'Nouveau', meta: dateTime('2026-10-23T17:44:00Z') }, { title: 'En analyse', meta: dateTime('2026-10-23T19:02:00Z'), note: 'Note de traitement.', state: 'current' }, { title: 'Résolu', state: 'pending' }]}/>)}

    {section('Formats', <DefinitionList items={[['Score (2 décimales)', score(0.3940)], ['Pourcentage', pct(0.354)], ['Distance', `${distance(450)} · ${distance(2340)}`], ['Date (heure de Tunis)', dateTime('2026-10-23T17:44:00Z')]]}/>)}

    {section('Légende de carte', <MapLegend show={['risk', 'hazards', 'route', 'line']}/>)}

    {panel && <SidePanel title="Panneau latéral" subtitle="Détail d’une ligne" onClose={() => setPanel(false)} footer={<Button variant="primary" onClick={() => setPanel(false)}>Fermer</Button>}><p>Échap ferme le panneau ; le focus revient sur l’élément d’origine.</p></SidePanel>}
    {modal && <Modal title="Modale" onClose={() => setModal(false)} footer={<Button variant="primary" onClick={() => setModal(false)}>Fermer</Button>}><p>Contenu de la modale.</p></Modal>}
    {confirm && <ConfirmModal title="Désactiver le compte ?" danger confirmLabel="Désactiver" onCancel={() => setConfirm(false)} onConfirm={() => setConfirm(false)}>Le compte ne pourra plus se connecter.</ConfirmModal>}
  </main>;
}
