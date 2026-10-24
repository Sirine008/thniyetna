// Run next to check-ui.mjs: node record-ask.mjs <repo> ask.json   (one real LLM call, ~60 s; logged in rag_queries like any question)
// Records one real /assistant/ask answer (LLM) for replay in the UI checks. Password from .env, never printed.
import fs from 'node:fs';
const [root, out] = process.argv.slice(2);
const env = fs.readFileSync(`${root}/.env`, 'utf8');
const pw = (env.match(/^BOOTSTRAP_PASSWORD=(.*)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');
const login = await (await fetch('http://localhost:8081/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'equipment.supervisor', password: pw }) })).json();
const question = 'Comment réparer un nid-de-poule avec un enrobé à chaud ?';
const t = Date.now();
const r = await fetch('http://localhost:8081/api/assistant/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${login.access_token}` }, body: JSON.stringify({ question }) });
const body = await r.json();
fs.writeFileSync(out, JSON.stringify({ question, status: r.status, body }, null, 1));
console.log('status', r.status, 'seconds', Math.round((Date.now() - t) / 1000), 'sources', body.sources?.length, 'cited', /\[\d/.test(body.answer || ''));
