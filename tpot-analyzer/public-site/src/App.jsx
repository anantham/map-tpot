import { useState, useEffect } from 'react'

export default function App() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch('/data.json').then(r => r.json()).then(setData)
  }, [])

  if (!data) return <div className="loading">Loading...</div>

  return (
    <div className="app">
      <h1>{data.meta.site_name}</h1>
      <p className="tagline">Find where you belong in TPOT</p>
      <p className="stats">{data.meta.total_searchable.toLocaleString()} accounts indexed</p>
    </div>
  )
}
