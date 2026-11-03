import {useState} from 'react';
import {setCardCapability} from './cardCapabilities';
export default function CardGrantInput() {
  const [token,setToken]=useState('');
  const [status,setStatus]=useState('');
  function apply() {
    try {const handle=setCardCapability(token.trim());setToken('');setStatus(`Grant added for @${handle} in this tab.`);}
    catch(error) {setStatus(error.message);}
  }
  return <section>
    <p>A curator can provide a one-use grant for a sponsored card. It expires within 10 minutes.</p>
    <label htmlFor="card-grant">Card grant</label>
    <input id="card-grant" type="password" value={token} onChange={e=>setToken(e.target.value)} autoComplete="off" />
    <button onClick={apply} disabled={!token.trim()}>Use grant</button>
    {status && <p role="status">{status}</p>}
  </section>;
}
