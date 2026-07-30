import { useState } from 'react'

export default function About({ meta, onNavigate }) {
  const [path, setPath] = useState(null)
  const counts = meta?.counts || {}
  const links = meta?.links || {}
  const siteName = meta?.site_name || 'Find My Ingroup'

  const numCommunities = counts.communities || 'many'
  const byBand = counts.by_band || {}
  const totalStr = counts.total_accounts?.toLocaleString() || '11,600+'
  const classifiedStr = byBand.exemplar?.toLocaleString() || '361'
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
              The archive contains eight relationship types: follows, followers, mentions,
              quotes, co-follows, likes, replies, and retweets. Different producers use different
              subsets of those records. The legacy NMF view uses follows, retweets, and optionally
              likes; the propagation graph has its own typed-edge weights. Those weights are
              hypotheses about signal, not measured universal meanings. An algorithm finds
              accounts with similar connection patterns, and a human curator reviews and names
              the resulting factors.
            </p>
            <p>
              Then we read tweets. Your social tribe and intellectual interests often point in
              different directions. This divergence makes the network interesting. We infer
              placement for accounts outside the core dataset based on their position in the
              network. Grayscale cards indicate weaker observed graph support for these inferred
              placements. This support score is heuristic, not a membership probability.
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
              and likes. The public snapshot described on this page includes around 327
              contributors. The Community Archive continues updating, so this is not a live
              contributor count. The snapshot contains millions of tweets and likes and provides
              a detailed, but incomplete, record of who contributors chose to listen to.
            </p>
            <p>
              Each archived account follows hundreds or thousands of people. Tracing these
              connections outward reveals roughly 298,000 accounts in the shadow network.
              Contributor exports provide much richer records, but available fields and timestamps
              vary; we do not assume complete histories. For most other accounts we initially know
              only observed incoming edges. They exist as faceless silhouettes in the graph.
            </p>
            <p>
              We selectively fetch data for the most connected shadow accounts via the Twitter API
              to fill in the picture. We retrieve their follows, recent tweets, and bios. We prioritize
              accounts that many archived people follow, or that sit at the intersection of multiple
              communities.
            </p>
            <p>
              A legacy pipeline report described a 2.7-million-edge searchable working graph.
              The raw relationship table below reported 25,132,521 records across eight edge
              types. These are different data products; without their source manifests, they
              should not be treated as the same denominator.
            </p>
            <p>
              Unless a paragraph explicitly says otherwise, every numerical result on this page
              is a point-in-time legacy measurement. The public page does not yet bind those
              numbers to an immutable source snapshot, query, code revision, and run receipt.
              Treat them as descriptive historical observations—not current Community Archive
              counts, calibrated performance, or independently reproducible benchmarks.
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
                    <td>3,822,341</td>
                    <td>Who you address</td>
                  </tr>
                  <tr>
                    <td>Follow</td>
                    <td>803,998</td>
                    <td>Who you listen to</td>
                  </tr>
                  <tr>
                    <td>Follower</td>
                    <td>1,647,325</td>
                    <td>Who listens to you</td>
                  </tr>
                  <tr>
                    <td>Quote</td>
                    <td>549,285</td>
                    <td>Who you publicly comment on</td>
                  </tr>
                  <tr>
                    <td>Co-followed</td>
                    <td>16,701</td>
                    <td>Accounts sharing an audience</td>
                  </tr>
                  <tr>
                    <td>Like</td>
                    <td>17,501,243</td>
                    <td>Attention or weak preference; may also reflect bookmarking, irony, or disagreement</td>
                  </tr>
                  <tr>
                    <td>Reply</td>
                    <td>17,362</td>
                    <td>Direct conversations</td>
                  </tr>
                  <tr>
                    <td>Retweet</td>
                    <td>774,266</td>
                    <td>Audience amplification</td>
                  </tr>
                  <tr>
                    <td><strong>Total raw edges</strong></td>
                    <td><strong>25,132,521</strong></td>
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
              The current heuristics give follows the largest coefficient. That is an assumption:
              follows are often more deliberate and persistent than a single interaction, but
              they can also be stale, adversarial, parasocial, or purely informational. Weight
              ablations and time-aware holdouts are needed before calling them the strongest
              signal in general.
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
              In one legacy comparison, follow-graph labels and tweet-content clusters had an
              adjusted mutual information score of 0.08. That is evidence of low agreement in
              that sample, not proof that the views are statistically independent or that one
              uniquely measures social tribe while the other measures intellectual interest.<sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/docs/adr/017-multi-view-account-descriptor.md#L61-L65" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[5]</a></sup>
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
              picture after TF-IDF and normalization. In this NMF producer, follows use a
              1.0 block weight, retweets default to 0.6, and optional likes default to 0.4.
              These are configurable heuristic coefficients, not learned causal effects or the
              weights used by every graph producer.<sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/scripts/cluster_soft.py#L335-L336" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[1]</a></sup>
            </p>
            <p>
              Separately, the typed propagation producer defaults to follow 1.0, quote 0.7,
              retweet 0.6, reply 0.5, like 0.3, mention 0.15, co-follow 0.1, and
              inbound-follower 0.0. The last layer is retained for reciprocity queries but
              omitted from the default sum. These coefficients are also hand-set: they do not
              yet learn valence, model event context, correct missing-not-at-random capture, or
              prove that one interaction type is intrinsically more informative.<sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/src/propagation/typed_graph.py#L33-L44" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[7]</a></sup>
            </p>
            <p>
              The legacy discovery technique is non-negative matrix factorization. It concatenates
              normalized TF-IDF blocks for follows, retweets, and optionally likes into a sparse
              account-by-feature matrix, then decomposes that matrix into two smaller matrices:
            </p>
            <p className="about-formula">
              <em>A</em> &asymp; <em>W</em> &middot; <em>H</em><sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/scripts/cluster_soft.py#L380-L403" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[2]</a></sup>
            </p>
            <p>
              <em>W</em> tells you each account&rsquo;s community mixture. <em>H</em> tells you what
              features load onto each factor across the follow, retweet, and optional-like blocks.
              Inspecting those loadings gives a curator evidence for naming, but it does not make
              the name objective or prove that a factor is a natural community.
            </p>
            <p>
              In the current NMF implementation, each account&rsquo;s factor row is normalized
              to sum to one. These are relative factor shares, not probabilities of belonging.
              Multiple nonzero shares show mixed structure; independently overlapping
              affinities require a separate model.
            </p>
            <p>
              In a legacy run, we tested 12, 14, and 16 factors on the same data. At 16, 14 of the communities
              matched the 14-factor run (91% overlap), plus two clean splits where tech-intellectuals
              and creatives each resolved into finer subcommunities. The curator selected 16 because
              those splits appeared interpretable and stable in those restarts. That is model-selection
              evidence for that snapshot, not proof of a true number of social tribes.
            </p>
            <p>
              The {numCommunities} factors emerge as anonymous math. A curator reviews the top
              accounts and follow targets in each factor and names them. A factor where members
              follow the same meditation teachers becomes Contemplative Practitioners.
            </p>
            <p>
              In that run, @repligate&rsquo;s normalized NMF factor shares are 52% LLM
              Whisperers, 16% AI Creatives, and 15% Queer TPOT. A
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
              The follow graph offers evidence about social position and attention. It does not by
              itself establish group belonging or what someone thinks, writes, or cares about.
              Tweet evidence adds a different, still incomplete view.
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
              is, not what the tweet says. We can label archive tweets without buying new Twitter
              data by pointing three AI models at already-held records, so that step adds no acquisition
              cost. Model inference, provider charges, local compute, and data-egress risks are separate
              costs. A legacy run reported 125 labeled accounts and over 21,000 evidence tags.
            </p>
            <p>
              Not all tweets carry equal weight. A <a href="https://www.lesswrong.com/tag/simulacrum-levels" target="_blank" rel="noopener noreferrer">sincere statement of belief</a> reveals intellectual
              commitments. A strategic argument reveals what someone promotes. The strongest community
              signal comes from performative tweets like in-group memes and shared references. These
              currently count double under an unvalidated heuristic. The hypothesis is that such posts
              reveal affiliation more directly; it would be falsified if held-out curator judgments
              or downstream calibration do not improve against an equal-weight baseline.
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
              The {classifiedStr} historical seed rows combine NMF-derived assignments,
              LLM-ensemble additions, and curator review. They are not a fully human-labeled or
              validated golden set. The legacy propagation attempted to extend those starting
              labels to roughly 200,000 other accounts.
            </p>
            <p>
              Community labels spread outward using Directed Personalized PageRank (PPR). We simulate a
              random walk across the graph starting exclusively from a community's seed accounts.
              The algorithm respects edge directionality: attention flows from the followers backward
              to the authorities they listen to.
            </p>
            <p>
              Raw propagation scores can favor highly connected accounts. A node with 10,000 followers
              may absorb mass across many random walks partly due to its graph position. To reduce this
              popularity effect, we normalize the community-specific PPR against a null model—the
              Global PageRank of the entire network.
            </p>
            <p className="about-formula">
              <em>Network Lift</em> = <em>Community PPR</em> &divide; <em>Global PageRank</em><sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/src/propagation/engine.py#L356-L389" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[6]</a></sup>
            </p>
            <p>
              This calculation isolates specific community affinity from general popularity.
              Under this random-walk model, 5.0x lift means five times the global PageRank
              visitation baseline. It does not mean five times the probability that the account
              belongs to the community.
            </p>
            <p>
              The currently loaded public export still carries historical display-band labels.
              They came from an older propagation artifact whose independent-Lift entropy formula
              was scale-dependent, and the labels are now quarantined legacy metadata. The
              current independent-Lift path refuses to regenerate or re-export those bands until
              specialist/bridge semantics beat simpler baselines on frozen judgments. The classic
              legacy export is also not provenance-bound to an exact propagation run, so the
              current exporter suppresses every existing band row and falls back to
              classified-only seed rows. Card intensity is a separate uncalibrated rendering
              heuristic.
            </p>
            <p>
              The graph explorer also exposes a separate Gaussian random-field harmonic solver.
              Its bounded output is an uncalibrated affinity, not a membership probability. Its
              uncertainty score combines affinity entropy with a low-degree penalty, so it is a
              heuristic prioritization signal rather than posterior uncertainty.
            </p>
            <p>
              That endpoint is currently a binary experimental path, not yet the overlapping
              subculture model described elsewhere. It aggregates an ego&rsquo;s working anchor
              polarities across tag keys and does not target an ontology task or community.
              Target-scoped anchors, cache keys, responses, and cross-target-isolation tests are
              required before interpreting separate community affinities.
            </p>
          </section>

          {/* Stage 5.5: The Bridge Discovery */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">&#x2194;</span>
              Historical Bridge Labels Are Not Findings
            </h2>

            <p>
              In one legacy comparison, we checked whether a graph-derived label matched a
              content-derived label for accounts appearing on TPOT reference lists.
            </p>
            <p>
              For 82% of them, the profiles do not match. Their follow-graph community and
              their tweet-content community point in different directions. @visakanv follows
              Internet Intellectuals but writes about contemplative practice. @patio11 follows
              Tech Intellectuals but engages with collective intelligence ideas. @RomeoStevens76
              follows Contemplative Practitioners but tweets about AI creativity.
            </p>
            <p>
              This sample suggests that some listed TPOT accounts follow one scene while writing
              across several. It does not establish an inherent property of TPOT membership or
              justify excluding a person whose observed activity concentrates on meditation.
            </p>
            <p>
              The loaded export contains {(byBand.bridge || 0).toLocaleString()} historical rows
              labeled &ldquo;bridge&rdquo;. Those rows predate the active Lift artifact and were
              produced with invalid entropy math, so their blended card aesthetics are preserved
              only as quarantined legacy metadata. They do not verify overlap, belonging, or
              identity.
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

            <h3>Graph evidence weakens when support is sparse</h3>
            <p>
              Observed classified seed neighbors can provide graph support, but the historical
              display bands also mixed in invalid independent-Lift entropy and are quarantined.
              Sparse support is not a calibrated distance law. Evidence coverage is observed
              outgoing follow edges divided by expected follows when that denominator is known
              and positive. The numerator and denominator must also refer to a compatible source,
              snapshot generation, and as-of time. Otherwise coverage is unknown rather than 0%
              or 100%.
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
              The intended iteration loop finds uncertain accounts, reads their tweets,
              classifies them, checks results, updates the map, and measures progress. Some
              pieces exist as scripts, but the provenance-tracked flywheel and automatic page
              refresh are not yet an operational guarantee.
            </p>
          </section>

          {/* Stage 6: How We Know It Works */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">6</span>
              How We Know It Works
            </h2>
            <p>
              A community that only shows up in one view could be a pipeline artifact.
              Corroboration across several views reduces that risk; it does not establish
              ontology-independent ground truth.
            </p>
            <p>
              We compare three views: the follow graph, topic models, and co-followed structure.
              Follow and co-follow views are graph-derived and therefore not independent.
              In the legacy analysis, all three views supported 12 of 15 named communities,
              while two views supported the remaining 3.
            </p>
            <p>
              We also re-ran the analysis as data grew from 441K to 815K to 2.7M edges. The
              same communities emerged each time. 11 of 16 matched strongly across runs; the
              other 5 showed minor boundary shifts. This legacy stability check is evidence
              against some sparse-data artifacts, but it does not rule out shared sampling,
              preprocessing, or curator-label artifacts.
            </p>
            <p>
              Separately, we embedded 24,000 tweets into a semantic space and clustered them at
              multiple scales. The tweet clusters have clean hierarchical structure up to 8 groups,
              which is consistent with macro-topic structure in that sample. Their 0.08 adjusted
              mutual information with follow-graph labels shows low agreement for that run; it
              does not confirm statistical independence or a unique interpretation for either
              view.<sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/docs/adr/017-multi-view-account-descriptor.md#L61-L65" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[3]</a></sup>
            </p>

            <h3>Testing against known lists</h3>
            <p>
              We tested against 1,822 accounts from four overlapping TPOT reference lists.
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
                    <td>Accounts appearing on 3+ lists</td>
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
                    <td>Accounts appearing on 2+ lists</td>
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
              In this legacy comparison, the more curated sources had higher measured recall.
              Accounts appearing on 3+ of these overlapping lists were found 65% of the time.
              Aditya&rsquo;s raw follow list had lower recall partly because mainstream accounts
              inflated the denominator.
            </p>
            <p>
              Graph coverage and classified density can limit recall. In that table, 39% of Orange
              directory accounts were unreachable. Adding well-chosen labels may improve recall,
              but the gain must be measured on held-out labels rather than assumed from graph size.
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
                    <td>Historical specialist + bridge + frontier labels</td>
                    <td>{((byBand.specialist || 0) + (byBand.bridge || 0) + (byBand.frontier || 0)).toLocaleString()}</td>
                  </tr>
                  <tr>
                    <td>Historical faint labels</td>
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
              In a legacy point-in-time test of binary TPOT relevance—not soft per-community
              membership—we removed known TPOT accounts from the seed set and propagated the
              network without them. This was not a frozen benchmark or a calibration result.
            </p>
            <p>
              Across five cross-validation folds, the seed-neighbor signal recovers held-out
              TPOT accounts with an AUC of 0.999. The system finds hidden TPOT accounts 100%
              of the time at a 5% false positive rate. A held-out TPOT member has a median of
              64 seed neighbors. A random non-TPOT account has 1. These are unregistered legacy
              estimates from the sampled binary task, not expected production performance.<sup><a href="https://github.com/anantham/map-tpot/blob/549de93/tpot-analyzer/scripts/verify_veil_cv.py#L415-L438" target="_blank" rel="noopener noreferrer" className="about-footnote-link">[4]</a></sup>
            </p>
            <p>
              Raw propagation scores yield an AUC of 0.178. TPOT accounts score lower than random
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
              deletion is consistent with redundant graph paths in that snapshot. It does not
              establish that the structure exists independently of seed selection, edge sampling,
              model choices, or curator naming.
            </p>
          </section>

          {/* Stage 8: Planned active learning loop */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">8</span>
              Planned Active Learning Loop
            </h2>

            <p>
              The intended system should actively propose where additional evidence would be
              most useful instead of passively waiting for data. The historical frontier ranking
              is currently blocked because its stored rows are unversioned and its active
              independent-Lift uncertainty and &ldquo;none&rdquo; terms are invalid. ADR 022
              specifies the holdout, receipts, budget gates, and randomized audit required before
              claiming value-of-information optimization.
            </p>
            <p>
              The planned policy ranks typed actions—such as reviewing an existing tweet or
              fetching a specific public edge—by expected development-risk reduction per dollar
              and human minute. That value must be tested against random, degree, entropy, and
              current frontier baselines before promotion.
            </p>
            <p>
              No autonomous paid expansion is authorized. Any future batch must record what was
              observed, what left the machine, what it cost, and whether the revealed evidence
              improved held-out decisions. Negative results remain part of the experiment record.
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
              These behavioral dimensions are intended to complement topical interests; their
              statistical independence has not been established. Two accounts might both discuss
              artificial intelligence. The system attempts to distinguish the
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
                <strong>{classifiedStr} seed accounts.</strong> These accounts have richer
                contributed archive data, which may include follows, retweets, and liked content.
                Available fields and time spans vary. They receive rich tarot-style cards with
                community iconography woven into the art.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--color">Specialist</span>
              <p>
                A historical display label from the stale band artifact. It is quarantined legacy
                metadata, not current strong graph evidence or confirmed belonging.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--bridge">Bridge</span>
              <p>
                A historical display label whose old threshold and precedence rules were not
                validated. It does not establish real overlap; blended cards retain the legacy
                aesthetic only.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Frontier</span>
              <p>
                A historical display label, not an information-value ranking. These grayscale
                cards may still suggest accounts to inspect, but the label cannot steer paid
                acquisition.
              </p>
            </div>

            <div className="about-tier">
              <span className="about-badge about-badge--gray">Faint</span>
              <p>
                A historical fallback label from the stale band export. It does not establish
                weak support or graph distance; dim cards retain legacy presentation only.
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
              This map starts from my perspective. Its inputs include the ~1,400 accounts I
              follow and {classifiedStr} historical seed rows assembled from NMF, LLM-ensemble,
              and curator inputs; its names and boundaries also reflect my editorial choices.
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
              card. The historical pipeline attempted to filter for this using graph affinity and
              support heuristics, but its independent display bands are now quarantined.
            </p>
            <p>
              TPOT can be viewed as a meta-community rather than one single thing. Conceptually, a
              &ldquo;bridge account&rdquo; would straddle several scenes and connect them. That is
              a useful retrieval target, not something the historical band label has established.
            </p>
            <p>
              In one legacy comparison, 82% of listed TPOT reference accounts received different
              graph-derived and content-derived labels. They
              might follow the AI Safety scene but write for the Highbies, or live in the NYC
              building scene while practicing Jhana. Disagreement between social scene and intellectual
              identity may indicate cross-pollination, model mismatch, or incomplete evidence; the
              observed disagreement alone does not decide among those explanations.
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
              An account with illustrative normalized factor shares of 45% Jhana, 30% Core TPOT,
              and 15% LLM Whisperers gets a
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
