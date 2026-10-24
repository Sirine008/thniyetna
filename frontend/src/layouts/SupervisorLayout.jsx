import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LogOut, Menu, X } from 'lucide-react';
import { clearSession, getSession } from '../lib/auth';
import { MINISTRIES, roleLabel } from '../lib/labels';
import { number } from '../lib/format';

/**
 * Supervisor shell: left sidebar (sections of the ministry) + top bar (user, role, logout).
 * Under 960 px the sidebar becomes a drawer opened from the top bar.
 * nav: [{ key, label, icon, to, count }]
 */
export default function SupervisorLayout({ ministry, nav, current, title, children }) {
  const session = getSession();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => { setOpen(false); }, [location.search]);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = e => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  function signOut() { clearSession(); window.location.assign('/'); }

  return <div className={`sup-shell${open ? ' is-open' : ''}`}>
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <aside className="sup-sidebar" id="sup-nav" aria-label="Sections">
      <div className="sup-brand"><Link to="/" className="wordmark">THNIYETNA</Link><span className="t-sm t-muted">{MINISTRIES[ministry]}</span></div>
      <nav aria-label="Navigation principale"><ul className="sup-nav">{nav.map(item => { const Icon = item.icon; const active = item.key === current; return <li key={item.key}>
        <Link to={item.to} className="sup-nav-link" aria-current={active ? 'page' : undefined}>
          <Icon aria-hidden="true"/><span>{item.label}</span>
          {item.count != null && Number(item.count) > 0 && <span className="sup-nav-count" aria-label={`${item.count} à traiter`}>{number(item.count)}</span>}
        </Link></li>; })}</ul></nav>
      <div className="sup-sidebar-foot"><Link to="/design" className="t-sm">Système de conception</Link></div>
    </aside>
    {open && <div className="sup-scrim" onClick={() => setOpen(false)} aria-hidden="true"/>}
    <div className="sup-main">
      <header className="sup-topbar">
        <button type="button" className="btn btn-ghost btn-icon sup-menu" aria-expanded={open} aria-controls="sup-nav" aria-label={open ? 'Fermer le menu' : 'Ouvrir le menu'} onClick={() => setOpen(v => !v)}>{open ? <X aria-hidden="true"/> : <Menu aria-hidden="true"/>}</button>
        <span className="sup-title">{title}</span>
        <div className="sup-user">
          <span className="sup-user-name"><b>{session?.display_name || 'Compte'}</b><span className="t-xs t-muted">{roleLabel(session?.role)}</span></span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={signOut}><LogOut aria-hidden="true"/><span className="sup-logout-label">Déconnexion</span></button>
        </div>
      </header>
      <main className="sup-content" id="contenu" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
