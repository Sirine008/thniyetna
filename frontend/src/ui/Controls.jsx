import React, { useId } from 'react';
import { ArrowRight, CircleAlert, CircleCheck, FlaskConical, Info, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { DEMO_LABEL } from '../lib/constants';

/** Button: primary | secondary | danger | ghost; `loading` shows a spinner and disables it. */
export function Button({ variant = 'secondary', size, block, icon: Icon, loading = false, children, className = '', type = 'button', ...rest }) {
  const cls = ['btn', `btn-${variant}`, size && `btn-${size}`, block && 'btn-block', !children && 'btn-icon', className].filter(Boolean).join(' ');
  return <button type={type} className={cls} disabled={loading || rest.disabled} aria-busy={loading || undefined} {...rest}>
    {loading ? <span className="spinner" aria-hidden="true"/> : Icon && <Icon aria-hidden="true"/>}
    {children}
  </button>;
}
export function ButtonLink({ to, variant = 'secondary', size, icon: Icon, children, className = '', ...rest }) {
  return <Link to={to} className={['btn', `btn-${variant}`, size && `btn-${size}`, className].filter(Boolean).join(' ')} {...rest}>{Icon && <Icon aria-hidden="true"/>}{children}</Link>;
}

export function Spinner({ large, label }) {
  return <span className="row t-muted" role={label ? 'status' : undefined}><span className={`spinner${large ? ' spinner-lg' : ''}`} aria-hidden="true"/>{label}</span>;
}
export function Loading({ label = 'Chargement…' }) {
  return <div className="loading-line" role="status"><span className="spinner" aria-hidden="true"/>{label}</div>;
}
export function SkeletonRows({ rows = 5, cols = 4 }) {
  return <div aria-hidden="true">{Array.from({ length: rows }, (_, i) => <div className="skeleton-row" key={i} style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
    {Array.from({ length: cols }, (__, j) => <span className="skeleton" key={j}/>)}
  </div>)}</div>;
}

/** Text + optional action; no illustration. */
export function EmptyState({ title, children, action }) {
  return <div className="empty-state"><p className="empty-state-title">{title}</p>{children && <p>{children}</p>}{action}</div>;
}

const NOTICE_ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert };
/** Inline message. `error` uses role=alert so screen readers announce it. */
export function Notice({ tone = 'info', title, children, action }) {
  const Icon = NOTICE_ICONS[tone];
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
    <Icon aria-hidden="true"/>
    <div className="notice-body">{title && <p className="notice-title">{title}</p>}{children && <div className="t-sm">{children}</div>}</div>
    {action}
  </div>;
}
export function DemoBanner({ show = true, children }) {
  return show ? <div className="demo-banner" role="note"><FlaskConical aria-hidden="true"/>{DEMO_LABEL}{children && <span className="t-sm" style={{ fontWeight: 400 }}>{children}</span>}</div> : null;
}

/** Labelled form field: label, help text and error are linked to the control (aria-describedby). */
export function Field({ label, help, error, children, className = '', required }) {
  const id = useId();
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const control = React.cloneElement(children, {
    id: children.props.id || id,
    'aria-describedby': [helpId, errorId].filter(Boolean).join(' ') || undefined,
    'aria-invalid': error ? true : undefined,
    required: required ?? children.props.required,
  });
  return <div className={`form-field ${className}`}>
    <label className="field-label" htmlFor={children.props.id || id}>{label}{(required ?? children.props.required) && <span className="t-subtle"> (obligatoire)</span>}</label>
    {control}
    {help && <span className="field-help" id={helpId}>{help}</span>}
    {error && <span className="field-error" id={errorId}><CircleAlert size={12} aria-hidden="true"/>{error}</span>}
  </div>;
}

/** KPI tile: a real API count; links to its filtered list when `to` is given. */
export function KpiTile({ label, value, to, linkLabel = 'Voir la liste' }) {
  const body = <><span className="kpi-label">{label}</span><span className="kpi-value">{value ?? '—'}</span>{to && <span className="kpi-link">{linkLabel}<ArrowRight aria-hidden="true"/></span>}</>;
  return to ? <Link className="kpi" to={to}>{body}</Link> : <div className="kpi">{body}</div>;
}

export function Card({ title, actions, children, footer, className = '', as: Tag = 'section', bodyClass = 'card-body', headingLevel = 2 }) {
  const H = `h${headingLevel}`;
  return <Tag className={`card ${className}`}>
    {(title || actions) && <div className="card-head">{title && <H>{title}</H>}{actions && <div className="row">{actions}</div>}</div>}
    {bodyClass === null ? children : <div className={bodyClass}>{children}</div>}
    {footer && <div className="card-foot">{footer}</div>}
  </Tag>;
}

export function PageHeader({ title, description, actions, kicker }) {
  return <div className="page-head"><div>{kicker && <p className="breadcrumb">{kicker}</p>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="row">{actions}</div>}</div>;
}

/** Tabs (ARIA tablist; arrow keys move between tabs). */
export function Tabs({ tabs, value, onChange, label }) {
  const onKey = event => {
    const i = tabs.findIndex(t => t.key === value);
    const next = event.key === 'ArrowRight' ? i + 1 : event.key === 'ArrowLeft' ? i - 1 : null;
    if (next == null) return;
    event.preventDefault();
    const t = tabs[(next + tabs.length) % tabs.length];
    onChange(t.key);
    document.getElementById(`tab-${t.key}`)?.focus();
  };
  return <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>{tabs.map(t => <button key={t.key} id={`tab-${t.key}`} role="tab" type="button"
    className="tab" aria-selected={t.key === value} tabIndex={t.key === value ? 0 : -1} onClick={() => onChange(t.key)}>
    {t.label}{t.count != null && <span className="count">{t.count}</span>}
  </button>)}</div>;
}

/** Vertical timeline. items: {title, meta, note, state: 'done' | 'current' | 'pending'} */
export function Timeline({ items, label }) {
  return <ol className="timeline" aria-label={label}>{items.map((item, i) => <li key={i} className={`timeline-item is-${item.state || 'done'}`}>
    <span className="timeline-dot" aria-hidden="true"/>
    <div className="timeline-title">{item.title}{item.state === 'current' && <span className="sr-only"> (étape actuelle)</span>}{item.state === 'pending' && <span className="sr-only"> (à venir)</span>}</div>
    {item.meta && <div className="timeline-meta">{item.meta}</div>}
    {item.note && <div className="timeline-note">{item.note}</div>}
  </li>)}</ol>;
}

export function DefinitionList({ items }) {
  return <dl className="dl">{items.filter(Boolean).map(([term, value]) => <React.Fragment key={term}><dt>{term}</dt><dd>{value ?? '—'}</dd></React.Fragment>)}</dl>;
}
