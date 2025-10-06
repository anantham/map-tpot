import React, {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import { fetchGraphData } from "./data";

const fetcher = (url) => fetch(url).then((res) => res.json());
const DEFAULT_PRESETS = {
  "Adi's Seeds": [
    "prerationalist",
    "gptbrooke",
    "the_wilderless",
    "nosilverv",
    "qorprate",
    "vividvoid_",
    "pli_cachete",
    "goblinodds",
    "eigenrobot",
    "pragueyerrr",
    "exgenesis",
    "becomingcritter",
    "astridwilde1",
    "malcolm_ocean",
    "m_ashcroft",
    "visakanv",
    "drmaciver",
    "tasshinfogleman"
  ]
};

const COLORS = {
  baseNode: "#a5b4fc",
  seedNode: "#fde68a",
  selectedNode: "#f472b6",
  neighborNode: "#5eead4",
  shadowNode: "#94a3b8",
  mutualEdge: "rgba(224, 242, 254, 0.92)",
  oneWayEdge: "rgba(125, 211, 252, 0.7)",
  selectedEdge: "#fb923c",
  neighborEdge: "#facc15"
};

const EMPTY_METRICS = Object.freeze({});

const normalizeScores = (scores = {}) => {
  const entries = Object.entries(scores).map(([key, value]) => [key, value ?? 0]);
  if (!entries.length) return {};
  const values = entries.map(([, value]) => value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) {
    return Object.fromEntries(entries.map(([key]) => [key, 0]));
  }
  return Object.fromEntries(
    entries.map(([key, value]) => [key, (value - min) / (max - min)])
  );
};

const toLowerSet = (items = []) => {
  const set = new Set();
  items.forEach((item) => {
    if (!item) return;
    set.add(String(item).toLowerCase());
  });
  return set;
};

export default function GraphExplorer({ dataUrl = "/analysis_output.json" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const getData = async () => {
      try {
        const graphData = await fetchGraphData();
        setData(graphData);
      } catch (err) {
        setError(err);
      }
    };
    getData();
  }, []);

  const mutate = async () => {
    try {
      const graphData = await fetchGraphData();
      setData(graphData);
    } catch (err) {
      setError(err);
    }
  };
  const [panelOpen, setPanelOpen] = useState(true);
  const [mutualOnly, setMutualOnly] = useState(true);
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });
  const [linkDistance, setLinkDistance] = useState(140);
  const [chargeStrength, setChargeStrength] = useState(-220);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [seedTextarea, setSeedTextarea] = useState("");
  const [customSeeds, setCustomSeeds] = useState([]);
  const [presetName, setPresetName] = useState("Adi's Seeds");
  const [includeShadows, setIncludeShadows] = useState(true);

  const [subgraphSize, setSubgraphSize] = useState(50);

  const graphRef = useRef(null);

  useEffect(() => {
    console.debug("[GraphExplorer] control panel open:", panelOpen);
  }, [panelOpen]);

  const resolvedSeeds = useMemo(() => {
    const seedSet = toLowerSet(data?.seeds);
    const resolvedSet = toLowerSet(data?.resolved_seeds);
    const combined = new Set([...seedSet, ...resolvedSet]);
    return combined;
  }, [data]);

  const customSeedSet = useMemo(() => toLowerSet(customSeeds), [customSeeds]);
  const effectiveSeedSet = useMemo(() => new Set([...resolvedSeeds, ...customSeedSet]), [resolvedSeeds, customSeedSet]);

  const metrics = data?.metrics ?? EMPTY_METRICS;

  const tpotnessScores = useMemo(() => {
    if (!metrics || !data?.graph?.nodes) return {};

    const followedBySeeds = {};
    const totalSeeds = effectiveSeedSet.size;

    data.graph.edges.forEach(edge => {
      const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;

      if (effectiveSeedSet.has(sourceId.toLowerCase())) {
        followedBySeeds[targetId] = (followedBySeeds[targetId] || 0) + 1;
      }
    });

    const normPR = normalizeScores(metrics.pagerank);
    const normFollowedBySeeds = normalizeScores(followedBySeeds);

    const nodes = new Set([
      ...Object.keys(normPR),
      ...Object.keys(normFollowedBySeeds),
    ]);

    const alpha = weights.pr; // Using the 'pr' weight as alpha for now

    return Array.from(nodes).reduce((acc, node) => {
      const score =
        alpha * (normPR[node] ?? 0) +
        (1 - alpha) * (normFollowedBySeeds[node] ?? 0);
      acc[node] = score;
      return acc;
    }, {});
  }, [metrics, data, effectiveSeedSet, weights.pr]);

  const { graphData, graphStats } = useMemo(() => {
    if (!data) {
      return {
        graphData: { nodes: [], links: [] },
        graphStats: {
          totalNodes: 0,
          totalDirectedEdges: 0,
          totalUndirectedEdges: 0,
          mutualEdgeCount: 0,
          visibleEdges: 0,
          visibleMutualEdges: 0,
          visibleShadowNodes: 0,
          visibleShadowEdges: 0
        }
      };
    }

    const nodesMeta = data.graph?.nodes || {};
    const edges = data.graph?.edges || [];
    const canonicalId = (value) => {
      if (value && typeof value === "object") {
        if (value.id !== undefined && value.id !== null) {
          return String(value.id);
        }
        return "";
      }
      if (value === undefined || value === null) return "";
      return String(value);
    };

    const isSeedId = (rawId) => {
      const canonical = canonicalId(rawId);
      if (!canonical) return false;
      const canonicalLower = canonical.toLowerCase();
      if (effectiveSeedSet.has(canonicalLower)) return true;
      const meta = nodesMeta[canonical];
      if (meta?.username) {
        const handleLower = String(meta.username).toLowerCase();
        if (effectiveSeedSet.has(handleLower)) return true;
      }
      return false;
    };

    const mutualAdjacency = new Map();
    const mutualCounts = new Map();
    const seedTouchCounts = new Map();
    let mutualEdgeCount = 0;

    edges.forEach((edge) => {
      const source = canonicalId(edge.source);
      const target = canonicalId(edge.target);
      if (!source || !target) return;
      if (edge.mutual) {
        mutualEdgeCount += 1;
        if (!mutualAdjacency.has(source)) mutualAdjacency.set(source, new Set());
        if (!mutualAdjacency.has(target)) mutualAdjacency.set(target, new Set());
        mutualAdjacency.get(source).add(target);
        mutualAdjacency.get(target).add(source);

        mutualCounts.set(source, (mutualCounts.get(source) || 0) + 1);
        mutualCounts.set(target, (mutualCounts.get(target) || 0) + 1);

        if (isSeedId(source)) {
          seedTouchCounts.set(target, (seedTouchCounts.get(target) || 0) + 1);
        }
        if (isSeedId(target)) {
          seedTouchCounts.set(source, (seedTouchCounts.get(source) || 0) + 1);
        }
      }
    });

    const nodeIdSet = new Set([
      ...Object.keys(nodesMeta),
      ...Object.keys(tpotnessScores)
    ]);
    edges.forEach((edge) => {
      const source = canonicalId(edge.source);
      const target = canonicalId(edge.target);
      if (source) nodeIdSet.add(source);
      if (target) nodeIdSet.add(target);
    });
    const nodeIds = Array.from(nodeIdSet);

    const distances = new Map();
    const queue = [];
    nodeIds.forEach((id) => {
      if (isSeedId(id)) {
        distances.set(id, 0);
        queue.push(id);
      }
    });

    while (queue.length) {
      const current = queue.shift();
      const neighbors = mutualAdjacency.get(current);
      if (!neighbors) continue;
      neighbors.forEach((neighbor) => {
        if (!nodeIdSet.has(neighbor)) return;
        if (distances.has(neighbor)) return;
        const distance = distances.get(current) + 1;
        distances.set(neighbor, distance);
        queue.push(neighbor);
      });
    }

    let maxMutualCount = 0;
    mutualCounts.forEach((value) => {
      if (value > maxMutualCount) maxMutualCount = value;
    });

    let maxSeedTouch = 0;
    seedTouchCounts.forEach((value) => {
      if (value > maxSeedTouch) maxSeedTouch = value;
    });

    const topNIds = Object.entries(tpotnessScores)
      .sort(([, a], [, b]) => b - a)
      .slice(0, subgraphSize)
      .map(([id]) => id);

    const allowedNodeSet = new Set([...topNIds, ...effectiveSeedSet]);

    const nodes = nodeIds.map((rawId) => {
      const id = String(rawId);
      if (!allowedNodeSet.has(id)) return null;
      const meta = nodesMeta[id] || {};
      const usernameLower = meta.username ? String(meta.username).toLowerCase() : null;
      const idLower = id.toLowerCase();
      const isSeed =
        effectiveSeedSet.has(idLower) ||
        (usernameLower ? effectiveSeedSet.has(usernameLower) : false);
      const isShadow = Boolean(meta.shadow || meta.provenance === "shadow" || id.startsWith("shadow:"));
      if (!includeShadows && isShadow) {
        return null;
      }
      const mutualCount = mutualCounts.get(id) || 0;
      const seedTouchCount = seedTouchCounts.get(id) || 0;
      const hopDistance = distances.has(id) ? distances.get(id) : Number.POSITIVE_INFINITY;
      const distanceScore = Number.isFinite(hopDistance) ? 1 / (hopDistance + 1) : 0;
      const mutualScore = maxMutualCount > 0 ? mutualCount / maxMutualCount : 0;
      const seedTouchScore = maxSeedTouch > 0 ? seedTouchCount / maxSeedTouch : 0;
      const inGroupScore = Math.min(
        1,
        distanceScore * 0.6 + mutualScore * 0.25 + seedTouchScore * 0.15 + (isSeed ? 0.1 : 0)
      );
      const tpotnessScore = tpotnessScores[id] ?? 0;
      const val = 10 + inGroupScore * 26 + (isSeed ? 6 : 0) + (isShadow ? 2 : 0);

      return {
        id,
        idLower,
        val,
        hopDistance,
        mutualCount,
        seedTouchCount,
        inGroupScore,
        provenance: meta.provenance || (isShadow ? "shadow" : "archive"),
        shadow: isShadow,
        community: metrics.communities?.[id],
        pagerank: metrics.pagerank?.[id],
        betweenness: metrics.betweenness?.[id],
        engagement: metrics.engagement?.[id],
        tpotnessScore: tpotnessScore,
        isSeed,
        neighbors: [],
        ...meta
      };
    }).filter(Boolean);



    const filteredLinks = edges
      .filter((edge) => (mutualOnly ? edge.mutual : true))
      .filter((edge) => allowedNodeSet.has(edge.source) && allowedNodeSet.has(edge.target))
      .map((edge) => {
        const source = canonicalId(edge.source);
        const target = canonicalId(edge.target);
        return {
          source,
          target,
          mutual: !!edge.mutual
        };
      });

    const visibleMutualEdges = filteredLinks.reduce(
      (count, link) => (link.mutual ? count + 1 : count),
      0
    );

    return {
      graphData: {
        nodes,
        links: filteredLinks
      },
      graphStats: {
        totalNodes: data.graph?.directed_nodes ?? nodeIds.length,
        totalDirectedEdges: data.graph?.directed_edges ?? edges.length,
        totalUndirectedEdges: data.graph?.undirected_edges ?? 0,
        mutualEdgeCount,
        visibleEdges: filteredLinks.length,
        visibleMutualEdges,
        visibleShadowNodes: nodes.filter((node) => node.shadow).length,
        visibleShadowEdges: filteredLinks.filter((edge) => edge.shadow).length
      }
    };
  }, [data, tpotnessScores, effectiveSeedSet, includeShadows, metrics, mutualOnly]);

  useEffect(() => {
    if (!graphData.nodes.length) return;
    console.debug(
      "[GraphExplorer] graph loaded",
      {
        nodes: graphStats.totalNodes,
        visibleEdges: graphStats.visibleEdges,
        mutualEdges: graphStats.visibleMutualEdges,
        shadowNodes: graphStats.visibleShadowNodes,
        shadowEdges: graphStats.visibleShadowEdges,
        mutualOnly
      }
    );
  }, [graphData.nodes.length, graphStats.totalNodes, graphStats.visibleEdges, graphStats.visibleMutualEdges, graphStats.visibleShadowEdges, graphStats.visibleShadowNodes, mutualOnly]);

  const nodeLookup = useMemo(() => {
    const map = new Map();
    graphData.nodes.forEach((node) => {
      map.set(node.id, node);
      map.set(node.idLower, node);
      if (node.username) {
        map.set(String(node.username).toLowerCase(), node);
      }
    });
    return map;
  }, [graphData.nodes]);

  const neighborMap = useMemo(() => {
    const map = new Map();
    graphData.links.forEach((edge) => {
      const source = typeof edge.source === "object" ? edge.source.id : edge.source;
      const target = typeof edge.target === "object" ? edge.target.id : edge.target;
      if (!map.has(source)) map.set(source, new Set());
      if (!map.has(target)) map.set(target, new Set());
      map.get(source).add(target);
      map.get(target).add(source);
    });
    return map;
  }, [graphData.links]);

  const topEntries = useMemo(() => {
    return Object.entries(tpotnessScores)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
  }, [tpotnessScores]);

  const seedList = useMemo(() => {
    const unique = new Map();
    graphData.nodes.forEach((node) => {
      if (effectiveSeedSet.has(node.idLower)) {
        unique.set(node.idLower, node);
      }
    });
    customSeedSet.forEach((seed) => {
      if (!unique.has(seed)) {
        unique.set(seed, { id: seed, username: seed, display_name: seed, idLower: seed });
      }
    });
    return Array.from(unique.values());
  }, [graphData.nodes, effectiveSeedSet, customSeedSet]);

  const totalWeight = weights.pr + weights.bt + weights.eng;
  const selectedNeighbors = selectedNodeId ? neighborMap.get(selectedNodeId) || new Set() : new Set();

  const getLinkStyle = (link) => {
    const sourceId = typeof link.source === "object" ? link.source.id : link.source;
    const targetId = typeof link.target === "object" ? link.target.id : link.target;
    const isSelectedEdge =
      selectedNodeId && (sourceId === selectedNodeId || targetId === selectedNodeId);
    if (isSelectedEdge) {
      return { color: COLORS.selectedEdge, width: 2.6, dash: [] };
    }

    const connectsNeighbors =
      selectedNodeId && selectedNeighbors.has(sourceId) && selectedNeighbors.has(targetId);
    if (connectsNeighbors) {
      return { color: COLORS.neighborEdge, width: 2.2, dash: [] };
    }

    if (link.shadow) {
      return { color: "rgba(203, 213, 225, 0.7)", width: 1.2, dash: [3, 5] };
    }

    if (link.mutual) {
      return { color: COLORS.mutualEdge, width: 1.7, dash: [] };
    }

    return { color: COLORS.oneWayEdge, width: 1.3, dash: [6, 4] };
  };

  useEffect(() => {
    if (!graphRef.current) return;
    const charge = graphRef.current.d3Force("charge");
    if (charge && typeof charge.strength === "function") {
      charge.strength(chargeStrength);
      graphRef.current.d3ReheatSimulation();
    }
  }, [chargeStrength, graphData]);

  useEffect(() => {
    if (!graphRef.current) return;
    const linkForce = graphRef.current.d3Force("link");
    if (linkForce && typeof linkForce.distance === "function") {
      linkForce.distance(() => linkDistance);
      graphRef.current.d3ReheatSimulation();
    }
  }, [linkDistance, graphData]);

  const handleWeightChange = (key) => (event) => {
    const value = Number(event.target.value);
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const handlePresetChange = (event) => {
    const name = event.target.value;
    setPresetName(name);
    const presetSeeds = DEFAULT_PRESETS[name] || [];
    setCustomSeeds(presetSeeds);
    setSeedTextarea(presetSeeds.join("\n"));
  };

  const handleApplyCustomSeeds = () => {
    const lines = seedTextarea
      .split(/[,\n]/)
      .map((line) => line.trim())
      .filter(Boolean);
    setCustomSeeds(lines);
  };

  const handleDownloadCsv = () => {
    const header = [
      "id",
      "display_name",
      "username",
      "pagerank",
      "betweenness",
      "engagement",
      "tpotness",
      "community",
      "is_seed"
    ];
    const rows = header.join(",") +
      "\n" +
      graphData.nodes
        .map((node) => {
          const tpotness = tpotnessScores[node.id] ?? 0;
          return [
            node.id,
            JSON.stringify(node.display_name || ""),
            JSON.stringify(node.username || ""),
            node.pagerank ?? 0,
            node.betweenness ?? 0,
            node.engagement ?? 0,
            tpotness,
            node.community ?? "",
            node.isSeed
          ].join(",");
        })
        .join("\n");
    const blob = new Blob([rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "tpot-status.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleRefreshData = async () => {
    await mutate();
  };

  if (error) return <div className="status-message">Error loading graph.</div>;
  if (!data) return <div className="status-message">Loading…</div>;

  return (
    <div className="layout">
      <div className={`control-panel ${panelOpen ? "open" : "collapsed"}`}>
        <button
          className={`panel-handle ${panelOpen ? "open" : "collapsed"}`}
          onClick={() => setPanelOpen((open) => !open)}
          aria-pressed={panelOpen}
          aria-label={panelOpen ? "Collapse controls" : "Expand controls"}
        >
          <span className="handle-label">Controls</span>
          <span className="handle-icon">{panelOpen ? "◀" : "▶"}</span>
        </button>
        {panelOpen && (
          <div className="panel-content">
            <h1>TPOT Graph Explorer</h1>
            <div className="panel-actions">
              <button onClick={handleDownloadCsv}>Download CSV</button>
              <button onClick={handleRefreshData}>Refresh Data</button>
            </div>

            <section>
              <h2>Graph summary</h2>
              <div className="summary-grid">
                <div>
                  <span className="summary-label">Nodes</span>
                  <span className="summary-value">{graphStats.totalNodes}</span>
                </div>
                <div>
                  <span className="summary-label">Visible edges</span>
                  <span className="summary-value">{graphStats.visibleEdges}</span>
                </div>
                <div>
                  <span className="summary-label">Directed / Undirected</span>
                  <span className="summary-value">
                    {graphStats.totalDirectedEdges} / {graphStats.totalUndirectedEdges}
                  </span>
                </div>
                <div>
                  <span className="summary-label">Mutual edges (view / total)</span>
                  <span className="summary-value">
                    {graphStats.visibleMutualEdges} / {graphStats.mutualEdgeCount}
                  </span>
                </div>
                <div>
                  <span className="summary-label">Shadow nodes visible</span>
                  <span className="summary-value">{graphStats.visibleShadowNodes}</span>
                </div>
                <div>
                  <span className="summary-label">Shadow edges visible</span>
                  <span className="summary-value">{graphStats.visibleShadowEdges}</span>
                </div>
              </div>
            </section>

            <section>
              <h2>Legend</h2>
              <ul className="legend">
                <li><span className="legend-color seed" /> Seed node</li>
                <li><span className="legend-color selected" /> Selected node</li>
                <li><span className="legend-color neighbor" /> Neighbor</li>
                <li><span className="legend-color shadow" /> Shadow node</li>
              </ul>
            </section>

            <section>
              <h2>Mutual edges</h2>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={mutualOnly}
                  onChange={(e) => setMutualOnly(e.target.checked)}
                />
                Show mutual-only edges
              </label>
            </section>

            <section>
              <h2>Shadow enrichment</h2>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={includeShadows}
                  onChange={(e) => setIncludeShadows(e.target.checked)}
                />
                Display shadow nodes (hybrid/API)
              </label>
              <small>
                Toggle to focus on archive-only graph. Shadow nodes load from enrichment cache and are outlined in slate.
              </small>
            </section>

           <section>
             <h2>Status weights</h2>
             <div className="slider">
               <label>α (Alpha) {weights.pr.toFixed(2)}</label>
               <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.pr}
                  onChange={handleWeightChange("pr")}
                />
              </div>
            </section>

            <section>
              <h2>Layout</h2>
              <div className="slider">
                <label>Subgraph Size (N) {subgraphSize}</label>
                <input
                  type="range"
                  min="10"
                  max="500"
                  value={subgraphSize}
                  onChange={(e) => setSubgraphSize(Number(e.target.value))}
                />
              </div>
              <div className="slider">
                <label>Link distance {linkDistance}</label>
                <input
                  type="range"
                  min="30"
                  max="320"
                  value={linkDistance}
                  onChange={(e) => setLinkDistance(Number(e.target.value))}
                />
              </div>
              <div className="slider">
                <label>Charge strength {chargeStrength}</label>
                <input
                  type="range"
                  min="-500"
                  max="-50"
                  value={chargeStrength}
                  onChange={(e) => setChargeStrength(Number(e.target.value))}
                />
              </div>
            </section>

            <section>
              <h2>Seed presets</h2>
              <select value={presetName} onChange={handlePresetChange}>
                {Object.keys(DEFAULT_PRESETS).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
                <option value="Custom">Custom</option>
              </select>
              <textarea
                placeholder="Enter handles or IDs, one per line"
                value={seedTextarea}
                onChange={(e) => setSeedTextarea(e.target.value)}
                rows={6}
              />
              <button onClick={handleApplyCustomSeeds}>Apply seeds</button>
            </section>

            <section>
              <h2>Top accounts</h2>
              <ol className="top-list">
                {topEntries.map(([id, score]) => {
                  const node = nodeLookup.get(id) || {};
                  const label = node.display_name || node.username || id;
                  return (
                    <li
                      key={`${id}`}
                      onMouseEnter={() => setSelectedNodeId(node.id)}
                      onMouseLeave={() => setSelectedNodeId(null)}
                      onClick={() => setSelectedNodeId(node.id)}
                    >
                      <strong>{label}</strong>
                      <div className="top-metrics">
                        {(score * 100).toFixed(1)} · PR {(node.pagerank ?? 0).toFixed(3)} · BT {(node.betweenness ?? 0).toFixed(3)} · EN {(node.engagement ?? 0).toFixed(3)}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>

            <section>
              <h2>Seed accounts ({seedList.length})</h2>
              <ul className="seed-list">
                {seedList.map((node) => (
                  <li key={`${node.id}-seed`}>
                    {node.display_name || node
.username || node.id}
                  </li>
                ))}
              </ul>
            </section>

            {selectedNodeId && (
              <section>
                <h2>Selected node</h2>
                <div className="selected-card">
                  {(() => {
                    const node = nodeLookup.get(selectedNodeId) || {};
                    const tpotness = tpotnessScores[node.id] ?? 0;
                    return (
                      <>
                        <h3>{node.display_name || node.username || node.id}</h3>
                        <p>ID: {node.id}</p>
                        <p>Provenance: {node.provenance || (node.shadow ? "shadow" : "archive")}</p>
                        <p>TPOT-ness: {(tpotness * 100).toFixed(1)}</p>
                        <p>Pagerank: {(node.pagerank ?? 0).toFixed(4)}</p>
                        <p>Betweenness: {(node.betweenness ?? 0).toFixed(4)}</p>
                        <p>Engagement: {(node.engagement ?? 0).toFixed(4)}</p>
                        <p>Followers: {node.num_followers ?? "?"}</p>
                        <p>Following: {node.num_following ?? "?"}</p>
                        <p>Location: {node.location || "—"}</p>
                        <p>Bio: {node.bio || "—"}</p>
                        {node.shadow && node.shadow_scrape_stats && (
                          <p>Shadow stats: {JSON.stringify(node.shadow_scrape_stats)}</p>
                        )}
                      </>
                    );
                  })()}
                </div>
              </section>
            )}
          </div>
        )}
      </div>

      <div className="graph-container">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeRelSize={6}
          enableNodeDrag={false}
          nodeColor={(node) => {
            if (node.id === selectedNodeId) return COLORS.selectedNode;
            if (selectedNeighbors.has(node.id)) return COLORS.neighborNode;
            if (node.isSeed) return COLORS.seedNode;
            if (node.shadow) return COLORS.shadowNode;
            return COLORS.baseNode;
          }}
          linkColor={(link) => getLinkStyle(link).color}
          linkWidth={(link) => getLinkStyle(link).width}
          linkDirectionalParticles={(link) => (link.mutual ? 0 : 2)}
          linkDirectionalParticleWidth={1.6}
          linkDirectionalParticleColor={(link) => getLinkStyle(link).color}
          linkCanvasObjectMode={() => "replace"}
          linkCanvasObject={(link, ctx) => {
            if (!link.source || !link.target) return;
            const { color, width, dash } = getLinkStyle(link);
            const from = link.source;
            const to = link.target;
            ctx.save();
            ctx.beginPath();
            ctx.lineWidth = width;
            ctx.strokeStyle = color;
            ctx.setLineDash(dash);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);
            ctx.stroke();
            ctx.restore();
          }}
          nodeLabel={(node) => {
            const tpotness = tpotnessScores[node.id] ?? 0;
            const name = node.display_name || node.username || node.id;
            const distanceLabel = Number.isFinite(node.hopDistance)
              ? node.hopDistance
              : "∞";
            const provenanceLabel = node.provenance || (node.shadow ? "shadow" : "archive");
            return `${name}\nProvenance: ${provenanceLabel}\nTPOT-ness: ${(tpotness * 100).toFixed(1)}\nMutual edges: ${node.mutualCount}\nSeed touches: ${node.seedTouchCount}\nHop distance: ${distanceLabel}\nPageRank: ${(node.pagerank ?? 0).toFixed(3)}\nBetweenness: ${(node.betweenness ?? 0).toFixed(3)}\nEngagement: ${(node.engagement ?? 0).toFixed(3)}`;
          }}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.display_name || node.username || node.id;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "rgba(248, 250, 252, 0.92)";
            ctx.fillText(label, node.x + 8, node.y + fontSize / 2);
          }}
          onNodeClick={(node) => {
            setSelectedNodeId(node.id === selectedNodeId ? null : node.id);
          }}
        />
      </div>
    </div>
  );
}