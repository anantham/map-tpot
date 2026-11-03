import {test} from 'node:test';
import assert from 'node:assert/strict';
import {repair,parseCsv,encodeCsv} from './repair_outreach_routes.mjs';
const rows = [['handle','account_id','contact_email','no_contact_beyond_x','draft_message','reply'],['demo','9007199254740993','','YES','a, "quoted"\nmessage','answered']];
const route = {type:'organisation_forwarding',address:'hello@example.org',source_url:'https://example.org/contact',verified_on:'2026-10-13',evidence:'Public organisation contact and named founder.',instruction:'Ask the organisation to forward to Demo; not personal email.'};
const review = {handle:'demo',account_id:'9007199254740993',primary_email:'hello@example.org',routes:[route]};
test('organisation forwarding survives export with provenance and unchanged history',()=>{
  const p=repair(rows,[review]); const r=Object.fromEntries(p.rows[0].map((h,i)=>[h,p.rows[1][i]]));
  assert.equal(r.contact_email,'hello@example.org'); assert.match(r.alternative_contact_routes,/not personal email/);
  assert.equal(r.no_contact_beyond_x,''); assert.equal(r.reply,'answered');assert.equal(r.draft_message,rows[1][4]);
  assert.equal(r.account_id,'9007199254740993'); assert.deepEqual(parseCsv(encodeCsv(p.rows)),p.rows);
});
test('existing email is never overwritten',()=>{const v=structuredClone(rows);v[1][2]='owner@example.net';assert.equal(repair(v,[review]).rows[1][2],'owner@example.net');});
test('missing review does not imply no alternative routes',()=>{const p=repair(rows,[]);assert.equal(p.rows[1][3],'');assert.match(p.rows[1][7],/Incomplete/);});
test('reject wrong identity and duplicate accounts',()=>{assert.throws(()=>repair(rows,[{...review,account_id:'wrong'}]),/identity/);assert.throws(()=>repair([...rows,rows[1]],[review]),/Ambiguous/);});
test('reject empty review, missing source and unsupported primary',()=>{assert.throws(()=>repair(rows,[{...review,routes:[]}]),/Empty/);assert.throws(()=>repair(rows,[{...review,routes:[{...route,source_url:''}]}]),/provenance/);assert.throws(()=>repair(rows,[{...review,primary_email:'guessed@example.org'}]),/evidence/);});
test('contact forms retained as links, never treated as email',()=>{const p=repair(rows,[{...review,primary_email:null,routes:[{...route,type:'contact_form',address:'https://example.org/contact'}]}]);assert.equal(p.rows[1][2],'');assert.match(p.rows[1][6],/contact_form/);});
test('idempotent projection refuses divergent existing route notes',()=>{const p=repair(rows,[review]);assert.equal(repair(p.rows,[review]).changes.length,0);p.rows[1][6]='Operator note';assert.throws(()=>repair(p.rows,[review]),/reconciliation/);});
test('incomplete checks retain reason without creating an absence claim or email',()=>{
  const check={handle:'demo',account_id:'9007199254740993',checked_on:'2026-10-13',source_urls:['https://example.org/'],reason:'Page unavailable; other routes not checked'};
  const p=repair(rows,[],[check]);assert.equal(p.rows[1][2],'');assert.equal(p.rows[1][3],'');assert.match(p.rows[1][7],/Page unavailable/);
  assert.throws(()=>repair(rows,[],[{...check,account_id:'wrong'}]),/identity/);
});
test('a published contact page is not mislabeled as a submitted form',()=>{
  const p=repair(rows,[{...review,primary_email:null,routes:[{...route,type:'contact_page',address:'https://example.org/contact'}]}]);
  assert.equal(p.rows[1][2],'');assert.match(p.rows[1][6],/contact_page/);
});
