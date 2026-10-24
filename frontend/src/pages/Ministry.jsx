import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, ClipboardList, Gauge, Inbox, Map, RefreshCw, Route, ScanSearch, Truck, Users, Wrench } from 'lucide-react';
import InterventionSheet from '../components/InterventionSheet';
import SupervisorLayout from '../layouts/SupervisorLayout';
import { getSession } from '../lib/auth';
import { Button, Notice, useToast } from '../ui';
import { sessionUsername, useWorkspace } from './ministry/useWorkspace';
import Accounts from './ministry/Accounts';
import Assistant from '../components/Assistant';
import Assignments from './ministry/Assignments';
import Fleet from './ministry/Fleet';
import Network from './ministry/Network';
import TransportHome from './ministry/TransportHome';
import Detections from './ministry/Detections';
import EquipmentHome from './ministry/EquipmentHome';
import Inspections from './ministry/Inspections';
import Priorities from './ministry/Priorities';
import Reports from './ministry/Reports';

const AssistantView = ({ w }) => <Assistant ministry={w.ministry}/>;

// Sections of each ministry: URL `?vue=<key>` (so KPI tiles and links can open a filtered list).
const SECTIONS = {
  equipment: [
    { key: 'accueil', label: 'Accueil', icon: Gauge, view: EquipmentHome },
    { key: 'signalements', label: 'Signalements', icon: Inbox, count: w => w.dashboard.open_complaints, view: Reports },
    { key: 'detections', label: 'Détections', icon: ScanSearch, count: w => w.dashboard.unvalidated_events, view: Detections },
    { key: 'priorites', label: 'Priorités d’entretien', icon: Wrench, view: Priorities },
    { key: 'inspections', label: 'Inspections', icon: Truck, view: Inspections },
    { key: 'assistant', label: 'Assistant', icon: BookOpen, view: AssistantView },
    { key: 'comptes', label: 'Comptes', icon: Users, view: Accounts },
  ],
  transport: [
    { key: 'accueil', label: 'Accueil', icon: Gauge, view: TransportHome },
    { key: 'reseau', label: 'Réseau à risque', icon: Map, view: Network },
    { key: 'lignes', label: 'Lignes & flotte', icon: Route, view: Fleet },
    { key: 'affectations', label: 'Affectations', icon: ClipboardList, view: Assignments },
    { key: 'assistant', label: 'Assistant', icon: BookOpen, view: AssistantView },
    { key: 'comptes', label: 'Comptes', icon: Users, view: Accounts },
  ],
};
export const sectionLink = (ministry, key, extra = {}) => `/ministry/${ministry}?${new URLSearchParams({ vue: key, ...extra })}`;

export default function Ministry({ ministry }) {
  const w = useWorkspace(ministry);
  const [params] = useSearchParams();
  const toast = useToast();
  const [sheetSegment, setSheetSegment] = useState(null);   // segment whose intervention sheet is open
  const me = sessionUsername(getSession());
  const sections = SECTIONS[ministry];
  const current = sections.find(s => s.key === params.get('vue')) || sections[0];
  const View = current.view;

  useEffect(() => { if (w.notice) { toast.push(w.notice); w.setNotice(''); } }, [w.notice]); // eslint-disable-line react-hooks/exhaustive-deps

  const nav = sections.map(s => ({ key: s.key, label: s.label, icon: s.icon, to: sectionLink(ministry, s.key), count: s.count?.(w) }));
  return <SupervisorLayout ministry={ministry} nav={nav} current={current.key} title={current.label}>
    <div className="row-between">
      <h1>{current.label}</h1>
      <Button icon={RefreshCw} loading={w.loading} onClick={w.reload}>{w.loading ? 'Actualisation…' : 'Actualiser'}</Button>
    </div>
    {w.error && <Notice tone="error" title={w.error}/>}
    <View w={w} me={me} onSheet={setSheetSegment} params={params}/>
    {sheetSegment && <InterventionSheet segment={sheetSegment} onClose={() => setSheetSegment(null)}/>}
  </SupervisorLayout>;
}
