import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, ClipboardList, FileText, Gauge, Inbox, Map, RefreshCw, Route, ScanSearch, Truck, Users, Wrench } from 'lucide-react';
import InterventionSheet from '../components/InterventionSheet';
import SupervisorLayout from '../layouts/SupervisorLayout';
import { getSession } from '../lib/auth';
import { Button, Notice, useToast } from '../ui';
import { sessionUsername, useWorkspace } from './ministry/useWorkspace';
import { LegacyAccounts, LegacyAssignments, LegacyAssistant, LegacyEvents, LegacyFleet, LegacyInspections, LegacyMetrics, LegacyNetwork, LegacyPriorities, LegacyReports } from './ministry/legacy';

// Sections of each ministry: URL `?vue=<key>` (so KPI tiles and links can open a filtered list).
const SECTIONS = {
  equipment: [
    { key: 'signalements', label: 'Signalements', icon: Inbox, count: w => w.dashboard.open_complaints, view: LegacyReports },
    { key: 'detections', label: 'Détections', icon: ScanSearch, count: w => w.dashboard.unvalidated_events, view: LegacyEvents },
    { key: 'priorites', label: 'Priorités d’entretien', icon: Wrench, view: LegacyPriorities },
    { key: 'inspections', label: 'Inspections', icon: Truck, view: LegacyInspections },
    { key: 'assistant', label: 'Assistant', icon: BookOpen, view: LegacyAssistant },
    { key: 'comptes', label: 'Comptes', icon: Users, view: LegacyAccounts },
  ],
  transport: [
    { key: 'reseau', label: 'Réseau à risque', icon: Map, view: LegacyNetwork },
    { key: 'affectations', label: 'Affectations', icon: ClipboardList, view: LegacyAssignments },
    { key: 'lignes', label: 'Lignes & flotte', icon: Route, view: LegacyFleet },
    { key: 'assistant', label: 'Assistant', icon: BookOpen, view: LegacyAssistant },
    { key: 'comptes', label: 'Comptes', icon: Users, view: LegacyAccounts },
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
    <LegacyMetrics w={w}/>
    <View w={w} me={me} onSheet={setSheetSegment} params={params}/>
    {sheetSegment && <InterventionSheet segment={sheetSegment} onClose={() => setSheetSegment(null)}/>}
  </SupervisorLayout>;
}
