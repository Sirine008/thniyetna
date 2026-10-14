import React, { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { loginWithCredentials, registerCitizen } from '../lib/api';
import { clearSession } from '../lib/auth';

const ROLE_USERS = { bus_driver: 'driver.srtb', equipment_supervisor: 'equipment.supervisor', transport_supervisor: 'transport.supervisor', inspection_vehicle: 'inspection.vehicle' };

const ROLE_LABELS = {
  citizen: 'Citoyen',
  bus_driver: 'Conducteur',
  equipment_supervisor: 'Ministère de l’Équipement',
  transport_supervisor: 'Ministère du Transport',
  inspection_vehicle: 'Véhicule d’inspection',
};

export default function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const expectedRole = params.get('role') || '';
  const next = params.get('next') || '/';
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState(ROLE_USERS[expectedRole] || '');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const canRegister = !expectedRole || expectedRole === 'citizen';
  const title = useMemo(() => ROLE_LABELS[expectedRole] || 'THNIYETNA', [expectedRole]);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const session = mode === 'register'
        ? await registerCitizen({ username, password, display_name: displayName })
        : await loginWithCredentials(username, password);
      if (expectedRole && session.role !== expectedRole) {
        clearSession();
        throw new Error(`Ce compte appartient au rôle « ${ROLE_LABELS[session.role] || session.role} ».`);
      }
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.message || 'Connexion impossible.');
    } finally {
      setLoading(false);
    }
  }

  return <main className="auth-page">
    <Link className="auth-back" to="/">← Retour</Link>
    <form className="auth-card" onSubmit={submit}>
      <div className="brandmark">ط</div>
      <span className="eyebrow">THNIYETNA · AUTHENTIFICATION</span>
      <h1>{mode === 'register' ? 'Créer un compte citoyen' : title}</h1>
      <p>{mode === 'register' ? 'Créez votre compte pour signaler et suivre les défauts routiers.' : 'Connectez-vous pour accéder à votre espace.'}</p>
      {mode === 'register' && <label>Nom affiché<input value={displayName} onChange={e => setDisplayName(e.target.value)} autoComplete="name" required minLength={2}/></label>}
      <label>Identifiant<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required minLength={3}/></label>
      <label>Mot de passe<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required minLength={8}/></label>
      {error && <div className="form-error">{error}</div>}
      <button className="submit-btn" disabled={loading}>{loading ? 'Chargement…' : mode === 'register' ? 'Créer le compte' : 'Se connecter'}</button>
      {canRegister && <button type="button" className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
        {mode === 'login' ? 'Nouveau citoyen ? Créer un compte' : 'J’ai déjà un compte'}
      </button>}
    </form>
  </main>;
}
