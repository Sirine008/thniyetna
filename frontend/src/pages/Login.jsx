import React, { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { loginWithCredentials, registerCitizen } from '../lib/api';
import { clearSession } from '../lib/auth';
import { apiErrorMessage } from '../lib/labels';
import { Button, Field, Notice } from '../ui';

const ROLE_USERS = { bus_driver: 'driver.srtb', equipment_supervisor: 'equipment.supervisor', transport_supervisor: 'transport.supervisor', inspection_vehicle: 'inspection.vehicle' };

const ROLE_LABELS = {
  citizen: 'Espace citoyen',
  bus_driver: 'Conducteur SRTB',
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
  const space = useMemo(() => ROLE_LABELS[expectedRole] || '', [expectedRole]);
  const register = mode === 'register';

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const session = register
        ? await registerCitizen({ username, password, display_name: displayName })
        : await loginWithCredentials(username, password);
      if (expectedRole && session.role !== expectedRole) {
        clearSession();
        throw new Error(`Ce compte appartient au rôle « ${ROLE_LABELS[session.role] || session.role} ».`);
      }
      navigate(next, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err.message || 'Connexion impossible.'));
    } finally {
      setLoading(false);
    }
  }

  return <>
    <header className="public-header"><Link to="/" className="wordmark">THNIYETNA</Link></header>
    <main className="auth-main" id="contenu">
      <Link className="back-link" to="/"><ArrowLeft aria-hidden="true"/>Choisir un autre espace</Link>
      <h1 style={{ marginBlockStart: 16 }}>{register ? 'Créer un compte citoyen' : 'Connexion'}</h1>
      {space && !register && <p className="t-muted" style={{ marginBlockStart: 4 }}>{space}</p>}
      {register && <p className="t-muted" style={{ marginBlockStart: 4 }}>Le compte sert à envoyer des signalements et à suivre leur traitement.</p>}
      <form className="auth-form" onSubmit={submit} noValidate={false}>
        {error && <Notice tone="error" title={error}/>}
        {register && <Field label="Nom affiché" help="Visible par les agents qui traitent vos signalements."><input className="input" value={displayName} onChange={e => setDisplayName(e.target.value)} autoComplete="name" required minLength={2}/></Field>}
        <Field label="Identifiant" help={register ? 'Lettres, chiffres, point, tiret ou tiret bas ; 3 caractères minimum.' : undefined}>
          <input className="input" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required minLength={3} autoCapitalize="none" spellCheck={false}/>
        </Field>
        <Field label="Mot de passe" help={register ? '8 caractères minimum.' : undefined}>
          <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={register ? 'new-password' : 'current-password'} required minLength={8}/>
        </Field>
        <Button type="submit" variant="primary" loading={loading}>{loading ? (register ? 'Création du compte…' : 'Connexion…') : register ? 'Créer le compte' : 'Se connecter'}</Button>
        {canRegister && <div className="auth-switch">
          <span className="t-muted">{register ? 'Vous avez déjà un compte ?' : 'Pas encore de compte citoyen ?'}</span>{' '}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setMode(register ? 'login' : 'register'); setError(''); }}>
            {register ? 'Se connecter' : 'Créer un compte'}
          </button>
        </div>}
      </form>
    </main>
  </>;
}
