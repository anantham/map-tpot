export default function About({ meta }) {
  const counts = meta?.counts || {}
  const links = meta?.links || {}
  const siteName = meta?.site_name || 'Find My Ingroup'

  const numCommunities = counts.communities || 'many'
  const classifiedStr = counts.classified_accounts?.toLocaleString() || 'hundreds of'
  const propagatedStr = counts.propagated_handles?.toLocaleString() || 'a growing set of'
  const showArchivePara = links.curator_dm && links.community_archive

  return (
    <div className="about-page">
      <a href="/" className="about-back">&larr; Back to search</a>

      <h1 className="about-title">How This Map Was Made</h1>

      {/* ── Section 1: Why This Exists ── */}
      <section className="about-section about-origin">
        <h2>Why This Exists</h2>
        <p>
          I followed around 2,000 people on Twitter. My feed was a firehose&mdash;brilliant
          posts from people I cared about buried under noise from people I&rsquo;d followed
          in a different season of my life. Lists were too manual; follow/unfollow felt like
          a false dichotomy.
        </p>
        <p>
          The real problem was that TPOT isn&rsquo;t one thing. It&rsquo;s{' '}
          {numCommunities} overlapping subcultures with their own inside references,
          aesthetic sensibilities, and epistemic norms. Some of those subcultures I&rsquo;m
          deeply embedded in. Others I just orbit. I wanted to see the map.
        </p>
        <p>
          This site is that map, made public so you can find your place in it too.
        </p>
      </section>

      {/* ── Section 2: What Your Card Means ── */}
      <section className="about-section">
        <h2>What Your Card Means</h2>

        <div className="about-tier">
          <span className="about-badge about-badge--color">Colorful card</span>
          <p>
            <strong>{classifiedStr} accounts</strong> have colorful cards. This means we
            analyzed their follow patterns and retweet targets directly&mdash;algorithmically
            seeded from the follow graph and then refined through human curation. The
            communities on your card reflect which subcultures your behavior most resembles.
          </p>
        </div>

        <div className="about-tier">
          <span className="about-badge about-badge--gray">Grayscale card</span>
          <p>
            <strong>{propagatedStr} accounts</strong> have grayscale cards. This means your
            community placement was inferred from where you sit in the follow graph relative
            to classified accounts&mdash;not from direct analysis of your follows. The
            placement is meaningful but less certain.
          </p>
        </div>

        {showArchivePara && (
          <p>
            Want a color card? You can contribute your follow and retweet data via the{' '}
            <a href={links.community_archive} target="_blank" rel="noopener noreferrer">
              community archive
            </a>
            , or{' '}
            <a href={links.curator_dm} target="_blank" rel="noopener noreferrer">
              DM the curator
            </a>
            . Contributing runs the full classification pipeline on your account and
            produces a richer, higher-confidence community profile.
          </p>
        )}
      </section>

      {/* ── Section 3: How We Know ── */}
      <section className="about-section">
        <h2>How We Know</h2>

        <h3>Who you follow &rarr; color cards</h3>
        <p>
          We build a behavioral feature matrix where each row is an account and the columns
          are who they follow and who they retweet. TF-IDF weighting means distinctive
          signals matter more&mdash;following a niche account that separates one subculture
          from another counts more than following an account everyone follows. Follow signals
          and retweet signals are normalized separately, with retweet targets weighted at
          0.6&times; to reflect that retweets are a coarser signal than deliberate follows.
          Non-negative Matrix Factorization (NMF) then decomposes this into community
          memberships. The resulting communities are reviewed and named by human curators.
        </p>

        <h3>Your neighbors &rarr; grayscale cards</h3>
        <p>
          For accounts not in the classified set, we use harmonic label propagation. The
          directed follow graph is symmetrized into an undirected similarity graph, then
          known community labels are &ldquo;spread&rdquo; through the network to unlabeled
          nodes. Accounts close to many labeled neighbors in the same community receive
          high-confidence placements; accounts at community boundaries or far from any
          labeled seed receive lower-confidence placements. We say &ldquo;neighbors&rdquo;
          rather than &ldquo;mutuals&rdquo; because the propagation uses the symmetrized
          graph, not just bidirectional edges.
        </p>
      </section>

      {/* ── Section 4: How We Check Our Work ── */}
      <section className="about-section">
        <h2>How We Check Our Work</h2>
        <p>
          We&rsquo;re building a held-out evaluation system&mdash;a set of accounts with
          human-verified community labels that were never used during training. The
          infrastructure is in place and we&rsquo;re actively collecting labels. Once the
          labeled set is large enough, we&rsquo;ll be able to report precision and recall
          for each community and track whether pipeline changes improve or degrade accuracy.
          For now, community placements should be read as strong signals, not verdicts.
        </p>
      </section>

      {/* ── Section 5: Under the Hood ── */}
      <section className="about-section">
        <h2>Under the Hood</h2>

        <details className="about-disclosure">
          <summary>How do follow-based classifications work?</summary>
          <div className="about-disclosure-body">
            <p>
              We construct two sparse matrices&mdash;one for follow targets, one for retweet
              targets&mdash;and apply TF-IDF normalization to each separately. The matrices
              are concatenated column-wise, with the retweet columns scaled by 0.6 before
              concatenation. This combined matrix <em>A</em> approximates:
            </p>
            <p className="about-formula">
              <em>A</em> &asymp; <em>W</em> &middot; <em>H</em>
            </p>
            <p>
              where <em>W</em> (accounts &times; communities) gives each account&rsquo;s
              community memberships and <em>H</em> (communities &times; features) describes
              each community by its top follow and retweet targets. NMF enforces
              non-negativity, which produces parts-based, interpretable decompositions.
            </p>
            <p className="about-caveat">
              <strong>Known limitation:</strong> Accounts with highly concentrated
              memberships (e.g., 95% in one community) have less informative second and
              third memberships. The NMF score is meaningful as a ranking within each
              community, less so as an absolute probability.
            </p>
          </div>
        </details>

        <details className="about-disclosure">
          <summary>How does neighbor propagation work?</summary>
          <div className="about-disclosure-body">
            <p>
              Harmonic label propagation is a Gaussian Random Field solve over the graph
              Laplacian. Partition nodes into labeled (<em>L</em>) and unlabeled (<em>U</em>)
              sets. The harmonic solution for unlabeled node scores is:
            </p>
            <p className="about-formula">
              <em>f</em><sub>U</sub> = &minus;<em>L</em><sub>UU</sub><sup>&minus;1</sup>
              &middot; <em>L</em><sub>UL</sub> &middot; <em>f</em><sub>L</sub>
            </p>
            <p>
              where <em>L</em> is the normalized graph Laplacian. In practice this is solved
              iteratively. To prevent large communities from overwhelming small ones, labeled
              seeds are reweighted by inverse square root of class size (
              1&thinsp;/&thinsp;&radic;<em>n</em><sub>c</sub>).
            </p>
            <p className="about-caveat">
              <strong>Known limitation:</strong> Only a small fraction of nodes are labeled
              seeds. Accounts more than ~3 hops from any seed receive less reliable
              placements. Grayscale cards at the edge of the graph should be treated as
              approximate.
            </p>
          </div>
        </details>
      </section>

      {/* ── Section 6: What's Coming Next ── */}
      <section className="about-section">
        <h2>What&rsquo;s Coming Next</h2>
        <p>
          The most important missing piece is <strong>tweet-level evidence</strong>. Right
          now, color cards are based on follow and retweet targets, not on what someone
          actually writes. That gap produces real errors&mdash;for example,{' '}
          <a href="https://twitter.com/repligate" target="_blank" rel="noopener noreferrer">
            @repligate
          </a>{' '}
          was assigned 100% Qualia Research by NMF (follows the right people), but her
          tweets point clearly toward LLM Whisperers. Once we layer in tweet content, cards
          like that will self-correct.
        </p>
        <p>Other things in the pipeline:</p>
        <ul>
          <li>Community fingerprinting from tweet vocabulary and link domains</li>
          <li>Subcommunity splits for communities that have grown heterogeneous</li>
          <li>Temporal trajectories &mdash; how community membership shifts over time</li>
          <li>A live accuracy scoreboard once the evaluation set is large enough</li>
        </ul>
      </section>

      {/* ── Section 7: Open Source ── */}
      <section className="about-section about-cta">
        <h2>Open Source</h2>
        <p>
          The entire pipeline&mdash;graph construction, NMF classification, label
          propagation, curation tooling, and this site&mdash;is open source. You can clone
          the repo, feed in your own follow data, and build a community map for any corner
          of the internet.
        </p>
        {links.repo ? (
          <a
            href={links.repo}
            target="_blank"
            rel="noopener noreferrer"
            className="about-repo-link"
          >
            View the code on GitHub &rarr;
          </a>
        ) : (
          <span className="about-repo-link">Repository link coming soon</span>
        )}
      </section>

      <div className="about-footer">
        <a href="/" className="about-back">
          &larr; Back to {siteName}
        </a>
      </div>
    </div>
  )
}
