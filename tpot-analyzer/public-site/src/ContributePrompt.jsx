export default function ContributePrompt({ handle, tier, links }) {
  const isNotFound = tier === 'not_found'

  return (
    <div className="contribute-prompt">
      {isNotFound && (
        <p className="contribute-missing">
          We don't have <strong>@{handle}</strong> in our database yet.
        </p>
      )}

      <h3 className="contribute-title">
        {isNotFound ? 'Get your card' : 'Unlock your full color card'}
      </h3>
      <p className="contribute-subtitle">
        {isNotFound
          ? 'Contribute your Twitter data to get a personalized community card:'
          : 'Your card is based on network position only. Share your tweets to get a richer, full-color analysis:'}
      </p>

      <ul className="contribute-paths">
        <li>
          <a href={links.curator_dm} target="_blank" rel="noopener noreferrer">
            DM the curator
          </a>
          <span className="path-desc"> &mdash; fastest way to get included</span>
        </li>
        <li>
          <a href={links.community_archive} target="_blank" rel="noopener noreferrer">
            Upload to Community Archive
          </a>
          <span className="path-desc"> &mdash; open-source Twitter data commons</span>
        </li>
        <li>
          <a href={links.repo} target="_blank" rel="noopener noreferrer">
            Clone the repo
          </a>
          <span className="path-desc"> &mdash; run the analysis yourself</span>
        </li>
      </ul>
    </div>
  )
}
