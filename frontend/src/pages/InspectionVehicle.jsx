import React, { useEffect, useRef, useState } from 'react';
import { CircleStop, FileUp, LocateFixed, LogOut, Play, Upload } from 'lucide-react';
import { PointsMap } from '../components/LeafletMap';
import { api } from '../lib/api';
import { clearSession } from '../lib/auth';
import { dateTime, duration, number, pct, plural, videoTime } from '../lib/format';
import { apiErrorMessage, defectTitle, gpsSourceLabel, jobStateLabel } from '../lib/labels';
import { Badge, Button, Card, ConfirmModal, DefinitionList, EmptyState, Field, Notice } from '../ui';

// Inspection vehicle (mobile first). Existing endpoints only: session start / heartbeat / stop, video upload,
// perception job create / status, observations of the session. The vehicle role cannot list sessions or jobs,
// so the current session and its jobs are remembered on this device.
const STORE = 'thniyetna.inspection';
const HEARTBEAT_MS = 5000;
const load = () => { try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch { return {}; } };
const save = value => { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch { /* storage unavailable */ } };
const JOB_TONE = { queued: 'neutral', running: 'primary', completed: 'green', failed: 'red' };

function JobStatus({ job }) {
  const r = job.result || {};
  const done = job.status === 'completed';
  return <div className="stack-sm">
    <div className="row"><Badge tone={JOB_TONE[job.status] || 'neutral'}>{jobStateLabel(job.status)}</Badge>
      {job.status === 'running' && <span className="t-sm t-muted t-num">{pct(job.progress)}</span>}
      <span className="t-xs t-muted">{dateTime(job.created_at)}</span></div>
    {job.status === 'running' && <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((job.progress || 0) * 100)}><span style={{ inlineSize: `${Math.round((job.progress || 0) * 100)}%` }}/></div>}
    {job.status === 'failed' && <Notice tone="error" title="L’analyse a échoué.">{job.error}</Notice>}
    {done && <DefinitionList items={[
      ['Durée de la vidéo', videoTime(r.video_duration_s)],
      ['Images analysées', `${number(r.frames_processed)} (${number(r.sample_fps, 1)} image/s)`],
      ['Temps de traitement', `${number(r.processing_time_s, 1)} s`],
      ['Détections avant suivi', number(r.detections_before_tracking)],
      ['Défauts après suivi', number(r.defects_after_tracking)],
      ['Source GPS', gpsSourceLabel(r.gps_source)],
      ['Défauts localisés', `${number(r.located_defects)} sur ${number(r.defects_after_tracking)}`],
      ['Événements routiers', number(r.events)],
    ]}/>}
    {done && r.gps_source === 'none' && <Notice tone="warning" title="Vidéo non localisée">Aucune position GPS : les défauts sont enregistrés comme observations, sans événement routier.</Notice>}
  </div>;
}

export default function InspectionVehicle() {
  const [state, setState] = useState(load);            // { vehicleCode, session: {id, started_at}, jobs: [id] }
  const [vehicleCode, setVehicleCode] = useState(state.vehicleCode || '');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [video, setVideo] = useState(null);
  const [gpx, setGpx] = useState(null);
  const [offset, setOffset] = useState('0');
  const [upload, setUpload] = useState(null);           // 0..1 while uploading
  const [jobs, setJobs] = useState({});
  const [observations, setObservations] = useState([]);
  const [tracking, setTracking] = useState(false);
  const [sent, setSent] = useState(0);
  const [confirmStop, setConfirmStop] = useState(false);
  const watch = useRef(null);
  const lastBeat = useRef(0);
  const session = state.session;
  const update = patch => setState(s => { const next = { ...s, ...patch }; save(next); return next; });

  // job status and detections: poll every 3 s while a job is queued or running
  useEffect(() => {
    const ids = state.jobs || [];
    let alive = true, timer;
    const tick = async () => {
      const rows = (await Promise.all(ids.map(id => api.perceptionJob(id).catch(() => null)))).filter(Boolean);
      if (!alive) return;
      setJobs(Object.fromEntries(rows.map(j => [j.id, j])));
      if (state.lastSession) {
        const found = await api.sessionObservations(state.lastSession).catch(() => null);
        if (alive && found) setObservations(found);
      }
      if (alive && rows.some(j => ['queued', 'running'].includes(j.status))) timer = setTimeout(tick, 3000);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [(state.jobs || []).join(','), state.lastSession]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (watch.current != null) navigator.geolocation?.clearWatch(watch.current); }, []);

  async function start(event) {
    event.preventDefault();
    setBusy('start'); setError('');
    try {
      const s = await api.startInspection({ vehicle_code: vehicleCode.trim(), mode: 'video' });
      update({ vehicleCode: vehicleCode.trim(), session: { id: s.id, started_at: s.started_at }, lastSession: s.id, jobs: [] });
      setJobs({}); setObservations([]); setSent(0);
    } catch (err) { setError(apiErrorMessage(err.message)); } finally { setBusy(''); }
  }

  function toggleGps() {
    if (tracking) { navigator.geolocation?.clearWatch(watch.current); watch.current = null; setTracking(false); return; }
    if (!navigator.geolocation) { setError('Géolocalisation indisponible sur cet appareil.'); return; }
    watch.current = navigator.geolocation.watchPosition(p => {
      if (Date.now() - lastBeat.current < HEARTBEAT_MS) return;
      lastBeat.current = Date.now();
      api.inspectionHeartbeat(session.id, {
        latitude: p.coords.latitude, longitude: p.coords.longitude, timestamp: new Date(p.timestamp).toISOString(),
        speed_kmh: p.coords.speed != null ? p.coords.speed * 3.6 : null, heading_deg: p.coords.heading ?? null, accuracy_m: p.coords.accuracy ?? null,
      }).then(() => setSent(n => n + 1)).catch(err => setError(apiErrorMessage(err.message)));
    }, () => { setError('Position GPS indisponible.'); setTracking(false); }, { enableHighAccuracy: true });
    setTracking(true);
  }

  async function stop() {
    setBusy('stop'); setError('');
    try {
      if (watch.current != null) { navigator.geolocation?.clearWatch(watch.current); watch.current = null; setTracking(false); }
      await api.stopInspection(session.id);
      update({ session: null });
    } catch (err) { setError(apiErrorMessage(err.message)); } finally { setBusy(''); setConfirmStop(false); }
  }

  async function send(event) {
    event.preventDefault();
    if (!video || !session) return;
    setBusy('upload'); setError(''); setUpload(0);
    try {
      const gpxText = gpx ? await gpx.text() : null;
      const media = await api.uploadVideo(video, setUpload);
      const options = { gps_offset_s: Number(offset) || 0 };
      if (gpxText) options.gpx = gpxText;
      const job = await api.createPerceptionJob({ job_type: 'video', storage_key: media.storage_key, media_uri: media.media_uri, session_id: session.id, options });
      update({ jobs: [job.id, ...(state.jobs || [])] });
      setVideo(null); setGpx(null);
      event.target.reset();
    } catch (err) { setError(apiErrorMessage(err.message)); } finally { setBusy(''); setUpload(null); }
  }

  const located = observations.filter(o => o.latitude != null && o.longitude != null);
  const jobList = (state.jobs || []).map(id => jobs[id]).filter(Boolean);
  return <div className="m-shell no-nav">
    <a className="skip-link" href="#contenu">Aller au contenu</a>
    <header className="m-header"><span className="wordmark">THNIYETNA</span><span className="t-sm t-muted">Véhicule d’inspection</span>
      <button type="button" className="btn btn-ghost btn-icon" aria-label="Déconnexion" onClick={() => { clearSession(); window.location.assign('/'); }}><LogOut aria-hidden="true"/></button></header>
    <main id="contenu" className="m-content">
      <h1>Inspection vidéo</h1>
      {error && <Notice tone="error" title={error}/>}

      <Card title="Session d’inspection" headingLevel={2}>
        {!session ? <form className="stack" onSubmit={start}>
          <Field label="Code du véhicule" help="Code enregistré par le Ministère (ex. DEMO-INSP-01)."><input className="input" required value={vehicleCode} onChange={e => setVehicleCode(e.target.value)} autoCapitalize="characters" spellCheck={false}/></Field>
          <Button type="submit" variant="primary" size="lg" block icon={Play} loading={busy === 'start'}>Démarrer l’inspection</Button>
        </form> : <div className="stack">
          <DefinitionList items={[['Véhicule', <span className="t-mono">{state.vehicleCode}</span>], ['Démarrée le', dateTime(session.started_at)], ['Session', <span className="t-mono t-sm">{session.id}</span>]]}/>
          <div className="row-between"><span className="t-sm">{tracking ? `Position envoyée toutes les 5 s · ${plural(sent, 'point')}` : 'Position GPS non envoyée'}</span>
            <Button icon={LocateFixed} onClick={toggleGps} aria-pressed={tracking}>{tracking ? 'Arrêter le GPS' : 'Envoyer ma position'}</Button></div>
          <Button variant="danger" size="lg" block icon={CircleStop} onClick={() => setConfirmStop(true)}>Arrêter l’inspection</Button>
        </div>}
      </Card>

      <Card title="Vidéo à analyser" headingLevel={2}>
        {!session ? <p className="t-muted t-sm">Démarrez une session pour envoyer une vidéo : chaque vidéo est rattachée à une session.</p>
          : <form className="stack" onSubmit={send}>
            <Field label="Vidéo" help="Vidéo de la route (caméra embarquée)."><input className="input" type="file" accept="video/*" required onChange={e => setVideo(e.target.files?.[0] || null)}/></Field>
            <Field label="Trace GPS (GPX, facultatif)" help="Sans GPX, les positions envoyées pendant la session sont utilisées ; sans aucune position, la vidéo n’est pas localisée."><input className="input" type="file" accept=".gpx,application/gpx+xml" onChange={e => setGpx(e.target.files?.[0] || null)}/></Field>
            <Field label="Décalage vidéo / GPS (secondes)" help="Positif si la vidéo a commencé après le premier point GPS."><input className="input" type="number" step="0.1" inputMode="decimal" value={offset} onChange={e => setOffset(e.target.value)}/></Field>
            {upload != null && <div className="stack-sm"><span className="t-sm">Envoi de la vidéo : <span className="t-num">{pct(upload)}</span></span><div className="progress"><span style={{ inlineSize: `${Math.round(upload * 100)}%` }}/></div></div>}
            <Button type="submit" variant="primary" size="lg" block icon={Upload} loading={busy === 'upload'} disabled={!video}>Envoyer la vidéo</Button>
          </form>}
      </Card>

      {jobList.length > 0 && <Card title="Analyses" headingLevel={2} bodyClass={null}>
        <ul className="short-list">{jobList.map(job => <li key={job.id} className="card-body"><JobStatus job={job}/></li>)}</ul>
      </Card>}

      {state.lastSession && <Card title="Détections de la session" headingLevel={2} actions={<span className="t-sm t-muted">{plural(observations.length, 'défaut')} · {plural(located.length, 'localisé', 'localisés')}</span>}>
        {observations.length ? <div className="stack">
          {located.length > 0 && <PointsMap points={located.map(o => ({ id: o.id, lat: o.latitude, lon: o.longitude, label: `${defectTitle(o.defect_type)} · ${pct(o.confidence)}` }))}/>}
          <ul className="evidence-list">{observations.map(o => <li key={o.id}>
            {o.media_uri && <a href={o.media_uri} target="_blank" rel="noreferrer"><img src={o.media_uri} alt={`Image de preuve : ${defectTitle(o.defect_type)}`} loading="lazy"/></a>}
            <div><b>{defectTitle(o.defect_type)}</b><span className="t-sm t-muted">Confiance {pct(o.confidence)} · vidéo à {videoTime(o.frame_time_s)}</span>
              <span className="t-xs">{o.latitude != null ? 'Localisé' : 'Non localisé (aucun événement routier)'}</span></div>
          </li>)}</ul>
        </div> : <EmptyState title="Aucune détection pour l’instant.">Les défauts apparaissent ici à la fin de l’analyse de la vidéo.</EmptyState>}
      </Card>}
    </main>
    {confirmStop && <ConfirmModal title="Arrêter l’inspection ?" danger confirmLabel="Arrêter l’inspection" loading={busy === 'stop'} onCancel={() => setConfirmStop(false)} onConfirm={stop}>
      La session sera clôturée. Les analyses déjà envoyées continuent et restent visibles ici.
    </ConfirmModal>}
  </div>;
}
