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
              You understand TPOT&rsquo;s language. Recognizing the language grants entry.
              Shared references, nested irony, and the way people hold ideas form a membrane.
              The uninformed cannot participate.
            </p>
            <p>
              Illegibility protects the culture. However, coordination remains trapped in
              individual heads.
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
              I know that Richard Ngo works on agent foundations and @repligate explores cyborgism.
              I can navigate the niches of AI safety and meditation. But trapping this knowledge in
              my head prevents it from scaling.
            </p>
            <p>
              People need this map to find each other to collaborate, build projects, and start
              communities around shared interests.
            </p>
          </section>

          <section className="about-section">
            <h2>Make the Structure Visible</h2>
            <p>
              This site makes the community structure visible instead of letting an algorithm
              decide whose tweets you see. It presents one version of the map.
            </p>
            <p>
              The whole thing is open source. Fork the repo, feed in your own follow data,
              label tweets by your own aesthetics, carve out your own ontology, and discover
              others you can work with.
            </p>
          </section>

          <section className="about-section about-origin">
            <h2>My Story</h2>
            <p>
              I followed around 2,000 people on Twitter. My feed was a firehose. Brilliant
              posts lay buried under noise from people I followed in a different season
              of my life. Lists required too much manual effort, and follow/unfollow
              presented a false dichotomy.
            </p>
            <p>
              TPOT contains {numCommunities} overlapping subcultures. Each maintains its
              own references, aesthetics, and epistemic norms. I am deeply embedded in
              some and merely orbit others. I built this site to see the map.
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
              Tens of thousands of accounts share references, aesthetics, and ways of thinking.
              People call this network TPOT&mdash;&ldquo;this part of Twitter.&rdquo;
            </p>
            <p>
              Understanding the language grants entry. The nested irony, philosophical shitposts,
              and holding ideas loosely while caring deeply form the boundary. The network remains
              hidden from the outside because it avoids visibility.
            </p>
          </section>

          <section className="about-section">
            <h2>It&rsquo;s Actually {numCommunities} Communities</h2>

            <p>
              The network includes builders, contemplatives, poets, AI safety researchers,
              identity experimentalists, institution designers, embodiment practitioners,
              psychonauts, and governance designers. These groups overlap while remaining
              distinct.
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
              We analyze eight types of connections: who follows whom, who quotes whom, and who
              replies to whom. Each connection type carries different meaning. Following a meditation
              teacher tells us more than following Elon Musk. An algorithm finds clusters of
              accounts with similar connection patterns. A human curator reviews and names
              each cluster.
            </p>
            <p>
              Then we read tweets. Your social tribe and intellectual interests often point in
              different directions. This divergence makes the network interesting. We infer
              placement for accounts outside the core dataset based on their position in the
              network. Grayscale cards signal lower confidence for these inferred placements.
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
              is a project where Twitter users voluntarily share their tweets, follows,
              and likes. Around 330 people have done this so far. This archive contains millions
              of tweets and likes. It provides a detailed record of who these people chose
              to listen to.
            </p>
            <p>
              Each archived account follows hundreds or thousands of people. Tracing these
              connections outward reveals roughly 270,000 accounts in the shadow network.
              We see everything for the 330 archived accounts. For the 270,000 others, we
              only know that someone chose to follow them. They exist as faceless silhouettes
              in the graph.
            </p>
            <p>
              We selectively fetch data for the most connected shadow accounts via the Twitter API
              to fill in the picture. We retrieve their follows, recent tweets, and bios. We prioritize
              accounts that many archived people follow, or that sit at the intersection of multiple
              communities.
            </p>
            <p>
              The result is a combined graph of 2.7 million weighted connections across 298,000 accounts spanning eight
              relationship types.
            </p>
            <div className="about-recall-table">
              <table>
                <thead>
                  <tr>
                    <th>Edge Type</th>
                    <th>Count</th>
                    <th>Meaning</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Mention</td>
                    <td>1,882,155</td>
                    <td>Who you address</td>
                  </tr>
                  <tr>
                    <td>Follow</td>
                    <td>803,998</td>
                    <td>Who you listen to</td>
                  </tr>
                  <tr>
                    <td>Follower</td>
                    <td>533,749</td>
                    <td>Who listens to you</td>
                  </tr>
                  <tr>
                    <td>Quote</td>
                    <td>343,886</td>
                    <td>Who you publicly comment on</td>
                  </tr>
                  <tr>
                    <td>Co-followed</td>
                    <td>33,402</td>
                    <td>Accounts sharing an audience</td>
                  </tr>
                  <tr>
                    <td>Like</td>
                    <td>24,501</td>
                    <td>Endorsements</td>
                  </tr>
                  <tr>
                    <td>Reply</td>
                    <td>12,021</td>
                    <td>Direct conversations</td>
                  </tr>
                  <tr>
                    <td>Retweet</td>
                    <td>6,989</td>
                    <td>Audience amplification</td>
                  </tr>
                  <tr>
                    <td><strong>Total raw edges</strong></td>
                    <td><strong>3,640,701</strong></td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* Stage 2: Reading the Signals */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">2</span>
              Reading the Signals
            </h2>
            <p>
              Follows provide the strongest signal. They are deliberate and stable indicators of who
              you listen to. However, a person extends beyond their follow list.
            </p>
            <p>
              For the archived accounts, we also see what they retweet, what they like, and who
              replies to their posts. For enriched shadow accounts, we fetch their recent tweets
              and bios to see what they write and how they describe themselves.
            </p>
            <p>
              Two hundred people following both you and a niche consciousness researcher reveals
              structure, not coincidence. We also embed tweet text into a shared semantic space
              and cluster at multiple scales to map what you write and think about.
            </p>
            <p>
              Follow-graph communities and tweet-content clusters are nearly independent. Their
              statistical agreement is 0.08 out of 1.0. Who you follow and what you write about
              measure different dimensions. The follow graph captures social tribes. Tweet content
              captures intellectual interests.<sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/docs/adr/017-multi-view-account-descriptor.md#L63" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[5]</a></sup>
            </p>
            <p>
              @repligate&rsquo;s follow list points to Qualia Research, as they follow consciousness
              researchers. Their tweet content points to LLM Whisperers, focusing on AI agents, prompt
              engineering, and recursive self-improvement. This divergence provides the most informative
              signal in the data. @repligate orbits one community socially while intellectually living
              in another.
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
              communities. Following Elon Musk doesn&rsquo;t. Rare, specific follows dominate the
              picture. Follows are primary. Retweets count at 0.6&times;. Likes at 0.4&times;.<sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/scripts/cluster_soft.py#L335-L336" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[1]</a></sup>
            </p>
            <p>
              The core technique is matrix factorization. You have a giant sparse matrix of
              who-follows-whom. The algorithm decomposes it into two smaller matrices:
            </p>
            <p className="about-formula">
              <em>A</em> &asymp; <em>W</em> &middot; <em>H</em><sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/scripts/cluster_soft.py#L390-L392" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[2]</a></sup>
            </p>
            <p>
              <em>W</em> tells you each account&rsquo;s community mixture. <em>H</em> tells you what
              defines each community by exposing follow targets and retweet targets. You can look at
              a cluster and see <em>why</em> it exists, which makes human naming possible.
            </p>
            <p>
              These memberships don&rsquo;t sum to one. You can be 80% Builders and 60%
              Contemplative at the same time. Real people belong to multiple scenes.
            </p>
            <p>
              We tested 12, 14, and 16 communities on the same data. At 16, 14 of the communities
              matched the 14-factor run (91% overlap), plus two clean splits where tech-intellectuals
              and creatives each resolved into finer subcommunities. We use 16 because those splits
              are meaningful and the structure is the most stable across random restarts. These are
              social tribes defined by follow patterns. What people write about is a separate question.
            </p>
            <p>
              The {numCommunities} factors emerge as anonymous math. A curator reviews the top
              accounts and follow targets in each factor and names them. A factor where members
              follow the same meditation teachers becomes Contemplative Practitioners.
            </p>
            <p>
              @repligate scores 52% LLM Whisperers, 16% AI Creatives, and 15% Queer TPOT. A
              follow-only analysis categorized them as 100% Qualia Research. Adding likes and
              retweets revealed the LLM tinkering identity. Tweet labeling refines this starting picture.
            </p>
          </section>

          {/* Stage 4: Correcting the Map */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">4</span>
              Correcting the Map
            </h2>

            <p>
              The follow graph tells you which social tribe someone belongs to. It doesn&rsquo;t
              tell you what they actually think, write, or care about. For that, you have to read
              their tweets.
            </p>
            <p>
              Three AI models independently read each tweet and tag it. We only keep tags where at
              least two agree. Each agreement becomes a small piece of evidence. One tweet about
              meditation is a nudge. Fifty tweets is a shove. The evidence accumulates, and it can
              be reversed if later tweets point elsewhere.
            </p>
            <p>
              AI misses things humans see. A tweet containing only a link gives it nothing to work
              with. An image-heavy thread carries meaning it can&rsquo;t read. In early spot-checks,
              about 30% of AI labels needed correction. The AI often guessed based on who the person
              is, not what the tweet says. We run labeling on archive tweets at zero API cost by
              pointing three AI models at the existing data. 125 accounts have been labeled this way
              so far, accumulating over 21,000 evidence tags.
            </p>
            <p>
              Not all tweets carry equal weight. A sincere statement of belief reveals intellectual
              commitments. A strategic argument reveals what someone promotes. The strongest community
              signal comes from performative tweets like in-group memes and shared references. These
              count double because they represent pure expressions of belonging.
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
              The tweets refined the graph rather than replacing it. @repligate genuinely orbits
              Qualia Research, but their active intellectual work lives in LLM Whisperers. The
              correction preserves both truths.
            </p>
          </section>

          {/* Stage 5: Spreading Outward */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">5</span>
              Spreading Outward
            </h2>

            <p>
              The {classifiedStr} seed accounts are well-classified. We must also classify the
              other ~200,000 accounts in the network.
            </p>
            <p>
              Community labels spread outward using Directed Personalized PageRank (PPR). We simulate a
              random walk across the graph starting exclusively from a community's seed accounts.
              The algorithm respects edge directionality: attention flows from the followers backward
              to the authorities they listen to.
            </p>
            <p>
              Raw propagation scores naturally inflate mega-accounts. A node with 10,000 followers
              will absorb probability mass from any random walk simply due to its size. To solve this
              hub penalty, we normalize the community-specific PPR against a Null Model—the
              Global PageRank of the entire network.
            </p>
            <p className="about-formula">
              <em>Network Lift</em> &asymp; <em>Community PPR</em> &divide; <em>Global PageRank</em><sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/src/propagation/engine.py#L327" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[6]</a></sup>
            </p>
            <p>
              This calculation isolates specific community affinity from general popularity. A score
              of 5.0x means an account is five times more likely to be reached by the
              community than by random chance.
            </p>
            <p>
              Not everyone gets a confident placement. Accounts with a Lift score greater than 5.0x
              receive vibrant specialist cards. Accounts with a Lift below 1.5x stay gray to indicate
              uncertainty. The map currently shows {(byBand.bridge || 0).toLocaleString()} bridge
              accounts connecting different scenes.
            </p>
          </section>

          {/* Stage 5.5: The Bridge Discovery */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">&#x2194;</span>
              Most TPOT Members Are Bridges
            </h2>

            <p>
              We checked if the social tribe matches the intellectual profile for people
              independently confirmed as TPOT members.
            </p>
            <p>
              For 82% of them, the profiles do not match. Their follow-graph community and
              their tweet-content community point in different directions. @visakanv follows
              Internet Intellectuals but writes about contemplative practice. @patio11 follows
              Tech Intellectuals but engages with collective intelligence ideas. @RomeoStevens76
              follows Contemplative Practitioners but tweets about AI creativity.
            </p>
            <p>
              TPOT members inherently follow one tribe while intellectually ranging across several.
              A person who exclusively follows and writes about meditation belongs to a meditation
              community, not TPOT.
            </p>
            <p>
              {(byBand.bridge || 0).toLocaleString()} accounts show up as bridges because these
              people genuinely straddle multiple worlds. Blended aesthetics on your card reflect
              how you move through the network.
            </p>
          </section>

          {/* Stage 5.5b: Honest Uncertainties */}
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
              The seed accounts are people who voluntarily uploaded their Twitter data. This group
              skews toward technically literate, EA-adjacent individuals comfortable sharing data
              publicly. Communities where people value privacy are underrepresented. The map sees
              what the seeds can reach.
            </p>

            <h3>Temporal freeze</h3>
            <p>
              Follow patterns change. Someone who followed AI safety accounts in 2023 might
              have pivoted to contemplative practice by 2026. The archive captures a snapshot
              rather than a continuous stream. Reading recent tweets partially compensates, but
              the underlying graph structure remains largely frozen.
            </p>

            <h3>This is Aditya&rsquo;s map, not <em>the</em> map</h3>
            <p>
              These {numCommunities} communities reflect my reading of the landscape. You might see
              one community where I see &ldquo;Jhana Practitioners&rdquo; and &ldquo;Contemplative
              Practitioners&rdquo; as distinct. The algorithm finds clusters. I apply the naming
              and boundary-drawing editorially.
            </p>
            <p>
              If this doesn&rsquo;t match your experience, that&rsquo;s not a bug. The{' '}
              <a href={links.repo} target="_blank" rel="noopener noreferrer">
                entire pipeline is open source
              </a>
              . Fork it, bring your own follow data, label tweets by your own aesthetics,
              and you&rsquo;ll get a different map.
            </p>

            <h3>Confidence decays with distance</h3>
            <p>
              The further you are from a classified account in the network, the weaker
              the signal. One connection away is strong. Two is useful. Three or more is
              mostly noise. With {classifiedStr} classified accounts in a 200K-node network,
              most accounts are far from anyone classified. Their placements appear faint
              because the network is too sparse to carry signal that far.
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
              The system continuously improves by finding uncertain accounts, reading their
              tweets, classifying them, checking results, updating the map, and measuring
              progress. Each round adds more classified accounts and corrects prior mistakes.
              The numbers on this page update with each round.
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
              We verify communities against three independent signals: the follow graph, topic
              models, and co-followed structure. All three signals confirm 12 of 15 communities.
              Two signals confirm the remaining 3 communities.
            </p>
            <p>
              We also re-ran the analysis as data grew from 441K to 815K to 2.7M edges. The
              same communities emerged each time. 11 of 16 matched strongly across runs; the
              other 5 showed minor boundary shifts. If the communities were an artifact of
              sparse data, tripling the data would have destroyed them.
            </p>
            <p>
              Separately, we embedded 24,000 tweets into a semantic space and clustered them at
              multiple scales. The tweet clusters have clean hierarchical structure up to 8 groups,
              meaning there are real macro-topics in what people write about. These content clusters
              are nearly independent of the follow-graph communities. The 0.08 agreement score
              confirms that social structure and intellectual structure operate as different dimensions.<sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/docs/adr/017-multi-view-account-descriptor.md#L63" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[3]</a></sup>
            </p>

            <h3>Testing against known lists</h3>
            <p>
              We tested against 1,822 accounts from four independent lists of known TPOT accounts.
              We measured how many reachable TPOT accounts the map successfully finds.
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
              follow list has low recall because mainstream accounts inflate the denominator.
            </p>
            <p>
              Graph coverage and classified density limit recall. Currently, 39% of Orange
              directory accounts remain unreachable. The {classifiedStr} classified accounts
              must each cover ~600 nodes in the 200K-node graph. Each round of improvement
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
              We prioritize honest measurement over perfection to understand system performance.
            </p>
          </section>

          {/* Stage 7: The Veil of Ignorance */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">7</span>
              The Veil of Ignorance
            </h2>

            <p>
              We must ask if the map can find the territory when we hide the landmarks.
            </p>
            <p>
              To test the map, we removed known TPOT accounts from the seed set and propagated
              the network without them. The system rediscovered them from the structure alone.
            </p>
            <p>
              Across five cross-validation folds, the seed-neighbor signal recovers held-out
              TPOT accounts with an AUC of 0.999. The system finds hidden TPOT accounts 100%
              of the time at a 5% false positive rate. A held-out TPOT member has a median of
              65 seed neighbors. A random non-TPOT account has 1.<sup><a href="https://github.com/anantham/map-tpot/blob/main/tpot-analyzer/scripts/verify_veil_cv.py#L428" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[4]</a></sup>
            </p>
            <p>
              Raw propagation scores yield an AUC of 0.225. TPOT accounts score lower than random
              noise because hub nodes near many communities inherit diffuse signal. The math
              requires measuring how many community members specifically follow you, rather than
              how much total signal reaches you.
            </p>

            <h3>The 17 skeleton keys</h3>
            <p>
              We sorted all {classifiedStr} seeds by connectivity to determine the minimum
              accounts needed to locate TPOT.
            </p>
            <p>
              The top 17 accounts, representing 5% of seeds by neighbor count, locate 81%
              of verified TPOT accounts. Adding the other 95% of seeds only pushes recall
              from 81% to 87%. The network has a backbone, and it&rsquo;s remarkably small.
            </p>
            <p>
              Those 17 accounts span contemplative practitioners, highbies, internet essayists,
              AI safety, builders, and creatives. These connectors bridge multiple scenes. If you
              wanted to reconstruct TPOT from scratch, you&rsquo;d start with them.
            </p>

            <h3>Communities survive deletion</h3>
            <p>
              To test resilience, we deleted all 67 seeds labeled Jhana Practitioners and
              propagated from the remaining 14 communities.
            </p>
            <p>
              The system achieved 100% recall from communities sharing no labels. Contemplative
              Practitioners and Highbies reach into Jhana&rsquo;s neighborhood through overlapping
              follow patterns.
            </p>
            <p>
              Every community survives full deletion. The most insular group, TfT-Coordination,
              recovers at 86%. Contemplative Practitioners, Highbies, and Core TPOT act as
              universal connectors. They appear in the top-3 recovery sources for every other
              community.
            </p>
            <p>
              We drew the communities to match follow patterns, not to survive this test. Surviving
              deletion confirms the structure exists independently of our labeling. We simply
              named the clusters we found.
            </p>
          </section>

          {/* Stage 8: The Active Learning Engine */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">8</span>
              The Active Learning Engine
            </h2>

            <p>
              The system actively drives its own expansion instead of passively waiting for
              data. It uses an Active Learning loop to maximize the return on investment for
              every Twitter API call.
            </p>
            <p>
              The pipeline ranks frontier accounts based on information theory. It calculates
              which uncertain accounts, if fetched and labeled, would resolve the most
              uncertainty across the entire graph. The algorithm prioritizes accounts positioned
              at structural bottlenecks where communities collide.
            </p>
            <p>
              We fetch the highly ranked accounts, read their tweets, and feed the new labels
              back into the network. This process collapses uncertainty cascades. A single
              strategic API call can solidify the placements of dozens of surrounding shadow
              accounts. The map builds itself outward by seeking the highest-leverage information.
            </p>
          </section>

          {/* Stage 9: Behavioral Fingerprinting */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">9</span>
              Behavioral Fingerprinting
            </h2>

            <p>
              Topic modeling captures what people write about. The pipeline also builds
              Behavioral Fingerprints to capture how people act.
            </p>
            <p>
              We compile Cadence, Posture, and Simulacrum profiles for every classified account.
              The system mathematically models behavioral rhythms like <code>reply_ratio</code> and
              <code>tweets_per_week</code>. The AI also classifies the stance of each tweet to detect
              if an account relies on a <code>playful-exploration</code> or <code>personal-testimony</code> posture.
            </p>
            <p>
              These behavioral dimensions operate independently from topical interests. Two
              accounts might both discuss artificial intelligence. The system distinguishes the
              founder shipping product announcements from the tinkerer anthropomorphizing
              the model late at night. The map groups people by their shared epistemic approach,
              not just their shared vocabulary.
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
              Your card embodies your communities. Each community has a signature mascot,
              palette, and elemental vibe. Your primary community dominates the composition.
              Secondary communities appear as accents. The result is a card you can <em>feel</em> without
              decoding.
            </p>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Exemplar</span>
              <p>
                <strong>{classifiedStr} seed accounts.</strong> These accounts possess full archive
                data including follows, retweets, and liked content. They receive rich tarot-style
                cards with community iconography woven into the art.
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
                Bridge accounts straddle 2&ndash;3 communities. Their cards blend multiple aesthetics
                to reflect social reality rather than classification failure.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Frontier</span>
              <p>
                Frontier accounts have uncertain placement due to distance from seeds or conflicting
                community pulls. Grayscale card. Candidates for exploration.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Faint</span>
              <p>
                Barely visible in the network. Present in the graph but below the confidence
                threshold. These accounts remain searchable, but receive dim cards.
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
              This map starts from my perspective. It relies on the ~1,400 accounts I follow,
              the {classifiedStr} seeds I classified, and the boundaries I drew.
            </p>
            <p>
              A contemplative practitioner would draw the meditation scene at higher resolution.
              They might split &ldquo;Jhana Practitioners&rdquo; into jhana technicians, somatic
              healers, and nondual teachers. A builder would see more granularity in the
              infrastructure scene. The map reflects the mapper.
            </p>
            <p>
              Not every account in the{' '}
              <a href="https://www.community-archive.org/" target="_blank" rel="noopener noreferrer">
                community archive
              </a>{' '}
              is TPOT. Uploading data represents an act of transparency rather than a membership
              card. The pipeline filters for this: accounts whose follow patterns don&rsquo;t
              concentrate in any community propagate with lower confidence.
            </p>
            <p>
              Identifying someone in the wrong community, a community that requires splitting,
              or a missing scene provides valuable signal. The map improves when you tell us.
            </p>
          </section>

          {/* The Visual Language */}
          <section className="about-section">
            <h2>The Visual Language</h2>

            <p>
              Each community has an encoded visual identity. Jhana Practitioners get lotus
              serpents and deep violet, still water and inner radiance. LLM Whisperers get
              recursive wyrms in toxic green, digital fog and glitch. Vibecamp Highbies get
              laughing bodhisattvas in burning gold. NYC Builders get concrete and crimson.
              Queer TPOT gets a kaleidoscopic chimera, holographic and shifting.
            </p>
            <p>
              Lotus borders and moonlight pools represent the contemplative scene. Circuit patterns
              mean LLM Whisperers. Fractal blooms mean AI Creatives. The card is a portrait of
              where someone lives in the network, rendered as mythology.
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
              The entire pipeline is open source. The pipeline operates generally while the
              seeds remain specific.
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