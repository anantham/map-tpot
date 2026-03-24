import { useState } from 'react'

export default function About({ meta, onNavigate }) {
  const [path, setPath] = useState(null)
  const counts = meta?.counts || {}
  const links = meta?.links || {}
  const siteName = meta?.site_name || 'Find My Ingroup'

  const numCommunities = counts.communities || 'many'
  const byBand = counts.by_band || {}
  const totalStr = counts.total_accounts?.toLocaleString() || '18,000+'
  const classifiedStr = byBand.exemplar?.toLocaleString() || '317'
  const showArchivePara = links.curator_dm && links.community_archive

  return (
    <div className="about-page">
      <a href="/" className="about-back" onClick={(e) => { e.preventDefault(); onNavigate ? onNavigate('/') : window.history.back() }}>&larr; Back to search</a>

      <h1 className="about-title">Find My Ingroup</h1>
      <p className="about-subtitle">A map of the communities inside your timeline</p>

      {/* ── Path Selector ── */}
      {!path && (
        <div className="about-selector">
          <p className="about-selector-prompt">How would you like to explore?</p>
          <div className="about-selector-buttons">
            <button
              className="about-selector-btn about-selector-btn--a"
              onClick={() => setPath('a')}
            >
              <span className="about-selector-label">I know what TPOT is, sorta</span>
              <span className="about-selector-desc">Find deeper communities, discover adjacent accounts</span>
            </button>
            <button
              className="about-selector-btn about-selector-btn--b"
              onClick={() => setPath('b')}
            >
              <span className="about-selector-label">What is going on?!</span>
              <span className="about-selector-desc">New here? Start with what this place even is</span>
            </button>
            <button
              className="about-selector-btn about-selector-btn--c"
              onClick={() => setPath('c')}
            >
              <span className="about-selector-label">I want to be inspired by your math</span>
              <span className="about-selector-desc">Pipeline walkthrough, design choices, validation</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Path indicator + reset ── */}
      {path && (
        <button className="about-path-reset" onClick={() => setPath(null)}>
          &larr; Choose a different path
        </button>
      )}

      {/* ════════════════════════════════════════════════ */}
      {/* PATH A: "I know what TPOT is, sorta"            */}
      {/* ════════════════════════════════════════════════ */}
      {path === 'a' && (
        <>
          <section className="about-section about-origin">
            <h2>The Illegibility Is the Point</h2>

            <p>
              You can understand TPOT&rsquo;s language. You&rsquo;re in because you recognize it.
              This isn&rsquo;t just a cute thing&mdash;it&rsquo;s an admission of how language shapes
              your mind. The shared references, the nested irony, the specific way people hold ideas
              here&mdash;it&rsquo;s a form of containment. People who know, know. People who don&rsquo;t,
              can&rsquo;t participate until they do.
            </p>
            <p>
              That illegibility protects the culture. But it has a cost: <strong>coordination is
              trapped in individual heads.</strong>
            </p>
          </section>

          <section className="about-section">
            <h2>People Ask Me</h2>

            <p>
              &ldquo;Who&rsquo;s working on agent foundations?&rdquo; &ldquo;Where&rsquo;s dharma
              Twitter?&rdquo; &ldquo;I want to learn about jhanas&mdash;who should I follow?&rdquo;
              &ldquo;What about nutrition, Ayurveda, somatic therapy?&rdquo; &ldquo;What about
              Kegan stages and adult development?&rdquo; &ldquo;What about farming, embodied living,
              beautiful cartography?&rdquo; &ldquo;What about gender discourse, dating?&rdquo;
              &ldquo;Who&rsquo;s in my city that&rsquo;s like me?&rdquo;
            </p>
            <p>
              I know the accounts. I know Richard Ngo is in agent foundations, I know repligate is in
              cyborgism, I know specific people working at specific niche corners of AI safety, meditation,
              and everything in between. But it&rsquo;s trapped in my head. It&rsquo;s not legible.
              I can&rsquo;t scale it.
            </p>
            <p>
              I&rsquo;m community building. I&rsquo;m field building. And there are people who need
              this map to find each other&mdash;to collaborate, to build projects, to start communities
              around shared interests.
            </p>
          </section>

          <section className="about-section">
            <h2>Take Charge</h2>
            <p>
              Rather than let Grok or an algorithm decide whose tweets you see in your feed, I want
              to make the structure visible. This site is one version of the map. But it&rsquo;s
              not <em>the</em> map.
            </p>
            <p>
              The whole thing is open source. You can fork the repo, feed in your own follow data,
              label tweets by your own aesthetics, carve out your own ontology of what this part of
              Twitter is&mdash;and thereby discover others you can work with.
            </p>
            {/* placeholder for links to posts about levels, language, etc. */}
          </section>

          <section className="about-section about-origin">
            <h2>My Story</h2>
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
        </>
      )}

      {/* ════════════════════════════════════════════════ */}
      {/* PATH B: "What is going on?!"                    */}
      {/* ════════════════════════════════════════════════ */}
      {path === 'b' && (
        <>
          <section className="about-section about-origin">
            <h2>There&rsquo;s a Loose Network on Twitter</h2>

            <p>
              It&rsquo;s not a hashtag. It&rsquo;s not a list. It&rsquo;s not an organization.
              It&rsquo;s a loose network of tens of thousands of accounts that share references,
              aesthetic sensibilities, and ways of thinking. People call it TPOT&mdash;&ldquo;this
              part of Twitter.&rdquo;
            </p>
            <p>
              You&rsquo;re &ldquo;in&rdquo; if you understand the language. That sounds circular,
              and it is. The shared language&mdash;the nested irony, the philosophical shitposts,
              the way people hold ideas loosely while caring deeply&mdash;is what defines the
              boundary. It&rsquo;s hard to see from outside because it&rsquo;s not trying to
              be seen.
            </p>
          </section>

          <section className="about-section">
            <h2>It&rsquo;s Actually Many Communities</h2>

            <p>
              Inside this network there are builders, contemplatives, poets, AI safety researchers,
              identity experimentalists, institution designers, people doing embodiment work,
              people exploring psychedelics, people building new forms of governance&mdash;overlapping
              but distinct. Currently we&rsquo;ve mapped {numCommunities} subcommunities.
            </p>
            <p>
              This site maps those subcommunities. Search your handle and see where you land.
              Browse a community to see who&rsquo;s in it. Follow a few accounts that match
              what you&rsquo;re curious about.
            </p>
          </section>

          <section className="about-section">
            <h2>How It Works (the Short Version)</h2>
            <p>
              We look at who follows whom. People who follow the same niche accounts tend to be
              in the same subcommunity&mdash;following a meditation teacher tells us more than
              following Elon Musk. An algorithm finds clusters of accounts with similar follow
              patterns, then a human curator reviews and names each cluster.
            </p>
            <p>
              For accounts not in the core dataset, we infer community placement from their
              position in the network&mdash;if most of your connections are Builders, you&rsquo;re
              probably Builder-adjacent. These inferred placements get a grayscale card instead
              of a colorful one, to signal lower confidence.
            </p>
          </section>
        </>
      )}

      {/* ════════════════════════════════════════════════ */}
      {/* PATH C: "I want to be inspired by your math"    */}
      {/* ════════════════════════════════════════════════ */}
      {path === 'c' && (
        <>
          {/* Stage 1: What We Can See */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">1</span>
              What We Can See
              <span className="about-badge-status about-badge-status--live">LIVE</span>
            </h2>

            <p>
              The{' '}
              <a href="https://www.community-archive.org/" target="_blank" rel="noopener noreferrer">
                Community Archive
              </a>{' '}
              is a project where Twitter users voluntarily share their data. {classifiedStr} people
              shared who they follow, who they retweet, and their tweets.
            </p>
            <p>
              That gives us a matrix: {classifiedStr} seed accounts &times; the ~182,000 accounts in
              their follow graph. For each archived account, we can see every follow and retweet.
              For the other ~182K, we only know that <em>someone</em> follows them&mdash;not who{' '}
              <em>they</em> follow.
            </p>
            <p>
              The result is a giant spreadsheet that&rsquo;s almost entirely empty&mdash;about 0.3%
              of cells are filled. That sparsity is the raw material.
            </p>
            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                @repligate is one of the {classifiedStr} who shared data. We can see all ~1,200
                accounts they follow and all their retweets. But for those 1,200 accounts, we only
                know @repligate follows them&mdash;not who <em>they</em> follow.
              </p>
            </div>
          </section>

          {/* Stage 2: What Signals We Use */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">2</span>
              What Signals We Use
            </h2>
            <p>
              We don&rsquo;t use a single signal. The pipeline layers multiple evidence types,
              each with different strengths:
            </p>
            <div className="about-signal-stack">
              <div className="about-signal-row">
                <span className="about-signal-name">Follow targets</span>
                <span className="about-signal-desc">Who you chose to listen to (deliberate, stable)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Retweet targets</span>
                <span className="about-signal-desc">What you amplify (weighted 0.6&times;, with optional time-decay)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Resolved like-author edges</span>
                <span className="about-signal-desc">~24K author-attributed likes (weighted 0.4&times;, positive valence)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Content vectors</span>
                <span className="about-signal-desc">25 macro-interest topics from 17.5M liked tweet texts (orthogonal to graph)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Co-followed topology</span>
                <span className="about-signal-desc">Accounts followed by the same people cluster together (Jaccard similarity)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Signed replies</span>
                <span className="about-signal-desc">17K signed reply pairs (author-liked + mutual-follow heuristics)</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Tweet labeling (bits)</span>
                <span className="about-signal-desc">Human-tagged tweets weighted by simulacrum level (L3 in-group = 2&times;)</span>
                <span className="about-badge-status about-badge-status--experimental">EXPERIMENTAL</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Engagement-weighted graph</span>
                <span className="about-signal-desc">Follow + RT + like + reply weights on propagation edges</span>
                <span className="about-badge-status about-badge-status--live">LIVE</span>
              </div>
            </div>
            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                Follow targets say &ldquo;Qualia Research&rdquo;&mdash;they follow QRI researchers,
                consciousness Twitter. But their tweet content says &ldquo;LLM Whisperers&rdquo;&mdash;they
                write about AI agents and prompt engineering. The follow signal and the tweet signal
                disagree. That&rsquo;s why we need both.
              </p>
            </div>
          </section>

          {/* Stage 3: How The First Map Is Made */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">3</span>
              How the First Map Is Made
              <span className="about-badge-status about-badge-status--live">LIVE</span>
            </h2>


            <h3>Four decisions before any code</h3>

            <details className="about-disclosure">
              <summary>1. How to represent the data</summary>
              <div className="about-disclosure-body">
                <p>
                  What counts as evidence that two accounts are in the same community? A follow is
                  deliberate&mdash;you chose to listen. A retweet is behavioral&mdash;you chose to
                  amplify. A like is cheap positive signal. A reply is unsigned&mdash;arguing looks
                  the same as agreeing.
                </p>
                <p>
                  We chose: <strong>follows + retweets + resolved like-author edges, separately
                  TF-IDF weighted</strong> (retweets at 0.6&times;, likes at 0.4&times;). TF-IDF means
                  distinctive follows matter more&mdash;following a niche consciousness researcher separates
                  communities, following @elonmusk doesn&rsquo;t.
                </p>
                <p>
                  The &ldquo;resolved likes&rdquo; caveat: of 17.5M raw likes in the archive, only ~24K
                  can be attributed to an author (the liked tweet&rsquo;s author must also be in the archive).
                  That&rsquo;s a partial structural signal over archive-visible targets, not the full liked-author
                  graph. But it still covers ~79% of seed accounts and meaningfully shifted community boundaries.
                </p>
                <p>
                  Also live: time-decay on retweets (recent RTs weighted more than old ones), 17K signed
                  reply pairs (author-liked-reply + mutual-follow heuristics), and engagement-weighted
                  propagation edges.
                </p>
              </div>
            </details>

            <details className="about-disclosure">
              <summary>2. How to discover communities</summary>
              <div className="about-disclosure-body">
                <p>
                  The deeper question: <strong>what is a community membership?</strong> Is each
                  account in exactly one community (hard clustering)? A weighted mixture that sums
                  to 1 (LDA)? Or independent memberships&mdash;you can be 80% Builders AND 60%
                  Contemplative?
                </p>
                <p>
                  We chose <strong>NMF (Non-negative Matrix Factorization)</strong>&mdash;independent,
                  non-negative, parts-based. The matrix <em>A</em> decomposes as:
                </p>
                <p className="about-formula">
                  <em>A</em> &asymp; <em>W</em> &middot; <em>H</em>
                </p>
                <p>
                  <em>W</em> ({classifiedStr} &times; {numCommunities}) gives each account&rsquo;s
                  community weights. <em>H</em> ({numCommunities} &times; 72K) shows what defines each
                  community&mdash;which follow targets, which retweet targets. That second matrix is
                  what makes human curation possible: you can see <em>why</em> a cluster exists.
                </p>
              </div>
            </details>

            <details className="about-disclosure">
              <summary>3. How to turn discovery into a prior</summary>
              <div className="about-disclosure-body">
                <p>
                  NMF gives you factors. That&rsquo;s not the same as beliefs. The prior could be
                  uniform (no opinion), population base rate (bigger communities get higher prior),
                  NMF-derived (let the math decide), or manually seeded by a curator.
                </p>
                <p>
                  We use the <strong>NMF-derived prior</strong>, but how strong it is matters as
                  much as where it comes from. How many labeled tweets should it take to override
                  &ldquo;100% Qualia Research&rdquo;? A skeptical prior (worth 2 virtual tweets) gets
                  corrected quickly. A strong prior (worth 20) resists correction.
                </p>
                <p>
                  The prior should also depend on data richness: full archive accounts get a confident
                  prior, shadow-graph accounts get a weaker one, accounts not in the graph at all
                  should start as <code>unknown</code>.
                </p>
              </div>
            </details>

            <details className="about-disclosure">
              <summary>4. What about accounts that fit nowhere?</summary>
              <div className="about-disclosure-body">
                <p>
                  Some accounts are bridges between communities. Some are outliers. Some are evidence
                  the ontology is incomplete.
                </p>
                <p>
                  The propagation output includes a <code>none</code> class and an entropy-based
                  uncertainty score. Accounts with high <code>none</code> weight or high entropy
                  are classified as &ldquo;frontier&rdquo;&mdash;we&rsquo;d rather say &ldquo;we
                  don&rsquo;t know&rdquo; than guess wrong.
                </p>
                <p>
                  Bridge accounts are not failures. @vgr (followed by 117 seeds from all 15
                  communities) genuinely straddles everything&mdash;they&rsquo;re pan-TPOT. The
                  system preserves their full membership distribution rather than forcing them
                  into a single bucket.
                </p>
              </div>
            </details>

            <h3>Then: human naming</h3>
            <p>
              The {numCommunities} factors that come out of NMF are anonymous&mdash;&ldquo;Factor
              7&rdquo; means nothing. A curator reviews the top accounts and top follow targets in
              each factor and names them: &ldquo;these people all follow the same meditation teachers
              and consciousness researchers &rarr; Contemplative Practitioners.&rdquo;
            </p>

            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                NMF result (with likes): <strong>52% LLM Whisperers, 16% AI Creatives, 15% Queer TPOT.</strong>{' '}
                The old follow-only NMF said 100% Qualia Research. Adding likes + retweets shifted them
                dramatically&mdash;their like patterns reveal the LLM tinkering identity that follows alone
                couldn&rsquo;t see. This is the graph prior. It&rsquo;s closer to the truth now, but tweet
                labeling refines it further.
              </p>
            </div>
          </section>

          {/* Stage 4: How The First Map Gets Corrected */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">4</span>
              How the First Map Gets Corrected
              <span className="about-badge-status about-badge-status--experimental">EXPERIMENTAL</span>
            </h2>

            <p>
              The follow graph tells you who someone chose to listen to. It doesn&rsquo;t tell you what
              they actually think, write, or care about.
            </p>
            <p>
              This is where tweet labeling comes in. A human reads tweets and tags each one: what domain
              is this about? What community would recognize this as theirs? Each tag becomes a
              &ldquo;bit&rdquo; of evidence&mdash;a log-likelihood ratio measuring how much that tweet
              shifts the account toward or away from a community. Bits are additive: one tweet about
              meditation shifts you slightly toward Contemplative; fifty tweets shift you strongly.
            </p>

            <h3>Not all tweets carry equal weight</h3>
            <p>
              Each labeled tweet gets a simulacrum level (L1&ndash;L4) that affects how much community
              signal it carries:
            </p>
            <div className="about-signal-stack">
              <div className="about-signal-row">
                <span className="about-signal-name">L1 &mdash; sincere</span>
                <span className="about-signal-desc">&ldquo;I believe X about consciousness&rdquo; &mdash; reveals intellectual commitments</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">L2 &mdash; strategic</span>
                <span className="about-signal-desc">&ldquo;Here&rsquo;s why you should care about X&rdquo; &mdash; reveals what they promote</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">L3 &mdash; performative</span>
                <span className="about-signal-desc">In-group signaling, memes, shared references &mdash; <em>the</em> community marker</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">L4 &mdash; vibes</span>
                <span className="about-signal-desc">Shitposts, post-ironic &mdash; signals &ldquo;speaks the language&rdquo; but not which community</span>
              </div>
            </div>

            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                After labeling 51 tweets (683 tags, 213 bits across 6 communities):
              </p>
              <div className="about-before-after">
                <div className="about-before-after-col">
                  <div className="about-before-after-label">Graph prior (NMF with likes)</div>
                  <div className="about-bar-chart">
                    <div className="about-bar" style={{ width: '100%', background: '#39FF14' }}>
                      <span>LLM Whisperers 52%</span>
                    </div>
                    <div className="about-bar" style={{ width: '31%', background: '#FF00FF' }}>
                      <span>AI Creatives 16%</span>
                    </div>
                    <div className="about-bar" style={{ width: '29%', background: '#FF69B4' }}>
                      <span>Queer TPOT 15%</span>
                    </div>
                  </div>
                </div>
                <div className="about-before-after-col">
                  <div className="about-before-after-label">After tweet labeling (bits)</div>
                  <div className="about-bar-chart">
                    <div className="about-bar" style={{ width: '78.8%', background: '#39FF14' }}>
                      <span>LLM Whisperers 39%</span>
                    </div>
                    <div className="about-bar" style={{ width: '64.8%', background: '#9b59b6' }}>
                      <span>Qualia Research 32%</span>
                    </div>
                    <div className="about-bar" style={{ width: '32%', background: '#e74c3c' }}>
                      <span>AI Safety 16%</span>
                    </div>
                    <div className="about-bar" style={{ width: '19.8%', background: '#2ecc71' }}>
                      <span>Contemplative 10%</span>
                    </div>
                  </div>
                </div>
              </div>
              <p className="about-caveat">
                The correction didn&rsquo;t throw out the graph&mdash;it refined it. They genuinely
                orbit Qualia Research (their follows prove it), but their active intellectual work lives
                in LLM Whisperers. Tweet labeling is currently experimental&mdash;applied to a
                handful of accounts.
              </p>
            </div>
          </section>

          {/* Stage 5: How Confidence Spreads */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">5</span>
              How Confidence Spreads
              <span className="about-badge-status about-badge-status--live">LIVE</span>
            </h2>

            <p>
              NMF + tweet labeling classifies {classifiedStr} seed accounts well. But what about the
              other 182,000 in the follow graph?
            </p>
            <p>
              Label propagation uses the graph itself. Start with classified &ldquo;seed&rdquo;
              accounts. Their community labels spread outward through follow edges&mdash;if you
              follow 10 people and 8 of them are Builders, you&rsquo;re probably Builder-adjacent.
              The math is a harmonic function on the graph Laplacian, but the intuition is simple:
              you are the company you keep.
            </p>
            <p>
              Not everyone gets a confident placement. Accounts close to many seeds in the same
              community get strong colors. Accounts at community boundaries or far from any seed
              stay gray&mdash;we&rsquo;d rather say &ldquo;we&rsquo;re not sure&rdquo; than
              guess wrong. <strong>That restraint is why grayscale cards exist.</strong>
            </p>

            <details className="about-disclosure">
              <summary>The math: harmonic label propagation</summary>
              <div className="about-disclosure-body">
                <p>
                  Partition nodes into labeled (<em>L</em>) and unlabeled (<em>U</em>) sets.
                  The harmonic solution:
                </p>
                <p className="about-formula">
                  <em>f</em><sub>U</sub> = &minus;<em>L</em><sub>UU</sub><sup>&minus;1</sup>
                  &middot; <em>L</em><sub>UL</sub> &middot; <em>f</em><sub>L</sub>
                </p>
                <p>
                  To prevent large communities from overwhelming small ones, seeds are reweighted
                  by inverse square root of class size (1/&radic;<em>n</em><sub>c</sub>). Solved
                  iteratively via conjugate gradient. Entropy <em>H</em> = &minus;&Sigma;<em>p</em><sub>c</sub>
                  &middot;log(<em>p</em><sub>c</sub>) measures placement uncertainty.
                </p>
              </div>
            </details>

            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                As a seed account, their labels propagate outward. Accounts that follow them and other
                LLM Whisperers pick up that signal. An account 3 hops away from any seed gets a
                faint, uncertain placement&mdash;if it gets one at all.
              </p>
            </div>
          </section>

          {/* Stage 6: How We Validate — Three Independent Signals */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">6</span>
              How We Validate
              <span className="about-badge-status about-badge-status--live">LIVE</span>
            </h2>
            <p>
              A community that only shows up in one signal could be an artifact. A community
              confirmed by <strong>three independent methods</strong> is real.
            </p>

            <h3>Three-signal convergence</h3>
            <p>
              We validate each community against three orthogonal signals:
            </p>
            <div className="about-signal-stack">
              <div className="about-signal-row">
                <span className="about-signal-name">Graph structure (NMF)</span>
                <span className="about-signal-desc">Who follows whom &mdash; social structure</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Content vectors (CT1)</span>
                <span className="about-signal-desc">What people like reading &mdash; 25 topics from 17.5M liked tweets</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Co-followed topology (CF1)</span>
                <span className="about-signal-desc">Who is followed by the same people &mdash; social consensus</span>
              </div>
            </div>
            <p>
              <strong>12 of 15 communities</strong> are validated by all three signals.
              The graph says they cluster, the content says they read the same things,
              and the topology says the broader network agrees they belong together.
              The remaining 3 are validated by 2 of 3 signals&mdash;real communities, but
              with weaker independent confirmation.
            </p>

            <h3>Holdout recall</h3>
            <p>
              We collected 389 accounts from two independent TPOT directories (the Strangest Loop
              directory and the Orange TPOT Substack directory)&mdash;none were used to build the
              map. Then we check: does the pipeline find them?
            </p>

            <div className="about-recall-table">
              <h3>Pipeline reach</h3>
              <table>
                <thead>
                  <tr>
                    <th>Layer</th>
                    <th>Accounts</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Exemplar (seed accounts)</td>
                    <td>{classifiedStr}</td>
                    <td>Full archive data, NMF community assignment</td>
                  </tr>
                  <tr>
                    <td>Specialist + Bridge + Frontier</td>
                    <td>{((byBand.specialist || 0) + (byBand.bridge || 0) + (byBand.frontier || 0)).toLocaleString()}</td>
                    <td>Inferred from 190K-node engagement-weighted graph</td>
                  </tr>
                  <tr>
                    <td>Faint (low confidence)</td>
                    <td>{(byBand.faint || 0).toLocaleString()}</td>
                    <td>In the graph but below confidence threshold — searchable, grayscale</td>
                  </tr>
                  <tr>
                    <td>Holdout directory accounts in graph</td>
                    <td>118 / 217</td>
                    <td>99 are not in the follow graph (need API enrichment)</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3>Bootstrap cross-validation</h3>
            <p>
              To test generalization, we run bootstrap CV: hold out 20% of seed accounts,
              propagate from the remaining 80%, and measure how many held-out accounts
              are rediscovered. Across 5 iterations:
            </p>
            <div className="about-recall-table">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Recall</th>
                    <th>What it measures</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Held-out seed accounts</td>
                    <td><strong>83.8% &plusmn; 5.0%</strong></td>
                    <td>Remove 20% of seeds &mdash; propagation still finds most of them</td>
                  </tr>
                  <tr>
                    <td>Directory-only accounts</td>
                    <td><strong>94.6% &plusmn; 0.4%</strong></td>
                    <td>Accounts from independent TPOT directories, never used as seeds</td>
                  </tr>
                  <tr>
                    <td>Combined</td>
                    <td><strong>93.3% &plusmn; 0.7%</strong></td>
                    <td>Overall TPOT discovery rate for accounts in the follow graph</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p>
              The bottleneck is <strong>graph coverage, not propagation quality</strong>.
              For accounts reachable in the follow graph, propagation finds 94% of
              independently-verified TPOT members. The 99 directory accounts outside
              the graph need API enrichment to bring their edges in.
            </p>
            <p>
              Bridge accounts are not failures. @vgr (followed by 117 seeds across all
              communities) genuinely straddles everything&mdash;they&rsquo;re pan-TPOT. The
              system preserves their full membership distribution rather than forcing them
              into a single bucket.
            </p>
            <p className="about-caveat">
              These numbers are a snapshot. The point isn&rsquo;t perfection&mdash;it&rsquo;s
              honest measurement so we know what works and what doesn&rsquo;t.
            </p>

            <div className="about-running-example">
              <div className="about-running-example-label">Running example: @repligate</div>
              <p>
                They&rsquo;re found at every stage&mdash;they&rsquo;re one of the {classifiedStr}.
                Their content profile (32% LLM-tinkering, 15% philosophy, 15% highbies social) aligns
                with their graph community (52% LLM Whisperers). When graph and content agree,
                confidence is high.
              </p>
            </div>
          </section>
        </>
      )}

      {/* ════════════════════════════════════════════════ */}
      {/* SHARED SECTIONS (all paths converge here)       */}
      {/* ════════════════════════════════════════════════ */}
      {path && (
        <>
          <hr className="about-divider" />

          {/* What Your Card Means */}
          <section className="about-section">
            <h2>What Your Card Means</h2>

            <p>
              Your card encodes your community membership through its visual aesthetic&mdash;not
              through labels or bar charts. Each community has a signature mascot, color palette,
              and elemental vibe. Your primary community dominates the lighting and composition.
              Secondary communities appear as subtle accents. The result is a card you can{' '}
              <em>feel</em> without decoding.
            </p>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Exemplar</span>
              <p>
                <strong>{classifiedStr} seed accounts.</strong> Full archive data analyzed&mdash;follow
                patterns, retweet targets, liked content. Rich tarot-style cards with community
                iconography woven into the art.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Specialist</span>
              <p>
                Clearly belongs to one community. Propagation from the follow graph gives a
                confident placement (&gt;30% in one community). Colorful card, strong visual identity.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--bridge">Bridge</span>
              <p>
                Genuinely straddles 2&ndash;3 communities. These accounts are valuable&mdash;they
                connect subcommunities. Their cards blend multiple community aesthetics. Being a
                bridge is not a classification failure; it&rsquo;s a social reality.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Frontier</span>
              <p>
                Uncertain placement&mdash;either too far from seeds, or followed by seeds from
                many communities. Grayscale card. These are candidates for exploration: follow
                a few frontier accounts and see if they resonate.
              </p>
            </div>

            {showArchivePara && (
              <p>
                Want a richer card? Contribute your data via the{' '}
                <a href={links.community_archive} target="_blank" rel="noopener noreferrer">
                  community archive
                </a>
                , or{' '}
                <a href={links.curator_dm} target="_blank" rel="noopener noreferrer">
                  DM the curator
                </a>
                .
              </p>
            )}
          </section>

          {/* This Is One Map, Not The Map */}
          <section className="about-section">
            <h2>This Is One Map, Not <em>The</em> Map</h2>

            <p>
              This map starts from <strong>my perspective</strong>&mdash;the ~300 accounts I follow,
              the communities I recognize, the boundaries I drew. It&rsquo;s not the objective
              structure of TPOT. It&rsquo;s Aditya&rsquo;s TPOT.
            </p>
            <p>
              Someone following different people would see different communities. A contemplative
              practitioner would draw the meditation scene at higher resolution&mdash;maybe splitting
              &ldquo;Jhana Practitioners&rdquo; into jhana technicians, somatic healers, and nondual
              teachers. A builder would see more granularity in the infrastructure scene. The map
              reflects the mapper.
            </p>
            <p>
              Not every account that contributed data to the{' '}
              <a href="https://www.community-archive.org/" target="_blank" rel="noopener noreferrer">
                community archive
              </a>{' '}
              is TPOT. Uploading your data is a generous act of transparency, not a membership card.
              Some contributors orbit the scene, some study it from outside, some are in adjacent
              networks entirely. The pipeline filters for this: accounts whose follow patterns
              don&rsquo;t concentrate in any community propagate with lower confidence.
            </p>
            <p>
              The honest thing is to say so. This is a map drawn from a particular vantage point,
              with particular blind spots, validated as well as we can against independent signals.
              If you see something wrong&mdash;someone in the wrong community, a community that
              should be split, a whole scene that&rsquo;s missing&mdash;that&rsquo;s signal.
              The map improves when you tell us.
            </p>
          </section>

          {/* The Visual Language */}
          <section className="about-section">
            <h2>The Visual Language</h2>

            <p>
              Each community has a visual identity&mdash;a mascot, a sigil, a color palette,
              an elemental vibe. These aren&rsquo;t decorative choices. They encode what makes
              each scene distinctive.
            </p>

            <div className="about-signal-stack">
              <div className="about-signal-row">
                <span className="about-signal-name">Jhana Practitioners</span>
                <span className="about-signal-desc">Lotus Serpent &middot; deep violet &middot; still water + inner radiance</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">LLM Whisperers</span>
                <span className="about-signal-desc">Recursive Wyrm &middot; toxic green &middot; digital fog + recursion</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Vibecamp Highbies</span>
                <span className="about-signal-desc">Laughing Bodhisattva &middot; burning gold &middot; sacred fire + holy chaos</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">NYC Builders</span>
                <span className="about-signal-desc">Cornerstone Titan &middot; concrete grey + crimson &middot; architecture + scaffolding</span>
              </div>
              <div className="about-signal-row">
                <span className="about-signal-name">Queer TPOT</span>
                <span className="about-signal-desc">Kaleidoscopic Chimera &middot; holographic shifting &middot; metamorphosis</span>
              </div>
            </div>

            <p>
              When you see a card with lotus borders and moonlight pools, that&rsquo;s not random&mdash;it
              means the account&rsquo;s primary community is the contemplative scene. Circuit patterns
              and glitch effects mean LLM Whisperers. Fractal blooms mean AI Creatives. The card
              is a portrait of where someone lives in the network, rendered as mythology.
            </p>
            <p>
              Community fractions become <strong>art direction weights</strong>. An account that&rsquo;s
              45% Jhana + 30% Core TPOT + 15% LLM Whisperers gets a card dominated by moonlight-violet,
              with star-dust accents and faint circuit traces. You feel it before you decode it.
            </p>
            <p>
              Visit any <a href="/?community=jhana-practitioners">community page</a> to
              see the full iconography&mdash;mascot, sigil, flag, palette, and how it shapes the cards.
            </p>
          </section>

          {/* Open Source */}
          <section className="about-section about-cta">
            <h2>Build Your Own Map</h2>
            <p>
              The entire pipeline&mdash;graph construction, NMF classification, content vectors,
              label propagation, seed validation, curation tooling, and this site&mdash;is open
              source. The pipeline is general; the seeds are specific.
            </p>
            <p>
              You can clone the repo, bring your own follow data, choose your own seed accounts,
              and build a community map from <em>your</em> perspective. Your map would have different
              communities, different boundaries, different blind spots. That&rsquo;s the point&mdash;the
              internet has as many maps as it has mappers.
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
            <a href="/" className="about-back" onClick={(e) => { e.preventDefault(); onNavigate ? onNavigate('/') : window.history.back() }}>
              &larr; Back to {siteName}
            </a>
          </div>
        </>
      )}
    </div>
  )
}
