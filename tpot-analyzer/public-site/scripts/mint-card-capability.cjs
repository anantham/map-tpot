/** Offline operator grant issuer; input is JSON on stdin, secret stays in env.
 * {kind:'generate'|'gallery',subject:'approved-owner',body:{...},force?:false}
 * Output is a one-use bearer capability expiring in five minutes.
 */
const {readFileSync} = require('node:fs');
const {digestBody,signCapability,verifyCapability} = require('../api/_cardAdmission');
const {validateCardRequest} = require('../api/_cardRequest');
const {normalizeHandle,normalizeImage} = require('../api/_imagePolicy');
const {normalizeCommunities} = require('../api/_galleryPolicy');
async function main() {
  const raw = readFileSync(0);
  if (raw.length>5*1024*1024) throw new Error('Grant input too large');
  const input = JSON.parse(raw.toString('utf8'));
  if (!['generate','gallery'].includes(input.kind)) throw new Error('Invalid grant kind');
  let handle;
  if (input.kind==='generate') {
    handle=validateCardRequest(input.body).handle;
    normalizeCommunities(input.body.communities.slice(0,5));
  } else {
    if (!input.body || Object.keys(input.body).some(k=>!['handle','imageUrl','communities'].includes(k))) throw new Error('Invalid gallery request');
    handle=normalizeHandle(input.body.handle);
    normalizeCommunities(input.body.communities || []);
    await normalizeImage(input.body.imageUrl);
  }
  const digest=digestBody(input.body);
  const token=signCapability({kind:input.kind,subject:input.subject,handle,digest,
    expiresAt:Math.floor(Date.now()/1000)+300,force:input.body.force===true});
  verifyCapability(token,{kind:input.kind,handle,digest});
  process.stdout.write(token+'\n');
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
