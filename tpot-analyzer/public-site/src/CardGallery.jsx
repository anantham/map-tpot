import { getAllCachedCards } from './GenerateCard'
import './card-gallery.css'

export default function CardGallery({ onMemberClick, onBack }) {
  const cards = getAllCachedCards()

  return (
    <div className="gallery">
      <div className="gallery-back">
        <a href="/" onClick={(e) => { e.preventDefault(); onBack() }}>←</a>
      </div>

      <h1 className="gallery-title">Card Gallery</h1>
      <p className="gallery-subtitle">
        {cards.length} card{cards.length !== 1 ? 's' : ''} generated
      </p>

      {cards.length === 0 && (
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
          </a>
        ))}
      </div>
    </div>
  )
}
