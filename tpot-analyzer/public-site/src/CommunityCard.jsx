export default function CommunityCard({ handle, displayName, bio, tier, memberships, communityMap }) {
  const isClassified = tier === 'classified'

  // Resolve community names and colors, sort by weight descending
  const bars = (memberships || [])
    .map(m => {
      const community = communityMap.get(m.community_id)
      return {
        name: community?.name || m.community_name || 'Unknown',
        color: community?.color || '#666',
        weight: m.weight,
        pct: Math.round(m.weight * 100),
      }
    })
    .sort((a, b) => b.weight - a.weight)

  return (
    <div className={`community-card ${isClassified ? 'card-classified' : 'card-propagated'}`} id="community-card">
      <div className="card-header">
        <span className="card-handle">@{handle}</span>
        {isClassified && displayName && (
          <span className="card-display-name">{displayName}</span>
        )}
      </div>

      {isClassified && bio && (
        <p className="card-bio">{bio}</p>
      )}

      <div className="card-bars">
        {bars.map((bar, i) => (
          <div className="bar-row" key={i}>
            <span className="bar-label">{bar.name}</span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${bar.pct}%`,
                  backgroundColor: isClassified ? bar.color : '#555',
                }}
              />
            </div>
            <span className="bar-pct">{bar.pct}%</span>
          </div>
        ))}
      </div>

      {!isClassified && (
        <p className="card-note">
          Based on your network position. Contribute your data to see yourself in color.
        </p>
      )}

      <div className="card-footer">findmyingroup.com</div>
    </div>
  )
}
