/** Apply sourced route reviews without changing outreach history or drafts. */
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export const EXTRA = ['alternative_contact_routes', 'contact_search_status'];
export function parseCsv(text) {
  const rows = []; let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && c === ',') { row.push(cell); cell = ''; }
    else if (!quoted && c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r' || quoted) cell += c;
  }
  if (quoted) throw new Error('Unclosed CSV quote');
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
export const encodeCsv = rows => rows.map(r => r.map(v => '"' + String(v).replaceAll('"', '""') + '"').join(',')).join('\r\n') + '\r\n';
export const sha = text => createHash('sha256').update(text).digest('hex');

export function repair(rows, reviews, checks = []) {
  const headers = [...rows[0]];
  if (new Set(headers).size !== headers.length) throw new Error('Duplicate headers');
  for (const field of ['handle','account_id','contact_email','no_contact_beyond_x']) {
    if (!headers.includes(field)) throw new Error('Missing field: ' + field);
  }
  for (const field of EXTRA) if (!headers.includes(field)) headers.push(field);
  const output = rows.slice(1).map(r => {
    if (r.length !== rows[0].length) throw new Error('CSV row width mismatch');
    return Object.fromEntries(headers.map(h => [h, r[rows[0].indexOf(h)] ?? '']));
  });
  const handles = new Map(), ids = new Set();
  for (const row of output) {
    const h = row.handle.toLowerCase();
    if (!h || !row.account_id || handles.has(h) || ids.has(row.account_id)) throw new Error('Ambiguous account identity');
    handles.set(h, row); ids.add(row.account_id);
  }
  const changes = []; const seen = new Set();
  const update = (row, field, value) => {
    if (row[field] !== value) {
      changes.push({handle:row.handle, account_id:row.account_id, field, before:row[field], after:value});
      row[field] = value;
    }
  };
  // The legacy collector stored no per-page success evidence. YES is unsupported.
  for (const row of output) if (row.no_contact_beyond_x === 'YES') {
    update(row, 'no_contact_beyond_x', '');
    if (!row.contact_search_status) update(row, 'contact_search_status', 'Incomplete legacy check; absence of other routes not verified');
  }
  const checked = new Set();
  for (const check of checks) {
    const h = check.handle.toLowerCase(), row = handles.get(h);
    if (checked.has(h) || !row || row.account_id !== check.account_id) throw new Error('Check identity mismatch');
    checked.add(h);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(check.checked_on) || !check.reason || !check.source_urls?.length ||
        !check.source_urls.every(u => /^https?:\/\//.test(u))) throw new Error('Missing check provenance');
    if (row.alternative_contact_routes) throw new Error('Existing verified routes require reconciliation before incomplete check');
    update(row, 'contact_search_status', `Incomplete check ${check.checked_on}: ${check.reason}`);
  }
  for (const review of reviews) {
    const h = review.handle.toLowerCase(), row = handles.get(h);
    if (seen.has(h) || !row || row.account_id !== review.account_id) throw new Error('Review identity mismatch');
    seen.add(h);
    if (!review.routes?.length) throw new Error('Empty review is not a negative finding');
    const summary = [];
    for (const route of review.routes) {
      if (!['personal_email','work_email','organisation_forwarding','contact_form','contact_page'].includes(route.type)) throw new Error('Unknown route type');
      if (!/^https?:\/\//.test(route.source_url) || !/^\d{4}-\d{2}-\d{2}$/.test(route.verified_on) || !route.evidence || !route.instruction) throw new Error('Missing route provenance');
      if (['contact_form','contact_page'].includes(route.type) ? !/^https?:\/\//.test(route.address) : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(route.address)) throw new Error('Invalid route address');
      summary.push(`${route.type}: ${route.address}\n${route.instruction}\nSource: ${route.source_url}\nVerified: ${route.verified_on}`);
    }
    const value = summary.join('\n\n');
    if (row.alternative_contact_routes && row.alternative_contact_routes !== value) throw new Error('Existing route notes require explicit reconciliation');
    update(row, 'alternative_contact_routes', value);
    update(row, 'contact_search_status', 'Public route verified; other routes not exhaustively checked');
    if (!row.contact_email && review.primary_email) {
      if (!review.routes.some(r => !['contact_form','contact_page'].includes(r.type) && r.address === review.primary_email)) throw new Error('Primary email lacks reviewed evidence');
      update(row, 'contact_email', review.primary_email);
    }
  }
  return {rows:[headers,...output.map(r=>headers.map(h=>r[h]))], changes};
}

async function main() {
  const [master, manifest, mode] = process.argv.slice(2);
  if (!master || !manifest || !['--plan','--apply'].includes(mode)) throw new Error('Usage: node repair_outreach_routes.mjs MASTER.csv REVIEWS.json --plan|--apply');
  const source = await fs.readFile(master, 'utf8');
  const packet = JSON.parse(await fs.readFile(manifest, 'utf8'));
  if (packet.expected_master_sha256 !== sha(source)) throw new Error('Master changed since review; regenerate plan');
  const result = repair(parseCsv(source), packet.reviews, packet.checks);
  const text = encodeCsv(result.rows);
  if (JSON.stringify(parseCsv(text)) !== JSON.stringify(result.rows)) throw new Error('CSV roundtrip failed');
  const counts = {accounts:result.rows.length-1, reviewed_accounts:packet.reviews.length,
    checked_accounts:new Set([...(packet.checks||[]),...packet.reviews].map(r=>r.handle.toLowerCase())).size,
    reviewed_routes:packet.reviews.reduce((n,r)=>n+r.routes.length,0),
    cleared_unsupported_flags:result.changes.filter(c=>c.field==='no_contact_beyond_x').length,
    changes:result.changes.length};
  if (mode === '--apply') {
    const backup = master + '.before-route-repair-' + packet.batch_id;
    await fs.writeFile(backup, source, {flag:'wx',mode:0o600});
    const receipt = {batch_id:packet.batch_id,before_sha256:sha(source),after_sha256:sha(text),counts,changes:result.changes};
    await fs.writeFile(master+'.route-repair-'+packet.batch_id+'.json',JSON.stringify(receipt,null,2),{flag:'wx',mode:0o600});
    if (sha(await fs.readFile(master,'utf8')) !== sha(source)) throw new Error('Master changed during apply; no replacement written');
    const staged = master + '.route-repair-staged-' + packet.batch_id;
    await fs.writeFile(staged,text,{flag:'wx',mode:0o600});
    await fs.rename(staged,master);
    if (sha(await fs.readFile(master,'utf8')) !== receipt.after_sha256) throw new Error('Saved-file mismatch');
  }
  console.log('✓ Exact account identities and CSV roundtrip');
  console.log(JSON.stringify(counts));
  console.log(mode === '--plan' ? 'Plan only; no files changed.' : '✓ Backup, change receipt and saved CSV verified. No messages sent.');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e=>{console.error('Route repair failed:',e.message);process.exitCode=1;});
