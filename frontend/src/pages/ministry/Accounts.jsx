import React, { useState } from 'react';
import { KeyRound, UserCheck, UserPlus, UserX } from 'lucide-react';
import { dateTime, plural } from '../../lib/format';
import { roleLabel } from '../../lib/labels';
import { Badge, Button, Card, ConfirmModal, DataTable, EmptyState, Field, Modal, SkeletonRows } from '../../ui';
import { STAFF_ROLES, SUPERVISOR_ROLES } from './useWorkspace';

// Accounts of the ministry. Same requests as before: POST /auth/staff, PATCH /auth/staff/{u}/active,
// POST /auth/staff/{u}/password (the API enforces the role permissions; this only shapes the forms).
const emptyDraft = role => ({ username: '', display_name: '', role, password: '' });

function CreateAccount({ w, onDone }) {
  const [draft, setDraft] = useState(emptyDraft(STAFF_ROLES[w.ministry][0]));
  const submit = async event => { event.preventDefault(); if (await w.createStaff(draft)) { setDraft(emptyDraft(draft.role)); onDone(); } };
  return <Modal title="Créer un compte" onClose={onDone} footer={<><Button onClick={onDone}>Annuler</Button><Button type="submit" form="staff-form" variant="primary" loading={w.saving === 'staff'}>Créer le compte</Button></>}>
    <form id="staff-form" className="stack" onSubmit={submit}>
      <Field label="Identifiant" help="3 à 80 caractères : lettres, chiffres, point, tiret, tiret bas."><input className="input" required minLength={3} maxLength={80} pattern={'[A-Za-z0-9._\\-]+'} title="Lettres, chiffres, . _ -" autoCapitalize="none" spellCheck={false} value={draft.username} onChange={e => setDraft({ ...draft, username: e.target.value })} data-autofocus/></Field>
      <Field label="Nom affiché"><input className="input" required minLength={2} maxLength={120} value={draft.display_name} onChange={e => setDraft({ ...draft, display_name: e.target.value })}/></Field>
      <Field label="Rôle"><select className="select" value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value })}>{STAFF_ROLES[w.ministry].map(role => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></Field>
      <Field label="Mot de passe initial" help="8 caractères minimum ; à transmettre à la personne par un canal sûr."><input className="input" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={draft.password} onChange={e => setDraft({ ...draft, password: e.target.value })}/></Field>
    </form>
  </Modal>;
}

function ResetPassword({ account, w, onDone }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const submit = async event => {
    event.preventDefault();
    if (password.length < 8) { setError('Le mot de passe doit contenir au moins 8 caractères.'); return; }
    if (await w.resetStaffPassword(account, password)) onDone();
  };
  return <Modal title={`Réinitialiser le mot de passe de ${account.username}`} onClose={onDone} footer={<><Button onClick={onDone}>Annuler</Button><Button type="submit" form="reset-form" variant="primary" icon={KeyRound} loading={w.saving === account.username}>Réinitialiser</Button></>}>
    <form id="reset-form" className="stack" onSubmit={submit} noValidate>
      <p>L’ancien mot de passe ne fonctionnera plus. Transmettez le nouveau à {account.display_name} par un canal sûr.</p>
      <Field label="Nouveau mot de passe" help="8 caractères minimum." error={error}><input className="input" type="password" minLength={8} maxLength={128} autoComplete="new-password" value={password} onChange={e => { setPassword(e.target.value); setError(''); }} data-autofocus/></Field>
    </form>
  </Modal>;
}

export default function Accounts({ w, me }) {
  const [creating, setCreating] = useState(false);
  const [confirm, setConfirm] = useState(null);   // account to deactivate / reactivate
  const [reset, setReset] = useState(null);
  const active = w.staff.filter(a => a.active).length;
  const columns = [
    { key: 'username', label: 'Identifiant', render: a => <><span className="t-mono">{a.username}</span>{a.username === me && <span className="cell-sub">Votre compte</span>}</> },
    { key: 'display_name', label: 'Nom' },
    { key: 'role', label: 'Rôle', render: a => roleLabel(a.role), sort: a => roleLabel(a.role) },
    { key: 'active', label: 'État', render: a => (a.active ? <Badge tone="green" icon={UserCheck}>Actif</Badge> : <Badge icon={UserX}>Inactif</Badge>), sort: a => Number(a.active) },
    { key: 'created_at', label: 'Créé le', render: a => <span className="t-num">{dateTime(a.created_at)}</span>, sort: a => a.created_at },
    { key: 'actions', label: '', sort: false, render: a => (a.username === me ? <span className="t-subtle t-sm">—</span> : <div className="cell-actions">
      <Button size="sm" variant={a.active ? 'danger' : 'secondary'} disabled={w.saving === a.username} onClick={() => setConfirm(a)}>{a.active ? 'Désactiver' : 'Réactiver'}</Button>
      {!SUPERVISOR_ROLES.includes(a.role) && <Button size="sm" icon={KeyRound} disabled={w.saving === a.username} onClick={() => setReset(a)}>Mot de passe</Button>}
    </div>) },
  ];
  if (!w.loaded && w.loading) return <SkeletonRows rows={5} cols={5}/>;
  return <>
    <p className="t-muted">{plural(w.staff.length, 'compte')} · {plural(active, 'actif', 'actifs')}. Les comptes désactivés ne peuvent plus se connecter.</p>
    <Card title="Comptes du ministère" actions={<Button variant="primary" icon={UserPlus} onClick={() => setCreating(true)}>Créer un compte</Button>} bodyClass={null}>
      <DataTable caption="Comptes du ministère" rowKey={a => a.username} rows={w.staff} columns={columns} initialSort={{ key: 'username', dir: 'asc' }}
        empty={<EmptyState title="Aucun compte." action={<Button icon={UserPlus} onClick={() => setCreating(true)}>Créer un compte</Button>}/>}/>
    </Card>
    {creating && <CreateAccount w={w} onDone={() => setCreating(false)}/>}
    {reset && <ResetPassword account={reset} w={w} onDone={() => setReset(null)}/>}
    {confirm && <ConfirmModal title={confirm.active ? `Désactiver le compte ${confirm.username} ?` : `Réactiver le compte ${confirm.username} ?`}
      danger={confirm.active} confirmLabel={confirm.active ? 'Désactiver le compte' : 'Réactiver le compte'} loading={w.saving === confirm.username}
      onCancel={() => setConfirm(null)} onConfirm={async () => { await w.toggleStaffActive(confirm); setConfirm(null); }}>
      {confirm.active ? `${confirm.display_name} (${roleLabel(confirm.role)}) ne pourra plus se connecter. Le compte peut être réactivé plus tard.` : `${confirm.display_name} pourra de nouveau se connecter.`}
    </ConfirmModal>}
  </>;
}
