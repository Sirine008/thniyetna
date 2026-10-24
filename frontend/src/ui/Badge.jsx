import React from 'react';
import {
  Archive, Bell, CalendarClock, CheckCheck, ChevronDown, ChevronUp, ChevronsUp, CircleCheck, CircleX, Clock, Eye,
  Inbox, RefreshCw, Route, Search, SignalHigh, SignalLow, SignalMedium, TriangleAlert, FlaskConical,
} from 'lucide-react';
import { DEMO_LABEL } from '../lib/constants';
import { alertTopicLabel, eventStateLabel, priorityLabel, reportStateLabel, riskLabel } from '../lib/labels';

// Colour is never alone: every badge has a text label and an icon whose shape differs per value.
export function Badge({ tone = 'neutral', icon: Icon, children, title, className = '' }) {
  return <span className={`badge badge-${tone} ${className}`} title={title}>{Icon && <Icon aria-hidden="true"/>}{children}</span>;
}

const RISK = { low: ['green', SignalLow], medium: ['yellow', SignalMedium], high: ['orange', SignalHigh], critical: ['red', TriangleAlert] };
export function RiskBadge({ level }) {
  if (!level) return <span className="t-subtle">—</span>;
  const [tone, icon] = RISK[level] || ['neutral', null];
  return <Badge tone={tone} icon={icon}>{riskLabel(level)}</Badge>;
}

const PRIORITY = { P1: ['red', ChevronsUp], P2: ['orange', ChevronUp], P3: ['yellow', ChevronDown], P4: ['neutral', Eye] };
export function PriorityBadge({ priority }) {
  if (!priority) return <span className="t-subtle">—</span>;
  const [tone, icon] = PRIORITY[priority] || ['neutral', null];
  return <Badge tone={tone} icon={icon}>{priorityLabel(priority)}</Badge>;
}

const REPORT = {
  open: ['orange', Inbox], under_review: ['yellow', Search], validated: ['primary', CircleCheck],
  planned: ['primary', CalendarClock], resolved: ['green', CheckCheck], rejected: ['neutral', CircleX],
};
export function ReportStateBadge({ status }) {
  const [tone, icon] = REPORT[status] || ['neutral', null];
  return <Badge tone={tone} icon={icon}>{reportStateLabel(status)}</Badge>;
}

export function EventStateBadge({ validated, status }) {
  const key = status || (validated ? 'validated' : 'observed');
  return key === 'observed'
    ? <Badge tone="orange" icon={Clock}>{eventStateLabel(key)}</Badge>
    : <Badge tone="green" icon={CircleCheck}>{eventStateLabel(key)}</Badge>;
}

/** Alert type of a notification: reroute / warning / superseded / other topics. */
export function AlertBadge({ topic, superseded }) {
  if (superseded) return <Badge tone="neutral" icon={Archive}>Remplacée</Badge>;
  if (topic === 'driver.reroute.alert') return <Badge tone="orange" icon={Route}>Déviation</Badge>;
  if (topic === 'driver.route.warning') return <Badge tone="red" icon={TriangleAlert}>Danger</Badge>;
  return <Badge tone="neutral" icon={Bell}>Information</Badge>;
}
export function ConfirmedBadge({ count }) {
  return count > 1 ? <Badge tone="neutral" icon={RefreshCw}>Confirmée {count}×</Badge> : null;
}

export function DemoBadge({ show = true }) {
  return show ? <Badge tone="demo" icon={FlaskConical}>{DEMO_LABEL}</Badge> : null;
}
