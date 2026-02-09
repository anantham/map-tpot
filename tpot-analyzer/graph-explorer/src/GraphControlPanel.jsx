import React from "react";
import { DEFAULT_WEIGHTS as DEFAULT_DISCOVERY_WEIGHTS } from "./config";

export default function GraphControlPanel({
  panelOpen, setPanelOpen,
  backendAvailable, computing,
  handleDownloadCsv, handleRefreshData,
  graphStats,
  mutualOnly, setMutualOnly,
  edgeOpacity, setEdgeOpacity,
  includeShadows, setIncludeShadows,
  weights, handleWeightChange,
  bridgeSummary, nodeLookup,
  subgraphSize, setSubgraphSize,
  linkDistance, setLinkDistance,
  chargeStrength, setChargeStrength,
  presetName, handlePresetChange, availablePresets,
  seedTextarea, setSeedTextarea, handleApplyCustomSeeds,
  myAccount, setMyAccount,
  excludeFollowing, setExcludeFollowing,
  myFollowingSet,
  topEntries, discoveryMetrics,
  selectedNodeId, setSelectedNodeId,
  seedList,
  getTpotnessFor, describePath,
}) {
  return (
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
          {backendAvailable === false && (
            <div style={{ padding: '10px', background: '#fee', borderRadius: '4px', marginBottom: '10px' }}>
              ⚠️ Backend API not available. Start the server with: <code>python -m scripts.start_api_server</code>
            </div>
          )}
          {computing && (
            <div style={{ padding: '10px', background: '#fef3cd', borderRadius: '4px', marginBottom: '10px' }}>
              🔄 Computing metrics...
            </div>
          )}
          <div className="panel-actions">
            <button onClick={handleDownloadCsv} disabled={computing}>Download CSV</button>
            <button onClick={handleRefreshData} disabled={computing}>
              {computing ? "Computing..." : "Recompute Metrics"}
            </button>
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
            {graphStats.usingStructuralFallback && (
              <p style={{ marginTop: 8, fontSize: '0.85em', color: '#94a3b8' }}>
                Structural view is visible while personalized metrics finish computing.
              </p>
            )}
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
            <h2>Edge opacity</h2>
            <div className="slider">
              <label>Transparency {edgeOpacity.toFixed(2)}</label>
              <input
                type="range"
                min="0.05"
                max="1.0"
                step="0.05"
                value={edgeOpacity}
                onChange={(e) => setEdgeOpacity(parseFloat(e.target.value))}
              />
            </div>
            <small>Adjust edge transparency (lower = more transparent)</small>
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
            <h2>Status weights (TPOT-ness = α·PR + β·BT + γ·ENG)</h2>
            <small>Adjust weights for composite score calculation. Changes trigger metric recomputation.</small>
            <div className="slider">
              <label>α (PageRank) {weights.pr.toFixed(2)}</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={weights.pr}
                onChange={handleWeightChange("pr")}
                disabled={computing}
              />
            </div>
            <div className="slider">
              <label>β (Betweenness) {weights.bt.toFixed(2)}</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={weights.bt}
                onChange={handleWeightChange("bt")}
                disabled={computing}
              />
            </div>
            <div className="slider">
              <label>γ (Engagement) {weights.eng.toFixed(2)}</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={weights.eng}
                onChange={handleWeightChange("eng")}
                disabled={computing}
              />
            </div>
            <div style={{ marginTop: '8px', fontSize: '0.85em', color: '#94a3b8' }}>
              Total: {(weights.pr + weights.bt + weights.eng).toFixed(2)}
              {Math.abs(weights.pr + weights.bt + weights.eng - 1.0) > 0.01 && " (⚠️ should sum to 1.0)"}
            </div>
          </section>

          <section>
            <h2>Connectivity</h2>
            <div className="summary-grid">
              <div>
                <span className="summary-label">Bridge nodes</span>
                <span className="summary-value">{graphStats.bridgeNodeCount || 0}</span>
              </div>
              <div>
                <span className="summary-label">Unresolved orphans</span>
                <span className="summary-value">{graphStats.orphanCount || 0}</span>
              </div>
            </div>
            {bridgeSummary.connectors.length > 0 && (
              <div style={{ marginTop: '8px', fontSize: '0.9em' }}>
                <strong>Key connectors</strong>
                <ul>
                  {bridgeSummary.connectors.slice(0, 3).map((item) => {
                    const labelNode = nodeLookup.get(item.id) || {};
                    const label = labelNode.display_name || labelNode.username || item.id;
                    return (
                      <li key={`connector-${item.id}`}>
                        {label} · supports {item.supportsCount} node{item.supportsCount === 1 ? '' : 's'}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {bridgeSummary.orphans.length > 0 && (
              <div style={{ marginTop: '8px', fontSize: '0.9em' }}>
                <strong style={{ color: '#f87171' }}>Still disconnected</strong>
                <ul>
                  {bridgeSummary.orphans.slice(0, 3).map((item) => {
                    const labelNode = nodeLookup.get(item.id) || {};
                    const label = labelNode.display_name || labelNode.username || item.id;
                    return (
                      <li key={`orphan-${item.id}`}>
                        {label} · needs {item.requiredBridgeCount}+ bridge nodes
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
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
              {Object.keys(availablePresets).map((name) => (
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
            <h2>My Account (optional)</h2>
            <input
              type="text"
              value={myAccount}
              onChange={(e) => setMyAccount(e.target.value)}
              placeholder="Your username (e.g., adityaarpitha)"
              style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
            />
            <label className="toggle">
              <input
                type="checkbox"
                checked={excludeFollowing}
                onChange={(e) => setExcludeFollowing(e.target.checked)}
                disabled={!myAccount || myFollowingSet.size === 0}
              />
              Exclude accounts I follow from Top Accounts
            </label>
            {myAccount && myFollowingSet.size > 0 && (
              <small style={{ display: 'block', marginTop: '4px', color: '#94a3b8' }}>
                Found {myFollowingSet.size} accounts you follow
              </small>
            )}
          </section>

          <section>
            <h2>Top accounts (by TPOT-ness score)</h2>
            <small style={{ display: 'block', marginBottom: '8px', color: '#94a3b8' }}>
              Ranked by discovery weights:&nbsp;
              {Object.entries(discoveryMetrics.config?.weights || DEFAULT_DISCOVERY_WEIGHTS)
                .map(([metric, weight]) => `${metric} ${(weight * 100).toFixed(0)}%`)
                .join(' · ')}
              {excludeFollowing && myFollowingSet.size > 0 && ' · Excluding accounts you follow'}
            </small>
            {topEntries.length === 0 ? (
              <p className="top-list-empty">
                Metrics still loading. Run a computation or adjust your seeds to populate this list.
              </p>
            ) : (
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
            )}
          </section>

          <section>
            <h2>Seed accounts ({seedList.length})</h2>
            <ul className="seed-list">
              {seedList.map((node) => (
                <li key={`${node.id}-seed`}>
                  {node.display_name || node.username || node.id}
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
                  const tpotness = getTpotnessFor(node.id, node.username);
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
                      {node.bridgeConnectorInfo && (
                        <p>Bridge connector for {node.bridgeConnectorInfo.supports.length} node{node.bridgeConnectorInfo.supports.length === 1 ? '' : 's'}</p>
                      )}
                      {node.bridgeTargetInfo && (
                        <p>
                          Connected via {node.bridgeTargetInfo.bridgeCount} bridge node{node.bridgeTargetInfo.bridgeCount === 1 ? '' : 's'} · Path: {describePath(node.bridgeTargetInfo.path)}
                        </p>
                      )}
                      {node.orphanInfo && (
                        <p style={{ color: '#f87171' }}>
                          Unresolved: needs {node.orphanInfo.requiredBridgeCount}+ bridge nodes (reason: {node.orphanInfo.reason || 'limit'})
                        </p>
                      )}
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
  );
}
