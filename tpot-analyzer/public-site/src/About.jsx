export default function About() {
  return (
    <div className="about-page">
      <a href="/" className="about-back">&larr; Back to search</a>

      <h1 className="about-title">How We Map Communities</h1>
      <p className="about-intro">
        This isn't one algorithm. It's a pipeline that combines graph topology, behavioral
        fingerprints, human curation, and probabilistic inference to find the communities
        that actually exist in the follow graph.
      </p>

      <img className="about-infographic" src="/about/5-full-pipeline.png" alt="Full pipeline: follow graph to your card" />

      <section className="about-section">
        <h2>The Base Signal: Follow Graph</h2>
        <img className="about-infographic" src="/about/1-follow-graph.png" alt="Follow graph to adjacency matrix" />
        <p>
          We start with who follows whom &mdash; 95,057 accounts and 319,771 edges. The follow
          graph is represented as a sparse adjacency matrix. For accounts with incomplete data,
          we apply inverse-probability edge weighting to correct for partial observability &mdash;
          if we only see 40% of someone's follows, the edges we do see get upweighted.
        </p>
      </section>

      <section className="about-section">
        <h2>Spectral Embedding + Hierarchical Clustering</h2>
        <img className="about-infographic" src="/about/2-spectral-embedding.png" alt="Laplacian to eigenvectors to clusters" />
        <p>
          We build a normalized graph Laplacian from the adjacency matrix and extract its
          top eigenvectors. These eigenvectors give every account a position in a
          high-dimensional space where graph-similar accounts are nearby. We then run Ward
          hierarchical clustering on this embedding, creating a dendrogram of nested communities
          at different scales. For large graphs, BIRCH-style micro-clusters are used as a first
          pass before the full hierarchy.
        </p>
        <p>
          Soft memberships are derived from distances to cluster centroids &mdash; accounts near
          a boundary get partial membership in multiple communities. Louvain modularity
          optimization provides a secondary structure signal that can be blended in.
        </p>
      </section>

      <section className="about-section">
        <h2>Named Communities: NMF over TF-IDF</h2>
        <img className="about-infographic" src="/about/3-nmf-decomposition.png" alt="NMF matrix factorization for communities" />
        <p>
          The named communities you see on your card come from a separate process. We build a
          behavioral feature matrix: each row is an account, columns are who they follow and
          who they retweet. We apply TF-IDF weighting so generic signals (following huge accounts)
          matter less than distinctive ones (following niche accounts that separate one subculture
          from another).
        </p>
        <p>
          Non-negative Matrix Factorization (NMF) then decomposes this into:
        </p>
        <ul>
          <li><strong>W</strong> &mdash; account-to-community weights (how strongly each account belongs to each community)</li>
          <li><strong>H</strong> &mdash; community-to-feature weights (what defines each community: top follow targets, top RT targets)</li>
        </ul>
        <p>
          These machine-generated communities are then curated by humans &mdash; named, colored,
          described. The math finds natural groupings; humans give them meaning.
        </p>
      </section>

      <section className="about-section">
        <h2>Label Propagation: Spreading Knowledge Through the Graph</h2>
        <img className="about-infographic" src="/about/4-label-propagation.png" alt="Color spreading from seed nodes through the network" />
        <p>
          For the ~9,000 accounts that aren't directly classified, we use harmonic label
          propagation &mdash; a Gaussian Random Field (GRF) style Laplacian solve that spreads
          known community labels through the network. The algorithm also estimates uncertainty:
          accounts at community boundaries or far from labeled seeds get lower confidence scores.
        </p>
        <p>
          If your card is in grayscale, it means your community placement comes from this
          propagation layer &mdash; based on your position in the network rather than direct
          analysis of your tweets. Contributing your Twitter data lets us run the full
          classification pipeline on your account, producing a richer and more accurate
          community profile.
        </p>
      </section>

      <section className="about-section">
        <h2>What "Enriching" Your Card Means</h2>
        <p>
          A grayscale card is based on graph position alone. When you contribute your tweet data,
          we can:
        </p>
        <ul>
          <li>Classify your tweets on the simulacrum axis (truth-tracking, persuasion, signaling, pattern)</li>
          <li>Build a content-aware fingerprint from your posting and liking patterns</li>
          <li>Compute direct NMF membership from your behavioral signals</li>
          <li>Give you a full-color card with higher-confidence community placement</li>
        </ul>
        <p>
          The difference between a grayscale and color card isn't just visual &mdash; it reflects
          genuinely deeper analysis.
        </p>
      </section>

      <section className="about-section">
        <h2>Local Signals We Use</h2>
        <div className="about-signals">
          <span className="signal-tag">Mutual-edge ratio</span>
          <span className="signal-tag">Community density</span>
          <span className="signal-tag">Tag entropy</span>
          <span className="signal-tag">Degree variance</span>
          <span className="signal-tag">Bridge membership</span>
          <span className="signal-tag">Personalized PageRank</span>
          <span className="signal-tag">Neighbor overlap</span>
          <span className="signal-tag">Community affinity</span>
          <span className="signal-tag">Shortest-path distance</span>
          <span className="signal-tag">Spectral embedding</span>
          <span className="signal-tag">Louvain modularity</span>
          <span className="signal-tag">NMF factorization</span>
          <span className="signal-tag">GRF propagation</span>
          <span className="signal-tag">Uncertainty estimation</span>
        </div>
      </section>

      <section className="about-section">
        <h2>Is This Validated?</h2>
        <p>
          There isn't one single "true" partition hiding in the graph. For this project,
          the relevant notion of truth is: does the carving match curator-labeled examples,
          does it abstain when it should, and does it help find real community members faster
          than simpler methods.
        </p>
        <p>
          The fancy math is only justified if it beats dumb baselines and improves curation
          throughput. Otherwise it's overkill. We validate with stability analysis (ARI under
          perturbation), propagation sanity checks (convergence, abstain rates, Louvain purity),
          and pipeline integrity tests.
        </p>
      </section>

      <section className="about-section about-cta">
        <h2>Open Source</h2>
        <p>
          The entire pipeline is open source. You can clone the repo, feed your own data,
          and build your own community map.
        </p>
        <a href="https://github.com/aditya/tpot-analyzer" target="_blank" rel="noopener noreferrer"
           className="about-repo-link">
          View the code on GitHub &rarr;
        </a>
      </section>

      <div className="about-footer">
        <a href="/">Back to Find My Ingroup</a>
      </div>
    </div>
  )
}
