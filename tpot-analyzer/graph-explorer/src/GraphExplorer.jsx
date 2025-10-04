import React, { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import useSWR from "swr";

const fetcher = (url) => fetch(url).then((res) => res.json());

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

export default function GraphExplorer({ dataUrl = "/analysis_output.json" }) {
  const { data, error } = useSWR(dataUrl, fetcher);
  const [mutualOnly, setMutualOnly] = useState(true);
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });
  const [linkDistance, setLinkDistance] = useState(120);
  const [chargeStrength, setChargeStrength] = useState(-200);
  const graphRef = useRef(null);

  const resolvedSeeds = useMemo(() => {
    const seeds = new Set();
    (data?.seeds || []).forEach((seed) => seeds.add(String(seed).toLowerCase()));
    (data?.resolved_seeds || []).forEach((seed) =>
      seeds.add(String(seed).toLowerCase())
    );
    return seeds;
  }, [data]);

  const compositeScores = useMemo(() => {
    if (!data?.metrics) return {};
    const { pagerank = {}, betweenness = {}, engagement = {} } = data.metrics;

    const normPR = normalizeScores(pagerank);
    const normBT = normalizeScores(betweenness);
    const normEG = normalizeScores(engagement);

    const nodes = new Set([
      ...Object.keys(normPR),
      ...Object.keys(normBT),
      ...Object.keys(normEG),
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
  }, [data, weights]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const { metrics = {}, graph = {} } = data;
    const nodesMeta = graph.nodes || {};
    const edges = graph.edges || [];
    const nodeIds = Object.keys(compositeScores);

    return {
      nodes: nodeIds.map((id) => {
        const meta = nodesMeta[id] || {};
        const username = meta.username?.toLowerCase();
        const isSeed =
          resolvedSeeds.has(id.toLowerCase()) ||
          (username && resolvedSeeds.has(username));
        return {
          id,
          val: (compositeScores[id] ?? 0) * 24 + 6,
          community: metrics.communities?.[id],
          pagerank: metrics.pagerank?.[id],
          betweenness: metrics.betweenness?.[id],
          engagement: metrics.engagement?.[id],
          isSeed,
          ...meta,
        };
      }),
      links: mutualOnly ? edges.filter(({ mutual }) => mutual) : edges,
    };
  }, [data, compositeScores, mutualOnly, resolvedSeeds]);

  const nodeLookup = useMemo(
    () => new Map(graphData.nodes.map((node) => [node.id, node])),
    [graphData.nodes]
  );

  const seedList = useMemo(() => {
    if (!graphData.nodes.length) return [];
    const normalizedLookup = new Map();
    graphData.nodes.forEach((node) => {
      normalizedLookup.set(node.id.toLowerCase(), node);
      if (node.username) {
        normalizedLookup.set(String(node.username).toLowerCase(), node);
      }
    });
    return Array.from(resolvedSeeds).map((seed) => {
      const node = normalizedLookup.get(seed);
      const label = node?.display_name || node?.username || node?.id || seed;
      return { id: node?.id || seed, label };
    });
  }, [graphData.nodes, resolvedSeeds]);

  const topEntries = useMemo(() => {
    return Object.entries(compositeScores)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
  }, [compositeScores]);

  useEffect(() => {
    if (!graphRef.current) return;
    const chargeForce = graphRef.current.d3Force("charge");
    if (chargeForce) {
      chargeForce.strength(chargeStrength);
      graphRef.current.d3ReheatSimulation();
    }
  }, [chargeStrength, graphData]);

  useEffect(() => {
    if (!graphRef.current) return;
    const linkForce = graphRef.current.d3Force("link");
    if (linkForce && linkForce.distance) {
      linkForce.distance(linkDistance);
      graphRef.current.d3ReheatSimulation();
    }
  }, [linkDistance, graphData]);

  const handleWeightChange = (key) => (event) => {
    const value = Number(event.target.value);
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const totalWeight = weights.pr + weights.bt + weights.eng;

  if (error) return <div>Error loading graph.</div>;
  if (!data) return <div>Loading…</div>;

  return (
    <div style={{ display: "flex", gap: 16, height: "100%" }}>
      <div style={{ width: 320, overflowY: "auto", paddingRight: 8 }}>
        <h2>Controls</h2>
        <label style={{ display: "block", marginBottom: 12 }}>
          <input
            type="checkbox"
            checked={mutualOnly}
            onChange={(e) => setMutualOnly(e.target.checked)}
          />{" "}
          Mutual-only edges
        </label>

        <section style={{ marginBottom: 16 }}>
          <h3 style={{ marginBottom: 8 }}>Status weights</h3>
          <label>
            PageRank {weights.pr.toFixed(2)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={weights.pr}
              onChange={handleWeightChange("pr")}
            />
          </label>
          <label>
            Betweenness {weights.bt.toFixed(2)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={weights.bt}
              onChange={handleWeightChange("bt")}
            />
          </label>
          <label>
            Engagement {weights.eng.toFixed(2)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={weights.eng}
              onChange={handleWeightChange("eng")}
            />
          </label>
          <small>Weights are auto-normalized (sum: {totalWeight.toFixed(2)}).</small>
        </section>

        <section style={{ marginBottom: 16 }}>
          <label>
            Link distance {linkDistance}
            <input
              type="range"
              min="30"
              max="300"
              value={linkDistance}
              onChange={(e) => setLinkDistance(Number(e.target.value))}
            />
          </label>
          <label style={{ display: "block", marginTop: 12 }}>
            Charge strength {chargeStrength}
            <input
              type="range"
              min="-500"
              max="-50"
              value={chargeStrength}
              onChange={(e) => setChargeStrength(Number(e.target.value))}
            />
          </label>
        </section>

        <section style={{ marginBottom: 16 }}>
          <h3>Top nodes</h3>
          <ol style={{ paddingLeft: 18 }}>
            {topEntries.map(([id, score]) => {
              const node = nodeLookup.get(id);
              const label = node?.display_name || node?.username || node?.id || id;
              return (
                <li key={id} style={{ marginBottom: 6 }}>
                  <strong>{label}</strong>
                  <div style={{ fontSize: "0.8rem", color: "#475569" }}>
                    Composite {(score * 100).toFixed(1)} · PR {(node?.pagerank ?? 0).toFixed(3)} · BT {(node?.betweenness ?? 0).toFixed(3)} · EN {(node?.engagement ?? 0).toFixed(3)}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section>
          <h3>Seed accounts ({seedList.length})</h3>
          <ul style={{ paddingLeft: 18 }}>
            {seedList.map(({ id, label }) => (
              <li key={id}>{label}</li>
            ))}
          </ul>
        </section>
      </div>

      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        nodeRelSize={6}
        nodeColor={(node) => (node.isSeed ? "#facc15" : "#60a5fa")}
        linkColor={(link) => (link.mutual ? "#94a3b8" : "#cbd5f5")}
        linkWidth={(link) => (link.mutual ? 1.6 : 0.5)}
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
          ctx.fillStyle = "#1f2937";
          ctx.fillText(label, node.x + 8, node.y + fontSize / 2);
        }}
      />
    </div>
  );
}
