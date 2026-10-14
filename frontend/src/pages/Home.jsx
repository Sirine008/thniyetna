import React from 'react';
import { Link } from 'react-router-dom';

const loginLink = (role, next) => `/login?role=${role}&next=${encodeURIComponent(next)}`;

export default function Home() {
  return <main className="landing">
    <div className="brandmark">ط</div>
    <h1>THNIYETNA</h1>
    <p>La route intelligente, sûre et connectée.</p>
    <div className="role-grid">
      <Link to={loginLink('citizen', '/citizen')} className="role-card">
        <div className="role-icon">◎</div><h2>Espace Citoyen</h2>
        <p>Signalez, suivez et explorez l’état des routes.</p><span>Se connecter →</span>
      </Link>
      <Link to={loginLink('bus_driver', '/driver')} className="role-card driver">
        <div className="role-icon">↗</div><h2>Conducteur SRTB</h2>
        <p>Navigation sûre, alertes et prochain meilleur itinéraire.</p><span>Se connecter →</span>
      </Link>
      <Link to={loginLink('equipment_supervisor', '/ministry/equipment')} className="role-card equipment">
        <div className="role-icon">⌖</div><h2>Ministère de l’Équipement</h2>
        <p>Validez les détections, traitez les signalements et suivez les inspections.</p><span>Se connecter →</span>
      </Link>
      <Link to={loginLink('transport_supervisor', '/ministry/transport')} className="role-card transport">
        <div className="role-icon">⇄</div><h2>Ministère du Transport</h2>
        <p>Gérez les lignes, la flotte, les affectations et le risque routier.</p><span>Se connecter →</span>
      </Link>
    </div>
    <div className="landing-foot"><i/> API + PostGIS + OSRM · Bizerte</div>
  </main>;
}
