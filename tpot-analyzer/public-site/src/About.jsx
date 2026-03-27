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
              You understand TPOT&rsquo;s language. You&rsquo;re in because you recognize it.
              The shared references, the nested irony, the way people hold ideas here&mdash;it&rsquo;s
              a membrane. People who know, know. People who don&rsquo;t, can&rsquo;t
              participate until they do.
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
              Twitter?&rdquo; &ldquo;Who should I follow for jhanas?&rdquo; &ldquo;What about
              Ayurveda, somatic therapy, Kegan stages?&rdquo; &ldquo;What about farming, embodied
              living, beautiful cartography?&rdquo; &ldquo;Who&rsquo;s in my city that&rsquo;s
              like me?&rdquo;
            </p>
            <p>
              I know the answers. Richard Ngo is in agent foundations. @repligate is in cyborgism.
              I know specific people at specific niche corners of AI safety, meditation, and
              everything in between. But it&rsquo;s trapped in my head. Not legible.
              Doesn&rsquo;t scale.
            </p>
            <p>
              People need this map to find each other&mdash;to collaborate, to build projects,
              to start communities around shared interests.
            </p>
          </section>

          <section className="about-section">
            <h2>Make the Structure Visible</h2>
            <p>
              Rather than let an algorithm decide whose tweets you see, this site makes the
              community structure visible. It&rsquo;s one version of the map. Not <em>the</em> map.
            </p>
            <p>
              The whole thing is open source. Fork the repo, feed in your own follow data,
              label tweets by your own aesthetics, carve out your own ontology&mdash;and
              discover others you can work with.
            </p>
          </section>

          <section className="about-section about-origin">
            <h2>My Story</h2>
            <p>
              I followed around 2,000 people on Twitter. My feed was a firehose&mdash;brilliant
              posts buried under noise from people I&rsquo;d followed in a different season
              of my life. Lists were too manual. Follow/unfollow felt like a false dichotomy.
            </p>
            <p>
              The real problem: TPOT isn&rsquo;t one thing. It&rsquo;s{' '}
              {numCommunities} overlapping subcultures, each with its own references, aesthetics,
              and epistemic norms. Some I&rsquo;m deeply embedded in. Others I just orbit.
              I wanted to see the map.
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
              Not a hashtag. Not a list. Not an organization. It&rsquo;s tens of thousands
              of accounts that share references, aesthetics, and ways of thinking. People
              call it TPOT&mdash;&ldquo;this part of Twitter.&rdquo;
            </p>
            <p>
              You&rsquo;re &ldquo;in&rdquo; if you understand the language. That sounds circular,
              and it is. The nested irony, the philosophical shitposts, the way people hold
              ideas loosely while caring deeply&mdash;that&rsquo;s the boundary. It&rsquo;s
              hard to see from outside because it&rsquo;s not trying to be seen.
            </p>
          </section>

          <section className="about-section">
            <h2>It&rsquo;s Actually {numCommunities} Communities</h2>

            <p>
              Builders, contemplatives, poets, AI safety researchers, identity experimentalists,
              institution designers, embodiment practitioners, psychonauts, governance
              designers&mdash;overlapping but distinct.
            </p>
            <p>
              This site maps those subcommunities. Search your handle and see where you land.
              Browse a community to see who&rsquo;s in it. Follow a few accounts that match
              what you&rsquo;re curious about.
            </p>
          </section>

          <section className="about-section">
            <h2>How It Works (Short Version)</h2>
            <p>
              We look at who follows whom. Following a meditation teacher tells us more than
              following Elon Musk. An algorithm finds clusters of accounts with similar
              follow patterns. A human curator reviews and names each cluster.
            </p>
            <p>
              For accounts not in the core dataset, we infer placement from their position
              in the network&mdash;if most of your connections are Builders, you&rsquo;re
              probably Builder-adjacent. Inferred placements get a grayscale card instead
              of a colorful one, signaling lower confidence.
            </p>
          </section>
        </>
      )}

      {/* ════════════════════════════════════════════════ */}
      {/* PATH C: "I want to be inspired by your math"    */}
      {/* ════════════════════════════════════════════════ */}
      {path === 'c' && (
        <>
          {/* Stage 1: The Raw Material */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">1</span>
              The Raw Material
            </h2>

            <p>
              The{' '}
              <a href="https://www.community-archive.org/" target="_blank" rel="noopener noreferrer">
                Community Archive
              </a>{' '}
              is a project where Twitter users voluntarily share their data. {classifiedStr} people
              shared who they follow, who they retweet, and their tweets. That&rsquo;s the seed.
            </p>
            <p>
              From those {classifiedStr}, we can trace outward to around 200,000 accounts in
              their follow graph. For the archived accounts we see everything. For the other 200K
              we only know that <em>someone</em> follows them. It&rsquo;s like knowing which
              lectures a student attends, but not what the professors do on weekends.
            </p>
            <p>
              Take @repligate. They shared their data, so we can see all ~1,200 accounts they
              follow and all their retweets. For those 1,200 accounts, we only know @repligate
              follows them. The result is a giant matrix that&rsquo;s almost entirely
              empty&mdash;about 0.3% filled. That sparsity is the raw material.
            </p>
          </section>

          {/* Stage 2: Reading the Signals */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">2</span>
              Reading the Signals
            </h2>
            <p>
              Who you follow is the strongest signal. It&rsquo;s deliberate, stable, and reveals
              what you chose to listen to. But a person is more than their follow list.
            </p>
            <p>
              What you retweet shows what you amplify. What you like shows what catches your eye.
              Who replies to your posts&mdash;and whether you liked their reply&mdash;hints at who
              you&rsquo;re in conversation with. Each signal has a different shape. Follows
              are architectural. Retweets are behavioral. Likes are reflexive. Replies are relational.
            </p>
            <p>
              Then there are patterns that emerge from the whole network at once. If 200
              people all follow both you and the same niche consciousness researcher, that&rsquo;s
              not coincidence&mdash;that&rsquo;s structure. We also run topic models over 17.5 million
              liked tweets to build an entirely different picture: not who you listen to, but
              what you read about.
            </p>
            <p>
              The interesting cases are where these signals disagree. @repligate&rsquo;s follow
              list says &ldquo;Qualia Research&rdquo;&mdash;they follow consciousness researchers,
              QRI people. But their liked content says &ldquo;LLM Whisperers&rdquo;&mdash;AI agents,
              prompt engineering, recursive self-improvement. That disagreement is the most informative
              thing in the data. It means @repligate orbits one community but intellectually lives
              in another. You need both signals to see that.
            </p>
          </section>

          {/* Stage 3: Finding the Communities */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">3</span>
              Finding the Communities
            </h2>

            <p>
              Not all follows are equal. Following a niche consciousness researcher separates
              communities. Following Elon Musk doesn&rsquo;t. So rare, specific follows
              dominate the picture. Follows are primary. Retweets count at 0.6&times;. Likes
              at 0.4&times;.
            </p>
            <p>
              The core technique is matrix factorization. You have a giant sparse matrix of
              who-follows-whom. The algorithm decomposes it into two smaller matrices:
            </p>
            <p className="about-formula">
              <em>A</em> &asymp; <em>W</em> &middot; <em>H</em>
            </p>
            <p>
              <em>W</em> tells you each account&rsquo;s community mixture. <em>H</em> tells you what
              defines each community&mdash;which follow targets, which retweet targets. That
              second matrix is crucial: you can look at a cluster and see <em>why</em> it
              exists, which is what makes human naming possible.
            </p>
            <p>
              Crucially, these memberships don&rsquo;t sum to one. You can be 80% Builders
              and 60% Contemplative at the same time. Real people belong to multiple scenes.
            </p>
            <p>
              We tested 12, 14, and 16 communities on the same data. At 16, 14 of the communities
              matched the 14-factor run (91% overlap), plus two clean splits where tech-intellectuals
              and creatives each resolved into finer subcommunities. We use 16 because those splits
              are meaningful and the structure is the most stable across random restarts.
            </p>
            <p>
              The {numCommunities} factors come out as anonymous math&mdash;&ldquo;Factor
              7&rdquo; means nothing. A curator reviews the top accounts and top follow targets
              in each factor and names them: &ldquo;these people all follow the same meditation
              teachers and consciousness researchers&rdquo; becomes Contemplative Practitioners.
            </p>
            <p>
              For @repligate, the result: <strong>52% LLM Whisperers, 16% AI
              Creatives, 15% Queer TPOT.</strong> A follow-only analysis had said 100% Qualia
              Research. Adding likes and retweets revealed the LLM tinkering identity that
              follows alone couldn&rsquo;t see. This is the starting picture. Tweet labeling
              refines it further.
            </p>
          </section>

          {/* Stage 4: Correcting the Map */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">4</span>
              Correcting the Map
              <span className="about-badge-status about-badge-status--experimental">EXPERIMENTAL</span>
            </h2>

            <p>
              The follow graph tells you who someone listens to. It doesn&rsquo;t tell you what
              they actually think, write, or care about. For that, you have to read their tweets.
            </p>
            <p>
              Three AI models independently read each tweet and tag it: what community would
              claim this? We only keep tags where at least two agree. Each agreement becomes
              a small piece of evidence. One tweet about meditation is a nudge. Fifty tweets
              is a shove. The evidence accumulates, and it can be reversed if later tweets point
              elsewhere.
            </p>
            <p>
              AI misses things humans see. A tweet that&rsquo;s just a link gives it nothing
              to work with. An image-heavy thread carries meaning it can&rsquo;t read. So a
              human opens each labeled tweet, checks the full context&mdash;images, quoted tweets,
              who&rsquo;s replying&mdash;and corrects mistakes. Of 57 tweets checked this way,
              33 needed corrections. The most common error: the AI guessed based on who the
              person <em>is</em>, not what the tweet <em>says</em>.
            </p>
            <p>
              Not all tweets carry equal weight. A sincere statement of belief reveals
              intellectual commitments. A strategic argument reveals what someone promotes.
              But the strongest community signal comes from performative tweets&mdash;in-group
              memes, shared references, the specific jokes only your people would get. These
              count double, because they&rsquo;re the purest expression of belonging.
            </p>
            <p>
              After labeling 51 of @repligate&rsquo;s tweets, the picture shifts:
            </p>
            <div className="about-before-after">
              <div className="about-before-after-col">
                <div className="about-before-after-label">Before (graph only)</div>
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
                <div className="about-before-after-label">After (graph + tweets)</div>
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
            <p>
              The tweets didn&rsquo;t throw out the graph&mdash;they refined it. @repligate
              genuinely orbits Qualia Research (their follows prove it), but their active
              intellectual work lives in LLM Whisperers. The correction preserves both truths.
            </p>
          </section>

          {/* Stage 5: Spreading Outward */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">5</span>
              Spreading Outward
            </h2>

            <p>
              The {classifiedStr} seed accounts are well-classified. But what about
              the other ~200,000 accounts in the network?
            </p>
            <p>
              Community labels spread outward through follow connections. If you follow 10
              people and 8 of them are Builders, you&rsquo;re probably Builder-adjacent.
              The intuition is simple: you are the company you keep.
            </p>
            <p>
              Each community spreads independently. Your connection to Qualia Research has
              nothing to do with your connection to LLM Whisperers. This matters because
              real people belong to multiple scenes. Someone followed by 12 Qualia researchers
              and 8 LLM tinkerers scores high in both&mdash;they&rsquo;re a bridge, not a
              classification failure.
            </p>
            <p>
              To separate real connections from noise, we count: how many classified accounts
              actually follow you, per community? An account followed by people from two
              different communities is a genuine bridge. An account with one random connection
              is noise&mdash;@googlecalendar doesn&rsquo;t show up even though it&rsquo;s
              technically in the network.
            </p>
            <p>
              Not everyone gets a confident placement. Accounts close to many classified
              accounts get strong colors. Accounts far from anyone classified stay
              gray&mdash;we&rsquo;d rather say &ldquo;we&rsquo;re not sure&rdquo; than
              guess wrong. <strong>That restraint is why grayscale cards exist.</strong> The
              map currently shows {(byBand.bridge || 0).toLocaleString()} bridge accounts
              connecting different scenes.
            </p>
          </section>

          {/* Stage 5.5: Honest Uncertainties */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">&#x26A0;</span>
              What We Don&rsquo;t Know
            </h2>

            <p>
              Every map has blind spots. Here are ours, honestly stated.
            </p>

            <h3>Archive bias</h3>
            <p>
              The seed accounts are people who voluntarily uploaded their Twitter data. That&rsquo;s
              not random&mdash;it skews toward people who are technically literate, EA-adjacent,
              and comfortable sharing data publicly. Communities where people value privacy
              (somatic practitioners, some queer scenes) are underrepresented. The map sees
              what the seeds can reach.
            </p>

            <h3>Temporal freeze</h3>
            <p>
              Follow patterns change. Someone who followed AI safety accounts in 2023 might
              have pivoted to contemplative practice by 2026. The archive is a snapshot, not a
              stream. Reading recent tweets partially compensates, but the underlying graph
              structure is largely frozen.
            </p>

            <h3>This is Aditya&rsquo;s map, not <em>the</em> map</h3>
            <p>
              These {numCommunities} communities are one person&rsquo;s reading of the
              landscape. Where I see &ldquo;Jhana Practitioners&rdquo; and &ldquo;Contemplative
              Practitioners&rdquo; as distinct, you might see one community. Where I
              see one &ldquo;Core TPOT,&rdquo; you might see three. The algorithm finds
              clusters; the naming and boundary-drawing is editorial&mdash;mine.
            </p>
            <p>
              If this doesn&rsquo;t match your experience, that&rsquo;s not a bug. The{' '}
              <a href={links.repo} target="_blank" rel="noopener noreferrer">
                entire pipeline is open source
              </a>
              . Fork it, bring your own follow data, label tweets by your own aesthetics,
              and you&rsquo;ll get a different map. Different seeds, different communities,
              different blind spots.
            </p>

            <h3>Confidence decays with distance</h3>
            <p>
              The further you are from a classified account in the network, the weaker
              the signal. One connection away is strong. Two is useful. Three or more is
              mostly noise. With {classifiedStr} classified accounts in a 200K-node network,
              most accounts are far from anyone classified. Their placements are faint not
              because they&rsquo;re not TPOT, but because the network is too sparse to carry
              signal that far.
            </p>

            <h3>AI labeling makes mistakes</h3>
            <p>
              The AI reads tweets and guesses communities, but it gets around 30% wrong on
              the first pass. It confuses mentioning a tool with being part of that
              tool&rsquo;s community. It can&rsquo;t see images. It attributes retweet
              content to the person who retweeted. A human spot-checks every batch, but
              verification is ongoing.
            </p>

            <h3>What we&rsquo;re doing about it</h3>
            <p>
              The system continuously improves: find accounts we&rsquo;re uncertain about,
              read their tweets, classify them, check the results, update the map,
              measure how much better we got. Each round adds more classified accounts
              and corrects prior mistakes. The numbers on this page update with each round.
            </p>
          </section>

          {/* Stage 6: How We Know It Works */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">6</span>
              How We Know It Works
            </h2>
            <p>
              A community that only shows up in one signal could be an artifact. A community
              confirmed by three independent methods is real.
            </p>
            <p>
              We check each community against three signals that have nothing to do with each
              other: the follow graph (who follows whom), topic models (what people like
              reading), and co-followed structure (who gets followed by the same people).{' '}
              <strong>12 of 15 communities</strong> are confirmed by all three. The remaining
              3 are confirmed by two&mdash;real communities, but with weaker independent evidence.
            </p>
            <p>
              We also re-ran the entire analysis on a graph with 85% more data (815K edges
              vs 441K). The same communities emerged. 11 of 16 matched strongly; the other 5
              showed minor boundary shifts. If the communities were an artifact of sparse data,
              doubling the data would have destroyed them. It didn&rsquo;t.
            </p>

            <h3>Testing against known lists</h3>
            <p>
              We test against 1,822 accounts from four independent lists of known TPOT
              accounts&mdash;none of which were used to build the map. The honest question:
              of accounts that are known TPOT and reachable in our network, how many does
              the map find?
            </p>

            <div className="about-recall-table">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Found (in network)</th>
                    <th>Found (total)</th>
                    <th>Not in network</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Accounts on 3+ lists</td>
                    <td><strong>65%</strong></td>
                    <td>65%</td>
                    <td>0%</td>
                  </tr>
                  <tr>
                    <td><a href="https://strangestloop.io/a-tpot-directory" target="_blank" rel="noopener noreferrer">Strangest Loop directory</a></td>
                    <td><strong>64%</strong></td>
                    <td>52%</td>
                    <td>19%</td>
                  </tr>
                  <tr>
                    <td><a href="https://tyleralterman.notion.site/Orange-TPOT-tpot-on-substack-2f0ff954ab4980fa9f26f8441870350d" target="_blank" rel="noopener noreferrer">Orange TPOT directory</a></td>
                    <td><strong>54%</strong></td>
                    <td>33%</td>
                    <td>39%</td>
                  </tr>
                  <tr>
                    <td>Accounts on 2+ lists</td>
                    <td><strong>43%</strong></td>
                    <td>42%</td>
                    <td>1%</td>
                  </tr>
                  <tr>
                    <td><a href="https://x.com/i/lists/1788441465326064008" target="_blank" rel="noopener noreferrer">Aditya&rsquo;s watchlist</a> (219 accounts)</td>
                    <td>31%</td>
                    <td>30%</td>
                    <td>4%</td>
                  </tr>
                  <tr>
                    <td><a href="https://x.com/adityaarpitha/following" target="_blank" rel="noopener noreferrer">Aditya&rsquo;s follows</a> (~1,400 accounts)</td>
                    <td>30%</td>
                    <td>30%</td>
                    <td>0%</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p>
              The more curated the source, the higher the recall. Accounts confirmed
              by 3+ independent sources are found 65% of the time. Aditya&rsquo;s raw
              follow list has low recall because most follows are mainstream accounts that
              aren&rsquo;t TPOT&mdash;the denominator is inflated.
            </p>
            <p>
              Two bottlenecks limit recall: <strong>graph coverage</strong> (39% of Orange
              directory accounts aren&rsquo;t reachable in our network yet) and{' '}
              <strong>classified density</strong> ({classifiedStr} classified accounts in
              a 200K-node graph means each seed covers ~600 nodes). Each round of improvement
              adds more classified accounts and pushes recall up.
            </p>

            <div className="about-recall-table">
              <table>
                <thead>
                  <tr>
                    <th>Current state</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Exemplar (seed accounts)</td>
                    <td>{classifiedStr}</td>
                  </tr>
                  <tr>
                    <td>Specialist + Bridge + Frontier</td>
                    <td>{((byBand.specialist || 0) + (byBand.bridge || 0) + (byBand.frontier || 0)).toLocaleString()}</td>
                  </tr>
                  <tr>
                    <td>Faint (low confidence)</td>
                    <td>{(byBand.faint || 0).toLocaleString()}</td>
                  </tr>
                  <tr>
                    <td>Total searchable</td>
                    <td>{totalStr}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p>
              These numbers are a snapshot. The point isn&rsquo;t perfection&mdash;it&rsquo;s
              honest measurement so we know what works and what doesn&rsquo;t.
            </p>
          </section>

          {/* Stage 7: The Veil of Ignorance */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">7</span>
              The Veil of Ignorance
            </h2>

            <p>
              The hardest question about any map isn&rsquo;t &ldquo;does it look right?&rdquo;
              It&rsquo;s: <strong>would it still find the territory if you hid the landmarks?</strong>
            </p>
            <p>
              So we ran the experiment. Take a known TPOT account. Remove them from the seed
              set. Propagate the entire network without them. Then ask: does the system rediscover
              them from the structure alone?
            </p>
            <p>
              The answer is yes&mdash;with near-perfect accuracy. Across five cross-validation
              folds, the seed-neighbor signal (how many classified accounts follow you) recovers
              held-out TPOT accounts with an AUC of 0.999. That&rsquo;s not a typo. The system
              finds hidden TPOT accounts 100% of the time at a 5% false positive rate. A held-out
              TPOT member has a median of 65 seed neighbors; a random non-TPOT account has 1.
            </p>
            <p>
              Raw propagation scores, by contrast, are useless&mdash;AUC 0.225, worse than a coin
              flip. TPOT accounts actually score <em>lower</em> than random noise because hub
              nodes near many communities inherit diffuse signal. The math works, but only if you
              measure the right thing: not &ldquo;how much signal reached you,&rdquo; but
              &ldquo;how many community members specifically follow you.&rdquo;
            </p>

            <h3>The 17 skeleton keys</h3>
            <p>
              Here&rsquo;s where it gets interesting. We sorted all {classifiedStr} seeds by
              connectivity&mdash;how many other seeds are their neighbors&mdash;and asked: how
              few accounts do you need to find most of TPOT?
            </p>
            <p>
              <strong>17 accounts.</strong> The top 5% of seeds, by neighbor count, are sufficient
              to locate 81% of every independently-verified TPOT account in the network. Adding
              the other 95% of seeds only pushes recall from 81% to 87%. The network has a
              backbone, and it&rsquo;s remarkably small.
            </p>
            <p>
              Those 17 accounts span most communities: contemplative practitioners, highbies,
              internet essayists, AI safety, builders, creatives. They&rsquo;re the people who
              bridge scenes&mdash;not specialists, but connectors. If you wanted to reconstruct
              TPOT from scratch, you&rsquo;d start with them.
            </p>

            <h3>Communities survive deletion</h3>
            <p>
              The strongest test: remove an <em>entire community</em>. Delete every seed labeled
              Jhana Practitioners&mdash;all 67 of them. Propagate from the remaining 14 communities.
              Can seeds from other communities still find the Jhana people?
            </p>
            <p>
              <strong>Yes. Every single one.</strong> 100% recall, from communities that share no
              labels with them. Contemplative Practitioners and Highbies&mdash;the connective
              tissue of TPOT&mdash;reach into Jhana&rsquo;s neighborhood because the follow
              patterns overlap enough.
            </p>
            <p>
              Every community survives full deletion. The weakest is TfT-Coordination at 86%&mdash;the
              most insular group, with the fewest cross-community connections. The three most
              resilient communities&mdash;Contemplative Practitioners, Highbies, and Core
              TPOT&mdash;act as universal connectors. They appear in the top-3 recovery sources
              for every other community. They are, in a structural sense, the fabric that holds
              TPOT together.
            </p>
            <p>
              This isn&rsquo;t circular. The communities weren&rsquo;t drawn to survive this test.
              They were drawn to match follow patterns. The fact that they <em>also</em> survive
              deletion means the structure is real. The graph knows about these communities
              independently of our labeling. We named what was already there.
            </p>
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
              Your card doesn&rsquo;t label your communities&mdash;it embodies them. Each
              community has a signature mascot, palette, and elemental vibe. Your primary
              community dominates the composition. Secondary communities appear as accents.
              The result is a card you can <em>feel</em> without decoding.
            </p>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Exemplar</span>
              <p>
                <strong>{classifiedStr} seed accounts.</strong> Full archive data&mdash;follows,
                retweets, liked content. Rich tarot-style cards with community iconography
                woven into the art.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Specialist</span>
              <p>
                Clearly belongs to one community. Confident graph placement. Colorful card,
                strong visual identity.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--bridge">Bridge</span>
              <p>
                Straddles 2&ndash;3 communities. These accounts connect subcommunities&mdash;their
                cards blend multiple aesthetics. Being a bridge is not a classification failure.
                It&rsquo;s a social reality.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Frontier</span>
              <p>
                Uncertain placement&mdash;too far from seeds, or pulled by many communities
                at once. Grayscale card. Candidates for exploration.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Faint</span>
              <p>
                Barely visible in the network. Present in the graph but below the confidence
                threshold. Searchable, but the card is dim&mdash;a whisper, not a statement.
              </p>
            </div>

            {showArchivePara && (
              <p>
                Want a richer card?{' '}
                <a href={links.community_archive} target="_blank" rel="noopener noreferrer">
                  Contribute to the archive
                </a>
                {' '}or{' '}
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
              This map starts from <strong>my perspective</strong>&mdash;the ~1,400 accounts I follow,
              the {classifiedStr} seeds I&rsquo;ve helped classify, the boundaries I drew. It&rsquo;s
              Aditya&rsquo;s TPOT.
            </p>
            <p>
              Someone following different people would see different communities. A contemplative
              practitioner would draw the meditation scene at higher resolution&mdash;splitting
              &ldquo;Jhana Practitioners&rdquo; into jhana technicians, somatic healers, and nondual
              teachers. A builder would see more granularity in the infrastructure scene. The map
              reflects the mapper.
            </p>
            <p>
              Not every account in the{' '}
              <a href="https://www.community-archive.org/" target="_blank" rel="noopener noreferrer">
                community archive
              </a>{' '}
              is TPOT. Uploading your data is a generous act of transparency, not a membership card.
              The pipeline filters for this: accounts whose follow patterns don&rsquo;t concentrate
              in any community propagate with lower confidence.
            </p>
            <p>
              If you see something wrong&mdash;someone in the wrong community, a community that
              should be split, a whole scene that&rsquo;s missing&mdash;that&rsquo;s signal.
              The map improves when you tell us.
            </p>
          </section>

          {/* The Visual Language */}
          <section className="about-section">
            <h2>The Visual Language</h2>

            <p>
              Each community has a visual identity&mdash;not as decoration, but as encoding.
              Jhana Practitioners get lotus serpents and deep violet, still water and inner
              radiance. LLM Whisperers get recursive wyrms in toxic green, digital fog and
              glitch. Vibecamp Highbies get laughing bodhisattvas in burning gold. NYC Builders
              get concrete and crimson. Queer TPOT gets a kaleidoscopic chimera, holographic
              and shifting.
            </p>
            <p>
              When you see lotus borders and moonlight pools on a card, that&rsquo;s not
              random&mdash;it means the contemplative scene. Circuit patterns mean LLM Whisperers.
              Fractal blooms mean AI Creatives. The card is a portrait of where someone lives
              in the network, rendered as mythology.
            </p>
            <p>
              An account that&rsquo;s 45% Jhana, 30% Core TPOT, 15% LLM Whisperers gets a
              card dominated by moonlight-violet, with star-dust accents and faint circuit
              traces. You feel it before you decode it.
            </p>
            <p>
              Visit any <a href="/?community=jhana-practitioners">community page</a> to
              see the full iconography.
            </p>
          </section>

          {/* Open Source */}
          <section className="about-section about-cta">
            <h2>Build Your Own Map</h2>
            <p>
              The entire pipeline is open source&mdash;from graph construction to this site.
              The pipeline is general. The seeds are specific.
            </p>
            <p>
              Clone the repo, bring your own follow data, choose your own seeds, and build
              a community map from <em>your</em> perspective. Different seeds, different
              communities, different blind spots. The internet has as many maps as it has
              mappers.
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
