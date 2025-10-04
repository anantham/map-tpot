import React, { useMemo, useState } from "react";
import { ForceGraph2D } from "react-force-graph";
import useSWR from "swr";

const fetcher = (url) => fetch(url).then((res) => res.json());

export default function GraphExplorer({ dataUrl = "/analysis_output.json" }) {
  const { data, error } = useSWR(dataUrl, fetcher);
  const [mutualOnly, setMutualOnly] = useState(true);
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });
  const [linkDistance, setLinkDistance] = useState(100);
  const [chargeStrength, setChargeStrength] = useState(-200);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const { metrics } = data;
    const edges = data.graph.edges || [];
    const nodesMeta = data.graph.nodes || {};
    return {
      nodes: Object.entries(metrics.composite).map(([id, score]) => ({
        id,
        val: score * 10 + 2,
        community: metrics.communities[id],
        pagerank: metrics.pagerank[id],
        betweenness: metrics.betweenness[id],
        engagement: metrics.engagement[id],
        ...nodesMeta[id],
      })),
      links: mutualOnly
        ? edges.filter(({ mutual }) => mutual)
        : edges,
    };
  }, [data, mutualOnly, weights]);

  if (error) return <div>Error loading graph</div>;
  if (!data) return <div>Loading…</div>;

  return (
    <div style={{ display: "flex", gap: 16 }}>
      <div style={{ width: 320 }}>
        <h2>Controls</h2>
        <label>
          <input
            type="checkbox"
            checked={mutualOnly}
            onChange={(e) => setMutualOnly(e.target.checked)}
          />
          Mutual-only edges
        </label>
        <div>
          <label>Pagerank weight: {weights.pr.toFixed(2)}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.pr}
            onChange={(e) => setWeights({ ...weights, pr: Number(e.target.value) })}
          />
        </div>
        <div>
          <label>Betweenness weight: {weights.bt.toFixed(2)}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.bt}
            onChange={(e) => setWeights({ ...weights, bt: Number(e.target.value) })}
          />
        </div>
        <div>
          <label>Engagement weight: {weights.eng.toFixed(2)}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.eng}
            onChange={(e) => setWeights({ ...weights, eng: Number(e.target.value) })}
          />
        </div>
        <div>
          <label>Link distance: {linkDistance}</label>
          <input
            type="range"
            min="30"
            max="300"
            value={linkDistance}
            onChange={(e) => setLinkDistance(Number(e.target.value))}
          />
        </div>
        <div>
          <label>Charge strength: {chargeStrength}</label>
          <input
            type="range"
            min="-500"
            max="-50"
            value={chargeStrength}
            onChange={(e) => setChargeStrength(Number(e.target.value))}
          />
        </div>
      </div>
      <ForceGraph2D
        graphData={graphData}
        nodeLabel={(node) => `${node.display_name || node.id}`}
        nodeAutoColorBy="community"
        cooldownTicks={100}
        linkDistance={linkDistance}
        d3Force={(name, force) => (name === "charge" ? force.strength(chargeStrength) : null)}
        linkDirectionalParticles={mutualOnly ? 0 : 2}
        nodeCanvasObjectMode={() => "after"}
        nodeCanvasObject={(node, ctx) => {
          const size = 4 + node.val;
          ctx.fillStyle = "rgba(0,0,0,0.7)";
          ctx.font = "12px sans-serif";
          ctx.fillText(node.id, node.x + size, node.y + size);
        }}
      />
    </div>
  );
}
