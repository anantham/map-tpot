import { useState, useEffect } from 'react'
import { getAllCachedCards } from './GenerateCard'
import './card-gallery.css'

export default function CardGallery({ onMemberClick, onBack }) {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Try server gallery first, fall back to localStorage
    fetch('/api/gallery')
      .then(r => r.json())
      .then(data => {
        if (data.cards && data.cards.length > 0) {
          setCards(data.cards)
        } else {
          // Server empty or unavailable — use local cache
          setCards(getAllCachedCards())
        }
      })
      .catch(() => {
        // API not available (local dev) — use local cache
        setCards(getAllCachedCards())
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="gallery">
      <div className="gallery-back">
        <a href="/" onClick={(e) => { e.preventDefault(); onBack() }}>←</a>
      </div>

      <h1 className="gallery-title">Card Gallery</h1>
      <p className="gallery-subtitle">
        {loading ? 'Loading...' : `${cards.length} card${cards.length !== 1 ? 's' : ''} generated`}
      </p>

      {!loading && cards.length === 0 && (
        <p className="gallery-empty">
          No cards generated yet. Search for a handle to create your first collectible card.
        </p>
      )}

      <div className="gallery-grid">
        {cards.map(card => (
          <a
            key={card.handle}
            className="gallery-card"
            href={`/?handle=${card.handle}`}
            onClick={(e) => {
              e.preventDefault()
              onMemberClick(card.handle)
            }}
          >
            <img
              src={card.url}
              alt={`@${card.handle}`}
              className="gallery-card-img"
              loading="lazy"
            />
            <div className="gallery-card-handle">@{card.handle}</div>
            {card.communities && card.communities.length > 0 && (
              <div className="gallery-card-communities">
                {card.communities.slice(0, 3).map(c => (
                  <span
                    key={c.name}
                    className="gallery-card-dot"
                    style={{ background: c.color }}
                    title={c.name}
                  />
                ))}
              </div>
            )}
          </a>
        ))}
      </div>
    </div>
  )
}
