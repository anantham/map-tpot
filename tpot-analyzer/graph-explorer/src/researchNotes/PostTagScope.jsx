import { useState } from 'react'

const types = { reply: 'Replies', quote: 'Quotes', repost: 'Reposts', mention: 'Mentions' }

export default function PostTagScope({ value, onChange, localApi = false }) {
  const [words,setWords] = useState(value.query || '')
  const [postDays,setPostDays] = useState(String(value.postWithinDays ?? 90))
  const change = (key, next) => onChange({ ...value, [key]: next })
  const invalidWords = words.trim().length === 1
  const unchanged = words.trim() === (value.query || '') && Number(postDays) === (value.postWithinDays ?? 90)
  return <fieldset className="working-post-tag-scope">
    <legend>Narrow the reference evidence</legend>
    <fieldset><legend>Tag discovery reference types</legend>
      {Object.entries(types).map(([kind,label]) => <label key={kind}>
        <input type="checkbox" checked={value.types.includes(kind)} onChange={event => change('types',
          event.target.checked ? [...value.types,kind] : value.types.filter(item => item !== kind))} /> {label}
      </label>)}
    </fieldset>
    {value.types.length === 0 && <p role="alert">Select at least one reference type.</p>}
    <label htmlFor="tag-reference-direction">Links from your examples</label>
    <select id="tag-reference-direction" value={value.direction} onChange={event => change('direction',event.target.value)}>
      <option value="outgoing">Accounts your examples refer to</option>
      <option value="incoming">Accounts referring to your examples</option>
    </select>
    {!localApi && <>
      <label htmlFor="tag-reference-min-posts">Minimum lifetime posts per link and type</label>
      <select id="tag-reference-min-posts" value={value.minPosts} onChange={event => change('minPosts',Number(event.target.value))}>
        {[1,3,10,25].map(number => <option key={number} value={number}>{number}</option>)}
      </select>
      <label htmlFor="tag-reference-recency">Latest reference</label>
      <select id="tag-reference-recency" value={value.latestWithinDays} onChange={event => change('latestWithinDays',Number(event.target.value))}>
        <option value={30}>Within 30 days</option><option value={90}>Within 90 days</option>
        <option value={365}>Within a year</option><option value={0}>Any date</option>
      </select>
    </>}
    <label htmlFor="tag-reference-min-support">Minimum supporting IN examples</label>
    <select id="tag-reference-min-support" value={value.minSupport} onChange={event => change('minSupport',Number(event.target.value))}>
      {[1,2,3,5].map(number => <option key={number} value={number}>{number}</option>)}
    </select>
    {localApi
      ? <small>Historical saved API references across all dates; no recent-activity filter. Coverage is partial, so missing references are unknown. Multiple types from one example count once. One hop only.</small>
      : <small>Lifetime repetition and the latest date are separate: this does not require that many recent posts.
        Multiple reference types from one example still count as one supporting example. One hop only.</small>}
    {!localApi && <form aria-label="Filter candidates by post content" className="working-tag-content-filter" onSubmit={event => {
      event.preventDefault()
      if (!invalidWords && !unchanged) onChange({ ...value,query:words.trim(),postWithinDays:Number(postDays) })
    }}>
      <label htmlFor="tag-content-words">Words in candidate posts (optional)</label>
      <input id="tag-content-words" value={words} maxLength={120} onChange={event => setWords(event.target.value)} placeholder="e.g. Buddhism Marxist" />
      <label htmlFor="tag-content-window">Candidate post window</label>
      <select id="tag-content-window" value={postDays} disabled={words.trim().length < 2 && !value.query}
        onChange={event => setPostDays(event.target.value)}>
        <option value="30">Within 30 days</option><option value="90">Within 90 days</option>
        <option value="365">Within a year</option><option value="0">Any date</option>
      </select>
      <small>All words must occur across their own indexed posts, possibly in different posts.
        This post window is separate from the reference date above. Quotes and criticism can match.</small>
      {invalidWords && <p role="alert">Use at least two characters, or clear the filter.</p>}
      <button type="submit" disabled={invalidWords || unchanged}>Apply content filter</button>
      {value.query && <button type="button" onClick={() => {
        setWords(''); setPostDays(String(value.postWithinDays ?? 90)); onChange({ ...value,query:'' })
      }}>Clear content filter</button>}
    </form>}
  </fieldset>
}
