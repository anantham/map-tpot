import { useState, useEffect, useCallback } from 'react'
import { getAllCachedCards } from './GenerateCard'
import './card-gallery.css'

function GalleryCardImage({ src, alt, onClick }) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className="gallery-card-img-wrapper">
      {!loaded && <div className="gallery-card-skeleton" />}
      <img
        src={src}
        alt={alt}
        className={`gallery-card-img ${loaded ? 'gallery-card-img--loaded' : 'gallery-card-img--loading'}`}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onClick={onClick}
        style={{ cursor: 'zoom-in' }}
      />
    </div>
  )
}

export default function CardGallery({ onMemberClick, onBack }) {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [fsIndex, setFsIndex] = useState(null)

  const isOpen = fsIndex !== null && cards.length > 0

  const goPrev = useCallback(() => {
    setFsIndex(i => (i > 0 ? i - 1 : cards.length - 1))
  }, [cards.length])

  const goNext = useCallback(() => {
    setFsIndex(i => (i < cards.length - 1 ? i + 1 : 0))
  }, [cards.length])

  const close = useCallback(() => setFsIndex(null), [])

  useEffect(() => {
    if (!isOpen) return
    const onKey = (e) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === 'ArrowRight') goNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, close, goPrev, goNext])

  useEffect(() => {
    // Show local cache immediately while server loads
    const local = getAllCachedCards()
    if (local.length > 0) {
      setCards(local)
      setLoading(false)
    }

    // Then fetch server gallery and merge with local (local wins for freshness)
    fetch('/api/gallery')
      .then(r => r.json())
      .then(data => {
        if (data.cards && data.cards.length > 0) {
          // Merge: local cards + server cards, dedup by handle, prefer local (fresher)
          const localCards = getAllCachedCards()
          const localMap = new Map(localCards.map(c => [c.handle, c]))
          for (const sc of data.cards) {
            if (!localMap.has(sc.handle)) {
              localMap.set(sc.handle, sc)
            }
          }
          const merged = [...localMap.values()].sort((a, b) => (b.cachedAt || b.generatedAt || 0) - (a.cachedAt || a.generatedAt || 0))
          setCards(merged)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const fsCard = isOpen ? cards[fsIndex] : null

  return (
    <div className="gallery">
      <div className="gallery-back">
        <a href="/" onClick={(e) => { e.preventDefault(); onBack() }}>← Back</a>
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

      {/* Skeleton placeholders while loading */}
      {loading && cards.length === 0 && (
        <div className="gallery-grid">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="gallery-card">
              <div className="gallery-card-skeleton" />
              <div className="gallery-card-handle-skeleton" />
            </div>
          ))}
        </div>
      )}

      <div className="gallery-grid">
        {cards.map((card, i) => (
          <div key={card.handle} className="gallery-card">
            <GalleryCardImage
              src={card.url}
              alt={`@${card.handle}`}
              onClick={() => setFsIndex(i)}
            />
            <a
              className="gallery-card-handle"
              href={`/?handle=${card.handle}`}
              onClick={(e) => {
                e.preventDefault()
                onMemberClick(card.handle)
              }}
            >
              @{card.handle}
            </a>
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
          </div>
        ))}
      </div>

      {isOpen && fsCard && (
        <div className="card-fullscreen-overlay" onClick={close}>
          <button className="card-fullscreen-close" onClick={close}>
            &times;
          </button>

          {cards.length > 1 && (
            <button
              className="card-fullscreen-nav card-fullscreen-nav--prev"
              onClick={(e) => { e.stopPropagation(); goPrev() }}
            >
              ‹
            </button>
          )}

          <div className="card-fullscreen-center" onClick={(e) => e.stopPropagation()}>
            <img
              className="card-fullscreen-image"
              src={fsCard.url}
              alt={`@${fsCard.handle}`}
            />
            <div className="card-fullscreen-handle">
              @{fsCard.handle}
              <span className="card-fullscreen-counter">
                {fsIndex + 1} / {cards.length}
              </span>
            </div>
          </div>

          {cards.length > 1 && (
            <button
              className="card-fullscreen-nav card-fullscreen-nav--next"
              onClick={(e) => { e.stopPropagation(); goNext() }}
            >
              ›
            </button>
          )}
        </div>
      )}
    </div>
  )
}
