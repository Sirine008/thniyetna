import React from 'react';
import { NavLink } from 'react-router-dom';
import { Bell, House, ListChecks, Map, Navigation, Plus } from 'lucide-react';

// Same destinations as before the redesign; icons + labels, 44 px targets.
const ITEMS = {
  driver: [['', Navigation, 'Trajet'], ['/map', Map, 'Carte'], ['/alerts', Bell, 'Alertes']],
  citizen: [['', House, 'Accueil'], ['/map', Map, 'Carte'], ['/report', Plus, 'Signaler'], ['/claims', ListChecks, 'Suivi']],
};

export default function BottomNav({ kind }) {
  const base = kind === 'driver' ? '/driver' : '/citizen';
  return <nav className="bottom-nav" aria-label="Navigation principale">{ITEMS[kind === 'driver' ? 'driver' : 'citizen'].map(([path, Icon, label]) =>
    <NavLink key={label} end={path === ''} to={base + path}><Icon aria-hidden="true"/><span>{label}</span></NavLink>)}</nav>;
}
