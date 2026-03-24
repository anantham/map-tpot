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
          {/* Stage 1: What We Can See */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">1</span>
              What We Can See
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
              From those {classifiedStr} accounts, we can trace outward to ~200,000 accounts in
              their follow graph. For each archived account, we see everything&mdash;every follow,
              every retweet. For the other ~200K, we only know that <em>someone</em> follows
              them&mdash;not who <em>they</em> follow. It&rsquo;s like knowing which lectures
              a student attends, but not what the professors do on weekends.
            </p>
            <p>
              Take @repligate. They&rsquo;re one of the {classifiedStr} who shared data. We can
              see all ~1,200 accounts they follow and all their retweets. But for those 1,200
              accounts, we only know @repligate follows them. The result is a giant matrix
              that&rsquo;s almost entirely empty&mdash;about 0.3% of cells are filled. That
              sparsity is the raw material.
            </p>
          </section>

          {/* Stage 2: What Signals We Use */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">2</span>
              What Signals We Use
            </h2>
            <p>
              Who you follow is the strongest signal. It&rsquo;s deliberate, stable, and reveals
              what you chose to listen to. But it&rsquo;s not the only one.
            </p>
            <p>
              What you retweet shows what you amplify. What you like shows what catches your eye.
              Who replies to your posts&mdash;and whether you liked their reply&mdash;hints at who
              you&rsquo;re actually in conversation with. Each signal has a different shape. Follows
              are architectural. Retweets are behavioral. Likes are reflexive. Replies are relational.
            </p>
            <p>
              Then there are signals that don&rsquo;t come from individual actions at all. If 200
              people all follow both you and the same niche consciousness researcher, that&rsquo;s
              not coincidence&mdash;that&rsquo;s topology. We compute these co-followed patterns
              across the whole network. Separately, we run topic models over 17.5 million liked
              tweets to ask: <em>what does this person read about?</em> That gives us 25
              macro-interest dimensions&mdash;an entirely different lens from the social graph.
            </p>
            <p>
              Here&rsquo;s why layering matters. @repligate&rsquo;s follow targets say
              &ldquo;Qualia Research&rdquo;&mdash;they follow QRI researchers, consciousness
              Twitter. But their liked content says &ldquo;LLM Whisperers&rdquo;&mdash;AI agents,
              prompt engineering, recursive self-improvement. The follow signal and the content
              signal disagree. That disagreement is the most informative thing in the data. It
              means @repligate orbits one community but intellectually lives in another. You need
              both signals to see that.
            </p>
            <p>
              In total we use eight signal types: follow targets, retweet targets, resolved
              like-author edges (~24K pairs), content vectors (25 topics), co-followed topology,
              17K signed reply pairs, human tweet labeling, and engagement-weighted propagation.
              Most run across all accounts. Tweet labeling is experimental&mdash;applied to a
              handful so far.
            </p>
          </section>

          {/* Stage 3: How The First Map Is Made */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">3</span>
              How the First Map Is Made
            </h2>

            <p>
              Before writing any code, four questions need answers. What counts as evidence? How
              do we define a community? How confident should we be in the initial picture? And
              what do we do with accounts that fit nowhere?
            </p>

            <h3>What counts as evidence</h3>
            <p>
              Not all actions carry the same weight. Following a niche consciousness researcher
              separates communities. Following @elonmusk doesn&rsquo;t. We weight signals by how
              distinctive they are&mdash;a technique called TF-IDF&mdash;so that rare, specific
              follows dominate the picture. Follows are primary. Retweets count at 0.6&times;.
              Resolved like-author edges (where we can identify whose tweet was liked) count
              at 0.4&times;.
            </p>
            <p>
              Of 17.5M raw likes in the archive, only ~24K can be attributed to an author. That&rsquo;s
              a partial signal, but it covers ~79% of seed accounts and meaningfully shifted
              community boundaries when we added it.
            </p>

            <h3>What is a community membership?</h3>
            <p>
              The central question. Is each account in exactly one community? A weighted mixture
              that sums to 1? Or independent memberships&mdash;you can be 80% Builders AND
              60% Contemplative?
            </p>
            <p>
              We chose NMF (Non-negative Matrix Factorization)&mdash;independent, non-negative,
              parts-based. It decomposes the giant matrix into two smaller ones:
            </p>
            <p className="about-formula">
              <em>A</em> &asymp; <em>W</em> &middot; <em>H</em>
            </p>
            <p>
              <em>W</em> gives each account&rsquo;s community weights. <em>H</em> shows what
              defines each community&mdash;which follow targets, which retweet targets. That
              second matrix is what makes human curation possible: you can look at a cluster
              and see <em>why</em> it exists.
            </p>

            <h3>How many communities?</h3>
            <p>
              We tested k=12, 14, and 16 factors with the same data. At k=14, 11 of 14
              communities matched across runs (46% average overlap). At k=16, 14 of 16
              matched to k=14 (91% overlap) with two clean splits&mdash;tech-intellectuals
              and creatives each resolved into finer subcommunities. We use k=16 because
              the splits are meaningful and the structure is the most stable across
              random restarts.
            </p>
            <p>
              NMF is non-unique&mdash;different random seeds give slightly different
              decompositions. We mitigate this by running multiple initializations and
              checking factor alignment. The communities that appear consistently
              across restarts are real structure, not artifacts.
            </p>

            <h3>How strong is the initial picture?</h3>
            <p>
              NMF gives you factors, not beliefs. The question is: how much evidence should
              it take to override the initial picture? A skeptical prior (worth 2 virtual
              tweets) gets corrected quickly. A strong prior (worth 20) resists correction.
              Full archive accounts get a confident prior. Accounts we only see through the
              wider network get a weaker one.
            </p>

            <h3>What about accounts that fit nowhere?</h3>
            <p>
              Some accounts are bridges between communities. Some are outliers. Some are
              evidence the ontology is incomplete. The system includes a &ldquo;none&rdquo;
              class and an entropy-based uncertainty score. Accounts with high uncertainty
              are classified as &ldquo;frontier&rdquo;&mdash;we&rsquo;d rather say &ldquo;we
              don&rsquo;t know&rdquo; than guess wrong.
            </p>
            <p>
              Bridge accounts are not failures. @vgr is followed by 117 seeds across all{' '}
              {numCommunities} communities. They genuinely straddle everything&mdash;they&rsquo;re
              pan-TPOT. The system preserves that full distribution rather than forcing them
              into a single bucket.
            </p>

            <h3>Then: human naming</h3>
            <p>
              The {numCommunities} factors that come out of NMF are anonymous&mdash;&ldquo;Factor
              7&rdquo; means nothing. A curator reviews the top accounts and top follow targets in
              each factor and names them: &ldquo;these people all follow the same meditation teachers
              and consciousness researchers&rdquo; becomes Contemplative Practitioners.
            </p>
            <p>
              For @repligate, the NMF result with likes is: <strong>52% LLM Whisperers, 16% AI
              Creatives, 15% Queer TPOT.</strong> The old follow-only NMF said 100% Qualia Research.
              Adding likes and retweets shifted them dramatically&mdash;their like patterns reveal
              the LLM tinkering identity that follows alone couldn&rsquo;t see. This is the graph
              prior. It&rsquo;s closer to the truth now, but tweet labeling refines it further.
            </p>
          </section>

          {/* Stage 4: How The First Map Gets Corrected */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">4</span>
              How the First Map Gets Corrected
              <span className="about-badge-status about-badge-status--experimental">EXPERIMENTAL</span>
            </h2>

            <p>
              The follow graph tells you who someone listens to. It doesn&rsquo;t tell you what
              they actually think, write, or care about. That gap is where tweet labeling comes in.
            </p>
            <p>
              Three AI models independently read each tweet and tag it: what community
              would claim this? We only keep tags where at least two models agree.
              Each agreement becomes a small piece of evidence nudging the account
              toward a community. One tweet about meditation is a nudge. Fifty tweets
              is a shove. The evidence adds up and can be reversed if later tweets
              point elsewhere.
            </p>
            <p>
              AI misses things humans see. A tweet that&rsquo;s just a link gives the AI
              nothing to work with. An image-heavy thread carries meaning the AI can&rsquo;t
              read. So a human opens each labeled tweet in a browser, checks the full
              context&mdash;images, quoted tweets, who&rsquo;s replying&mdash;and corrects
              mistakes. Of 57 tweets spot-checked this way, 33 needed corrections. The most
              common error: the AI guessed based on who the person <em>is</em>, not what
              the tweet <em>says</em>.
            </p>
            <p>
              Not all tweets carry equal weight. A sincere statement of belief (&ldquo;I think
              consciousness is fundamental&rdquo;) reveals intellectual commitments. A strategic
              argument (&ldquo;here&rsquo;s why you should care&rdquo;) reveals what someone
              promotes. But the strongest community signal comes from performative
              tweets&mdash;in-group memes, shared references, the specific jokes only your
              people would get. These L3 tweets count double, because they&rsquo;re the purest
              expression of belonging. Vibes-only shitposts signal that someone speaks the
              language, but not which community they&rsquo;re in.
            </p>
            <p>
              After labeling 51 of @repligate&rsquo;s tweets (683 tags, 213 bits across 6
              communities), the picture shifts:
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
            <p>
              The correction didn&rsquo;t throw out the graph&mdash;it refined it. @repligate
              genuinely orbits Qualia Research (their follows prove it), but their active
              intellectual work lives in LLM Whisperers. Tweet labeling now covers
              32 accounts (502 tweets), each checked by three AI models and then
              spot-checked by a human in the browser.
            </p>
          </section>

          {/* Stage 5: How Confidence Spreads */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">5</span>
              How Confidence Spreads
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
              To separate real connections from noise, we check: how many classified accounts
              actually follow you, per community? An account followed by people from two
              different communities is a genuine bridge. An account with one random connection
              is noise&mdash;that&rsquo;s why @googlecalendar doesn&rsquo;t show up even
              though it&rsquo;s technically in the network.
            </p>
            <p>
              Not everyone gets a confident placement. Accounts close to many classified
              accounts get strong colors. Accounts far from anyone classified stay
              gray&mdash;we&rsquo;d rather say &ldquo;we&rsquo;re not sure&rdquo; than
              guess wrong. <strong>That restraint is why grayscale cards exist.</strong>
            </p>

            <h3>Why this approach?</h3>
            <p>
              An earlier version forced every account into exactly one community. If you
              were 60% Qualia, you could only be 40% everything else combined. This
              produced zero bridges&mdash;every account was either a specialist or unknown.
              That&rsquo;s not how communities work.
            </p>
            <p>
              The current system runs a separate calculation for each community. The
              scores don&rsquo;t compete with each other, so someone can be strongly
              connected to both Contemplative Practitioners and Qualia Research at the
              same time. The map currently shows{' '}
              {(byBand.bridge || 0).toLocaleString()} bridge accounts that were invisible
              in the old approach.
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
              The seed accounts are people who voluntarily uploaded their Twitter data to the
              Community Archive. That&rsquo;s not random&mdash;it skews toward people who are
              technically literate, EA-adjacent, and comfortable sharing data publicly. Communities
              where people value privacy (somatic practitioners, some queer scenes) are
              underrepresented in the seeds. The map sees what the seeds can reach.
            </p>

            <h3>Temporal freeze</h3>
            <p>
              Follow patterns change. Someone who followed AI safety accounts in 2023 might
              have pivoted to contemplative practice by 2026. The archive is a snapshot, not a
              stream. The active learning pipeline (fetching recent tweets via API) partially
              compensates, but the graph structure is largely frozen.
            </p>

            <h3>Ontology is one curator&rsquo;s lens</h3>
            <p>
              The {numCommunities} communities are named and bounded by one person&rsquo;s
              judgment. &ldquo;Jhana Practitioners&rdquo; vs &ldquo;Contemplative
              Practitioners&rdquo;&mdash;where exactly is the line? A different curator would
              draw different boundaries, merge some, split others. NMF gives us factors;
              the naming is editorial.
            </p>

            <h3>Confidence decays with distance</h3>
            <p>
              The further you are from a classified account in the network, the weaker
              the signal. One connection away is strong. Two connections is useful. Three
              or more is mostly noise. With {classifiedStr} classified accounts in a
              200K-account network, most accounts are far from anyone classified. Their
              placements are faint not because they&rsquo;re not TPOT, but because the
              network is too sparse to carry signal that far.
            </p>

            <h3>AI labeling makes mistakes</h3>
            <p>
              The AI reads tweets and guesses communities, but it gets ~30% wrong on the
              first pass. It confuses mentioning a tool with being part of that
              tool&rsquo;s community. It can&rsquo;t see images. It attributes retweet
              content to the person who retweeted. A human spot-checks in the browser,
              but only 57 of 502 labeled tweets have been verified so far.
            </p>

            <h3>What we&rsquo;re doing about it</h3>
            <p>
              The system continuously improves: find accounts we&rsquo;re uncertain about,
              read their tweets, classify them, spot-check the results, update the map,
              measure how much better we got. Each round adds more classified accounts
              and corrects prior mistakes. The numbers on this page update with each round.
            </p>
          </section>

          {/* Stage 6: How We Validate */}
          <section className="about-section">
            <h2>
              <span className="about-stage-num">6</span>
              How We Validate
            </h2>
            <p>
              A community that only shows up in one signal could be an artifact. A community
              confirmed by three independent methods is real.
            </p>
            <p>
              We check each community against three orthogonal signals: graph structure
              (who follows whom), content vectors (what people like reading&mdash;25 topics
              from 17.5M liked tweets), and co-followed topology (who is followed by the
              same people). <strong>12 of 15 communities</strong> are validated by all
              three. The remaining 3 are confirmed by 2 of 3&mdash;real communities, but
              with weaker independent confirmation.
            </p>
            <p>
              @repligate illustrates what convergence looks like. Their content profile
              (32% LLM-tinkering, 15% philosophy, 15% highbies social) aligns with their
              graph community (52% LLM Whisperers). When graph and content agree,
              confidence is high.
            </p>

            <h3>Holdout recall</h3>
            <p>
              We test against 1,822 accounts from four independent lists of known TPOT
              accounts&mdash;none of which were used to build the map. The honest question
              is: of accounts that are known TPOT and reachable in our network, how many
              does the map find?
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
              Aditya&rsquo;s follows have low recall because most are mainstream
              accounts that aren&rsquo;t TPOT&mdash;the denominator is inflated.
              The more curated the source, the higher the recall. Accounts confirmed
              by 3+ independent sources are found 65% of the time.
            </p>
            <p>
              Two bottlenecks limit recall: <strong>graph coverage</strong> (39% of Orange
              directory accounts aren&rsquo;t reachable&mdash;we don&rsquo;t have their
              follow data yet) and <strong>seed density</strong> ({classifiedStr} seeds in
              a 200K-node graph means each seed covers ~600 nodes). Each round of active
              learning adds more seeds and pushes recall up.
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
