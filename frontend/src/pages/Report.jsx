import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Camera, ImagePlus, LocateFixed, Send } from 'lucide-react';
import BottomNav from '../components/BottomNav';
import { PointMap } from '../components/LeafletMap';
import { api } from '../lib/api';
import { BIZERTE } from '../lib/constants';
import { coords } from '../lib/format';
import { REPORT_CATEGORIES, apiErrorMessage } from '../lib/labels';
import { Button, Field, Notice } from '../ui';

// Same flow as before: GPS on load (Bizerte by default), optional photo upload, then POST /platform/complaints.
const CATEGORIES = [['road_damage', 'Nid-de-poule'], ['flooding', 'Inondation'], ['obstacle', 'Obstacle']];

export default function Report() {
  const nav = useNavigate();
  const [desc, setDesc] = useState('Nid-de-poule important sur la chaussée');
  const [cat, setCat] = useState('road_damage');
  const [pos, setPos] = useState(BIZERTE);
  const [located, setLocated] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState('');
  const [state, setState] = useState('idle');
  const [error, setError] = useState('');
  const locate = () => navigator.geolocation?.getCurrentPosition(
    p => { setPos([p.coords.latitude, p.coords.longitude]); setLocated(true); },
    () => setError('GPS indisponible : position par défaut de Bizerte utilisée.'),
  );
  useEffect(locate, []);
  useEffect(() => {
    if (!photo) { setPreview(''); return undefined; }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const submit = async event => {
    event.preventDefault();
    if (!desc.trim() || state === 'sending') return;
    setState('sending'); setError('');
    try {
      let image_url = null, image_storage_key = null;
      if (photo) { const media = await api.uploadImage(photo); image_url = media.media_uri; image_storage_key = media.storage_key; }
      await api.submitClaim({ description: desc, latitude: pos[0], longitude: pos[1], category: cat, image_url, image_storage_key });
      setState('done');
      setTimeout(() => nav('/citizen'), 1100);
    } catch (e) {
      setState('error');
      setError(`Échec de transmission : ${apiErrorMessage(e.message)}`);
    }
  };

  return <div className="m-shell">
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <header className="m-header"><div className="row"><button type="button" className="btn btn-ghost btn-icon" aria-label="Retour" onClick={() => nav(-1)}><ArrowLeft aria-hidden="true"/></button><span className="t-strong">Nouveau signalement</span></div><span className="wordmark">THNIYETNA</span></header>
    <main id="contenu" className="m-content">
      <div><h1>Signaler un défaut de la chaussée</h1><p className="t-muted t-sm">Le signalement est transmis au Ministère de l’Équipement ; une photo permet l’analyse automatique du défaut.</p></div>
      <form className="stack" onSubmit={submit}>
        <fieldset className="fieldset"><legend>Photo (facultative)</legend>
          <label className="photo-input">
            <input type="file" accept="image/*" capture="environment" onChange={e => setPhoto(e.target.files?.[0] || null)}/>
            {preview ? <img src={preview} alt="Aperçu de la photo jointe"/> : <ImagePlus aria-hidden="true"/>}
            <span><b>{photo ? 'Photo jointe' : 'Ajouter une photo'}</b><span className="t-sm t-muted">{photo ? photo.name : 'Appareil photo ou galerie'}</span></span>
            <span className="btn btn-secondary btn-sm" aria-hidden="true"><Camera/>{photo ? 'Changer' : 'Choisir'}</span>
          </label>
        </fieldset>
        <fieldset className="fieldset"><legend>Type de problème</legend>
          <div className="choice-group">{CATEGORIES.map(([value, label]) => <label key={value} className="choice">
            <input type="radio" name="category" value={value} checked={cat === value} onChange={() => setCat(value)}/>{label}
            <span className="sr-only"> ({REPORT_CATEGORIES[value]})</span></label>)}</div>
        </fieldset>
        <Field label="Description" help="Ce que vous voyez, et où exactement sur la chaussée."><textarea className="textarea" rows={4} value={desc} onChange={e => setDesc(e.target.value)} required/></Field>
        <fieldset className="fieldset"><legend>Position du signalement</legend>
          <div className="stack-sm">
            <PointMap lat={pos[0]} lon={pos[1]} height={160} label={`Position du signalement : ${coords(pos[0], pos[1])}`}/>
            <div className="row-between"><span className="t-sm"><span className="t-num">{coords(pos[0], pos[1])}</span><span className="t-muted"> · {located ? 'position GPS' : 'position par défaut (Bizerte)'}</span></span>
              <Button size="sm" icon={LocateFixed} onClick={locate}>Actualiser la position</Button></div>
          </div>
        </fieldset>
        {error && <Notice tone={state === 'error' ? 'error' : 'warning'} title={error}/>}
        {state === 'done' && <Notice tone="success" title="Signalement envoyé.">Retour à l’accueil…</Notice>}
        <Button type="submit" variant="primary" size="lg" block icon={Send} loading={state === 'sending'} disabled={state === 'done'}>{state === 'sending' ? 'Transmission…' : state === 'done' ? 'Signalement envoyé' : state === 'error' ? 'Réessayer l’envoi' : 'Envoyer le signalement'}</Button>
        <Link to="/citizen/claims" className="t-sm">Voir mes signalements</Link>
      </form>
    </main>
    <BottomNav kind="citizen"/>
  </div>;
}
