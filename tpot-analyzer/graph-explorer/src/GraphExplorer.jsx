import React, {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import useSWR from "swr";

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
  const { data, error, mutate } = useSWR(dataUrl, fetcher, { suspense: false });
  const [panelOpen, setPanelOpen] = useState(true);
  const [mutualOnly, setMutualOnly] = useState(true);
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });
  const [linkDistance, setLinkDistance] = useState(140);
  const [chargeStrength, setChargeStrength] = useState(-220);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [seedTextarea, setSeedTextarea] = useState("");
  const [customSeeds, setCustomSeeds] = useState([]);
  const [presetName, setPresetName] = useState("Adi's Seeds");

  const graphRef = useRef(null);

  const resolvedSeeds = useMemo(() => {
    const seedSet = toLowerSet(data?.seeds);
    const resolvedSet = toLowerSet(data?.resolved_seeds);
    const combined = new Set([...seedSet, ...resolvedSet]);
    return combined;
  }, [data]);

  const customSeedSet = useMemo(() => toLowerSet(customSeeds), [customSeeds]);
  const effectiveSeedSet = useMemo(() => new Set([...resolvedSeeds, ...customSeedSet]), [resolvedSeeds, customSeedSet]);

  const metrics = data?.metrics || {};

  const compositeScores = useMemo(() => {
    if (!metrics) return {};
    const normPR = normalizeScores(metrics.pagerank);
    const normBT = normalizeScores(metrics.betweenness);
    const normEG = normalizeScores(metrics.engagement);
    const nodes = new Set([
      ...Object.keys(normPR),
      ...Object.keys(normBT),
      ...Object.keys(normEG)
    ]);
    const total = weights.pr + weights.bt + weights.eng || 1;
    return Array.from(nodes).reduce((acc, node) => {
      const score =
        (weights.pr * (normPR[node] ?? 0) +
          weights.bt * (normBT[node] ?? 0) +
          weights.eng * (normEG[node] ?? 0)) /
        total;
      acc[node] = score;
      return acc;
    }, {});
  }, [metrics, weights]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const nodesMeta = data.graph?.nodes || {};
    const edges = data.graph?.edges || [];
    const nodeIds = Object.keys(compositeScores);
    return {
      nodes: nodeIds.map((id) => {
        const meta = nodesMeta[id] || {};
        const username = meta.username?.toLowerCase();
        const idLower = id.toLowerCase();
        const isSeed =
          effectiveSeedSet.has(idLower) ||
          (username && effectiveSeedSet.has(username));
        return {
          id,
          idLower,
          val: (compositeScores[id] ?? 0) * 24 + 6,
          community: metrics.communities?.[id],
          pagerank: metrics.pagerank?.[id],
          betweenness: metrics.betweenness?.[id],
          engagement: metrics.engagement?.[id],
          isSeed,
          neighbors: [],
          ...meta
        };
      }),
      links: edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        mutual: edge.mutual
      }))
    };
  }, [data, compositeScores, effectiveSeedSet, metrics]);

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
    return Object.entries(compositeScores)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
  }, [compositeScores]);

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
      "composite",
      "community",
      "is_seed"
    ];
    const rows = header.join(",") +
      "\n" +
      graphData.nodes
        .map((node) => {
          const composite = compositeScores[node.id] ?? 0;
          return [
            node.id,
            JSON.stringify(node.display_name || ""),
            JSON.stringify(node.username || ""),
            node.pagerank ?? 0,
            node.betweenness ?? 0,
            node.engagement ?? 0,
            composite,
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
        <button className="collapse-btn" onClick={() => setPanelOpen((open) => !open)}>
          {panelOpen ? "⬅" : "➡"}
        </button>
        {panelOpen && (
          <div className="panel-content">
            <h1>TPOT Graph Explorer</h1>
            <div className="panel-actions">
              <button onClick={handleDownloadCsv}>Download CSV</button>
              <button onClick={handleRefreshData}>Refresh Data</button>
            </div>

            <section>
              <h2>Legend</h2>
              <ul className="legend">
                <li><span className="legend-color seed" /> Seed node</li>
                <li><span className="legend-color selected" /> Selected node</li>
                <li><span className="legend-color neighbor" /> Neighbor</li>
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
              <h2>Status weights</h2>
              <div className="slider">
                <label>PageRank {weights.pr.toFixed(2)}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.pr}
                  onChange={handleWeightChange("pr")}
                />
              </div>
              <div className="slider">
                <label>Betweenness {weights.bt.toFixed(2)}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.bt}
                  onChange={handleWeightChange("bt")}
                />
              </div>
              <div className="slider">
                <label>Engagement {weights.eng.toFixed(2)}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.eng}
                  onChange={handleWeightChange("eng")}
                />
              </div>
              <small>Weights auto-normalized (sum: {totalWeight.toFixed(2)}).</small>
            </section>

            <section>
              <h2>Layout</h2>
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
                    const composite = compositeScores[node.id] ?? 0;
                    return (
                      <>
                        <h3>{node.display_name || node.username || node.id}</h3>
                        <p>ID: {node.id}</p>
                        <p>Composite: {(composite * 100).toFixed(1)}</p>
                        <p>Pagerank: {(node.pagerank ?? 0).toFixed(4)}</p>
                        <p>Betweenness: {(node.betweenness ?? 0).toFixed(4)}</p>
                        <p>Engagement: {(node.engagement ?? 0).toFixed(4)}</p>
                        <p>Followers: {node.num_followers ?? "?"}</p>
                        <p>Following: {node.num_following ?? "?"}</p>
                        <p>Location: {node.location || "—"}</p>
                        <p>Bio: {node.bio || "—"}</p>
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
            if (node.id === selectedNodeId) return "#f471b5";
            if (selectedNeighbors.has(node.id)) return "#22d3ee";
            if (node.isSeed) return "#facc15";
            return "#60a5fa";
          }}
          linkColor={(link) => {
            const sourceId = typeof link.source === "object" ? link.source.id : link.source;
            const targetId = typeof link.target === "object" ? link.target.id : link.target;
            if (selectedNodeId && sourceId && targetId) {
              if (sourceId === selectedNodeId || targetId === selectedNodeId) {
                return "#f97316";
              }
              if (selectedNeighbors.has(sourceId) && selectedNeighbors.has(targetId)) {
                return "#f59e0b";
              }
              return "#334155";
            }
            return link.mutual ? "#94a3b8" : "#475569";
          }}
          linkWidth={(link) => {
            const sourceId = typeof link.source === "object" ? link.source.id : link.source;
            const targetId = typeof link.target === "object" ? link.target.id : link.target;
            if (selectedNodeId && (sourceId === selectedNodeId || targetId === selectedNodeId)) {
              return 2.5;
            }
            return link.mutual ? 1.6 : 0.6;
          }}
          linkDirectionalParticles={mutualOnly ? 0 : 2}
          linkDirectionalParticleWidth={2}
          nodeLabel={(node) => {
            const composite = compositeScores[node.id] ?? 0;
            const name = node.display_name || node.username || node.id;
            return `${name}\nComposite: ${(composite * 100).toFixed(1)}\nPageRank: ${(node.pagerank ?? 0).toFixed(3)}\nBetweenness: ${(node.betweenness ?? 0).toFixed(3)}\nEngagement: ${(node.engagement ?? 0).toFixed(3)}`;
          }}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.display_name || node.username || node.id;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "#e2e8f0";
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
