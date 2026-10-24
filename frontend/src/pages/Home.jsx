import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Bus, Landmark, MapPin, Route } from 'lucide-react';

const loginLink = (role, next) => `/login?role=${role}&next=${encodeURIComponent(next)}`;

// Entry page: one row per space, same four login links as before.
const SPACES = [
  { role: 'citizen', next: '/citizen', icon: MapPin, title: 'Espace citoyen', text: 'Signaler un défaut de chaussée, suivre ses signalements, vérifier un itinéraire.' },
  { role: 'bus_driver', next: '/driver', icon: Bus, title: 'Conducteur SRTB', text: 'Ligne affectée, alertes de danger et itinéraire de remplacement.' },
  { role: 'equipment_supervisor', next: '/ministry/equipment', icon: Landmark, title: 'Ministère de l’Équipement', text: 'Traiter les signalements, valider les détections, planifier l’entretien.' },
  { role: 'transport_supervisor', next: '/ministry/transport', icon: Route, title: 'Ministère du Transport', text: 'Lignes, flotte, affectations et réseau à risque.' },
];

export default function Home() {
  return <>
    <header className="public-header"><span className="wordmark">THNIYETNA</span></header>
    <main className="public-main" id="contenu">
      <h1>Choisissez votre espace</h1>
      <p className="t-muted" style={{ marginBlockStart: 4 }}>Gouvernorat de Bizerte · état des routes, signalements et itinéraires.</p>
      <ul className="role-list">{SPACES.map(({ role, next, icon: Icon, title, text }) => <li key={role}>
        <Link className="role-link" to={loginLink(role, next)}>
          <Icon aria-hidden="true"/>
          <div><h2>{title}</h2><p>{text}</p></div>
          <span className="role-go">Se connecter<ArrowRight aria-hidden="true"/></span>
        </Link>
      </li>)}</ul>
    </main>
  </>;
}
