import { useState } from 'react'
import './community-page.css'
import iconographyData from '../../config/community_iconography.json'

const ICONOGRAPHY = iconographyData.communities

function TweetCard({ tweet, username, communityColor }) {
  const typeLabels = {
    thread: '🧵 thread',
    reply: '↩ reply',
    retweet: '🔁 RT',
    tweet: 'tweet',
  }
  const date = tweet.created_at
    ? new Date(tweet.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : ''
  const xUrl = `https://x.com/${username}/status/${tweet.id}`

  return (
    <div className="cp-tweet" style={{ borderLeftColor: tweet._isTop ? communityColor : '#333' }}>
      <div className="cp-tweet-header">
        <span className="cp-tweet-type" style={{ color: tweet._isTop ? communityColor : '#aaa' }}>
          {typeLabels[tweet.type] || 'tweet'} · {date}
        </span>
        <a href={xUrl} target="_blank" rel="noopener noreferrer" className="cp-tweet-link">
          ↗ view on X
        </a>
      </div>
      <div className="cp-tweet-text">{tweet.text}</div>
      <div className="cp-tweet-stats">
        <span>❤ {tweet.favorite_count}</span>
        <span>🔁 {tweet.retweet_count}</span>
      </div>
    </div>
  )
}

function SpotlightCard({ member, communityColor, onMemberClick }) {
  const tweetsWithTop = (member.tweets || []).map((t, i) => ({ ...t, _isTop: i === 0 }))

  return (
    <div className="cp-spotlight">
      <div className="cp-spotlight-header">
        <div className="cp-spotlight-avatar" style={{ background: '#333' }} />
        <div className="cp-spotlight-info">
          <a
            className="cp-spotlight-handle"
            style={{ color: communityColor }}
            href={`/?handle=${member.username}`}
            onClick={(e) => {
              e.preventDefault()
              onMemberClick(member.username)
            }}
          >
            @{member.username}
          </a>
          <div className="cp-spotlight-bio">{member.bio}</div>
        </div>
        <div className="cp-spotlight-weight">weight {member.weight.toFixed(2)}</div>
      </div>
      {tweetsWithTop.map(t => (
        <TweetCard
          key={t.id}
          tweet={t}
          username={member.username}
          communityColor={communityColor}
        />
      ))}
    </div>
  )
}

function MemberGridItem({ member, communityColor, onMemberClick }) {
  return (
    <a
      className="cp-member-item"
      href={`/?handle=${member.username}`}
      onClick={(e) => {
        e.preventDefault()
        onMemberClick(member.username)
      }}
    >
      <div className="cp-member-handle" style={{ color: communityColor }}>@{member.username}</div>
      <div className="cp-member-bio">{member.bio}</div>
    </a>
  )
}

export default function CommunityPage({
  community,
  communities,
  onBack,
  onMemberClick,
  onCommunityClick,
}) {
  const featured = community.featured_members || []
  const allMembers = community.all_members || []
  const browseableCount = featured.length + allMembers.length
  const color = community.color

  const [copied, setCopied] = useState(false)

  const handleShare = () => {
    const url = `${window.location.origin}/?community=${community.slug}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const siblings = (communities || []).filter(c => c.id !== community.id)

  return (
    <div className="community-page">
      <div className="cp-back">
        <a href="/" onClick={(e) => { e.preventDefault(); onBack() }}>←</a>
      </div>

      <div className="cp-hero" style={{ borderBottomColor: color }}>
        <div className="cp-hero-dot" style={{ background: color }} />
        <div className="cp-hero-content">
          <h1 className="cp-hero-name">{community.name}</h1>
          <p className="cp-hero-desc">{community.description}</p>
          <div className="cp-hero-meta">
            <span>{browseableCount} members</span>
            <span>·</span>
            <span>{featured.length} featured</span>
            <span>·</span>
            <button className="cp-share-btn" onClick={handleShare} style={{ color }}>
              {copied ? '✓ Link copied!' : '🔗 Share this community'}
            </button>
          </div>
        </div>
      </div>

      {/* Community Identity — banner image + tagline */}
      {(() => {
        const icon = ICONOGRAPHY[community.short_name]
        if (!icon) return null
        return (
          <div className="cp-identity" style={{ borderColor: color }}>
            <img
              className="cp-identity-banner"
              src={`/images/communities/${community.short_name}.png`}
              alt={`${community.name} — ${icon.tagline}`}
              onError={(e) => { e.target.style.display = 'none' }}
            />
            <div className="cp-identity-footer">
              <p className="cp-identity-tagline">&ldquo;{icon.tagline}&rdquo;</p>
              {icon.memetic_name && (
                <span className="cp-identity-aka">aka <strong>{icon.memetic_name}</strong></span>
              )}
              <div className="cp-identity-palette-inline">
                {icon.colors.map((c, i) => (
                  <div key={i} className="cp-identity-swatch" style={{ background: c }} title={c} />
                ))}
              </div>
            </div>
          </div>
        )
      })()}

      <div className="cp-body">
        {/* Left column: spotlights */}
        {featured.length > 0 && (
          <div className="cp-spotlights">
            <div className="cp-section-label">Prototypical Members</div>
            {featured.map(m => (
              <SpotlightCard
                key={m.username}
                member={m}
                communityColor={color}
                onMemberClick={onMemberClick}
              />
            ))}
          </div>
        )}

        {/* Right column: all members sidebar */}
        {allMembers.length > 0 && (
          <div className="cp-all-members">
            <div className="cp-section-label">
              All Members · {browseableCount}
            </div>
            <div className="cp-member-list">
              {allMembers.map(m => (
                <MemberGridItem
                  key={m.username}
                  member={m}
                  communityColor={color}
                  onMemberClick={onMemberClick}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="cp-sibling-nav">
        <div className="cp-sibling-links">
          {siblings.map(c => (
            <a
              key={c.id}
              href={`/?community=${c.slug}`}
              style={{ color: c.color }}
              onClick={(e) => {
                e.preventDefault()
                onCommunityClick(c.slug)
                window.scrollTo(0, 0)
              }}
            >
              {c.name}
            </a>
          ))}
        </div>
        <div className="cp-footer-text">Find My Ingroup · amiingroup.vercel.app</div>
      </div>
    </div>
  )
}
