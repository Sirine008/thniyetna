// Run next to check-ui.mjs: node record-sheet.mjs <repo> sheet.json   (one real LLM call, ~100 s)
// Records one real intervention sheet (LLM ~100 s) for replay in screenshots. Password from .env, never printed.
import fs from 'node:fs';
const root = process.argv[2], out = process.argv[3];
const env = fs.readFileSync(`${root}/.env`, 'utf8');
const pw = (env.match(/^BOOTSTRAP_PASSWORD=(.*)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');
const login = await (await fetch('http://localhost:8081/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'equipment.supervisor', password: pw }) })).json();
const H = { Authorization: `Bearer ${login.access_token}` };
const map = await (await fetch('http://localhost:8081/api/platform/map')).json();
const seg = map.segments.filter(s => /^P[12]$/.test(s.maintenance_priority || '')).sort((a, b) => b.risk_score - a.risk_score)[0];
console.log('segment', seg.segment_code, seg.maintenance_priority);
const t = Date.now();
const r = await fetch(`http://localhost:8081/api/assistant/intervention/${encodeURIComponent(seg.segment_code)}`, { method: 'POST', headers: H });
const body = await r.json();
fs.writeFileSync(out, JSON.stringify({ segment_code: seg.segment_code, status: r.status, body }, null, 1));
console.log('status', r.status, 'seconds', Math.round((Date.now() - t) / 1000), 'sections', body.sections?.length);
