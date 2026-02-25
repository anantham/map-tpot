import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import { useGraphData } from "./hooks/useGraphData";
import { useGraphSeeds } from "./hooks/useGraphSeeds";
import { buildGraphView } from "./graphTransform";
import GraphControlPanel from "./GraphControlPanel";

const COLORS = {
  baseNode: "#a5b4fc",
  seedNode: "#fde68a",
  selectedNode: "#f472b6",
  neighborNode: "#5eead4",
  shadowNode: "#94a3b8",
  bridgeNode: "#fb923c",
  orphanNode: "#f87171",
  mutualEdge: "rgba(224, 242, 254, 0.25)", // More transparent
  oneWayEdge: "rgba(125, 211, 252, 0.15)", // More transparent
  selectedEdge: "#fb923c",
  neighborEdge: "#facc15"
};

const EMPTY_METRICS = Object.freeze({});

const normalizeHandle = (value) => {
  if (!value && value !== 0) return null;
  const cleaned = String(value).trim().replace(/^@/, "");
  if (!cleaned) return null;
  return cleaned.toLowerCase();
};

const dedupeHandles = (handles = []) => {
  const seen = new Set();
  const result = [];
  handles.forEach((handle) => {
    const normalized = normalizeHandle(handle);
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      result.push(normalized);
    }
  });
  return result;
};

const toLowerSet = (items = []) => {
  const set = new Set();
  items.forEach((item) => {
    if (!item) return;
    set.add(String(item).toLowerCase());
  });
  return set;
};

const sanitizeSeedList = (handles = []) => dedupeHandles(handles);

export default function GraphExplorer({ dataUrl: _dataUrl = "/analysis_output.json" }) {
  const [panelOpen, setPanelOpen] = useState(true);
  const [mutualOnly, setMutualOnly] = useState(false);
  const [linkDistance, setLinkDistance] = useState(140);
  const [chargeStrength, setChargeStrength] = useState(-220);
  const [edgeOpacity, setEdgeOpacity] = useState(0.25); // Default opacity for edges
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [includeShadows, setIncludeShadows] = useState(true);
  const [subgraphSize, setSubgraphSize] = useState(50);
  const [contextMenu, setContextMenu] = useState(null);
  const [myAccount, setMyAccount] = useState(''); // User's own account for filtering
  const [excludeFollowing, setExcludeFollowing] = useState(false); // Filter out accounts I follow
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });

  // --- Seed / preset management ---
  const {
    seedTextarea, setSeedTextarea, presetName,
    availablePresets, activeSeedList, customSeedHandleSet,
    applyCustomSeedList, persistSeedsToServer,
    handlePresetChange, handleApplyCustomSeeds,
  } = useGraphSeeds({
    onSettingsLoaded: useCallback((state) => {
      const autoShadow = state?.settings?.auto_include_shadow;
      if (typeof autoShadow === 'boolean') setIncludeShadows(autoShadow);
    }, []),
  });

  // --- Data pipeline (health → structure → metrics) ---
  const {
    graphStructure, metrics, error, loading, computing,
    backendAvailable, recomputeMetrics,
  } = useGraphData({
    activeSeedList,
    includeShadows,
    weights,
  });

  // Placeholder for future fallback mode using a static analysis JSON blob.
  void _dataUrl;

  const graphRef = useRef(null);

  // Dismiss context menu on outside click or ESC key
  useEffect(() => {
    if (!contextMenu) return;

    const handleClick = () => setContextMenu(null);
    const handleEscape = (e) => {
      if (e.key === 'Escape') setContextMenu(null);
    };

    // Small delay to prevent immediate dismissal from the right-click event
    const timeoutId = setTimeout(() => {
      document.addEventListener('click', handleClick);
      document.addEventListener('keydown', handleEscape);
    }, 100);

    return () => {
      clearTimeout(timeoutId);
      document.removeEventListener('click', handleClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [contextMenu]);

  // Discovery ranking now piggybacks on computeMetrics; no separate fetch needed.

  // Merged data - metrics are optional, graph can display without them
  const data = useMemo(() => {
    if (!graphStructure) return null;  // Only require structure

    return {
      graph: {
        nodes: graphStructure.nodes,
        edges: graphStructure.edges,
        directed_nodes: graphStructure.directed_nodes,
        directed_edges: graphStructure.directed_edges,
        undirected_edges: graphStructure.undirected_edges,
      },
      metrics: metrics?.metrics || {},  // Optional - defaults to empty
      seeds: metrics?.seeds || [],
      resolved_seeds: metrics?.resolved_seeds || [],
    };
  }, [graphStructure, metrics]);

  useEffect(() => {
    console.debug("[GraphExplorer] control panel open:", panelOpen);
  }, [panelOpen]);

  const resolvedSeeds = useMemo(() => {
    const seedSet = toLowerSet(data?.seeds);
    const resolvedSet = toLowerSet(data?.resolved_seeds);
    const combined = new Set([...seedSet, ...resolvedSet]);
    return combined;
  }, [data]);

  const activeSeedHandleSet = useMemo(() => toLowerSet(activeSeedList), [activeSeedList]);

  const effectiveSeedSet = useMemo(() => new Set([...resolvedSeeds, ...activeSeedHandleSet]), [resolvedSeeds, activeSeedHandleSet]);

  const metricsData = data?.metrics ?? EMPTY_METRICS;

  const discoveryMetrics = useMemo(() => metricsData?.discovery || {}, [metricsData]);

  const tpotnessScores = useMemo(() => {
    const map = {};
    const rawScores = discoveryMetrics.scores || {};
    Object.entries(rawScores).forEach(([key, score]) => {
      const normalized = normalizeHandle(key);
      if (normalized) {
        map[normalized] = score ?? 0;
        map[String(key).toLowerCase()] = score ?? 0;
      }
    });
    activeSeedList.forEach((seed) => {
      const key = normalizeHandle(seed);
      if (key) {
        map[key] = 1;
      }
    });
    if (Object.keys(map).length > 0) {
      return map;
    }
    return metricsData?.composite ?? {};
  }, [discoveryMetrics, metricsData, activeSeedList]);

  const getTpotnessFor = useCallback((id, username) => {
    const idValue = id ? String(id) : "";
    if (idValue && Object.prototype.hasOwnProperty.call(tpotnessScores, idValue)) {
      return tpotnessScores[idValue];
    }
    const idLower = idValue.toLowerCase();
    if (idLower && Object.prototype.hasOwnProperty.call(tpotnessScores, idLower)) {
      return tpotnessScores[idLower];
    }
    const usernameKey = username ? normalizeHandle(username) : null;
    if (usernameKey && Object.prototype.hasOwnProperty.call(tpotnessScores, usernameKey)) {
      return tpotnessScores[usernameKey];
    }
    return 0;
  }, [tpotnessScores]);
  const metricsReady = useMemo(() => Object.keys(tpotnessScores).length > 0, [tpotnessScores]);

  const { graphData, graphStats, bridgeDiagnostics } = useMemo(
    () => buildGraphView({
      data, tpotnessScores, effectiveSeedSet, includeShadows,
      metricsData, mutualOnly, metricsReady, subgraphSize,
    }),
    [data, tpotnessScores, effectiveSeedSet, includeShadows, metricsData, mutualOnly, metricsReady, subgraphSize]
  );

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

  const describePath = useCallback((path = []) => {
    if (!Array.isArray(path) || path.length === 0) return "";
    return path
      .map((nodeId) => {
        const node = nodeLookup.get(nodeId);
        if (!node) return nodeId;
        if (node.username) return `@${node.username}`;
        if (node.display_name) return node.display_name;
        return node.id || nodeId;
      })
      .join(" → ");
  }, [nodeLookup]);

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

  // Get following list for myAccount (if specified)
  const myFollowingSet = useMemo(() => {
    if (!myAccount || !graphStructure) return new Set();

    const myAccountLower = normalizeHandle(myAccount);
    if (!myAccountLower) return new Set();

    // Find my account node in the graph
    const edges = graphStructure.graph?.edges || [];
    const following = new Set();

    edges.forEach(edge => {
      const sourceLower = normalizeHandle(edge.source);
      if (sourceLower === myAccountLower) {
        const targetLower = normalizeHandle(edge.target);
        if (targetLower) {
          following.add(targetLower);
        }
      }
    });

    return following;
  }, [myAccount, graphStructure]);

  const topEntries = useMemo(() => {
    let entries = Object.entries(tpotnessScores)
      .sort((a, b) => b[1] - a[1]);

    // Filter out accounts I'm already following
    if (excludeFollowing && myFollowingSet.size > 0) {
      entries = entries.filter(([id]) => {
        const idLower = normalizeHandle(id);
        return !myFollowingSet.has(idLower);
      });
    }

    return entries.slice(0, 12);
  }, [tpotnessScores, excludeFollowing, myFollowingSet]);

  const bridgeSummary = useMemo(() => {
    if (!bridgeDiagnostics) {
      return { connectors: [], orphans: [] };
    }
    const connectors = [];
    if (bridgeDiagnostics.connectors && bridgeDiagnostics.connectors.forEach) {
      bridgeDiagnostics.connectors.forEach((value, key) => {
        const supports = Array.from(value.supports || []);
        connectors.push({
          id: key,
          supports,
          supportsCount: supports.length,
          samples: value.samples || []
        });
      });
    }
    connectors.sort((a, b) => (b.supportsCount || 0) - (a.supportsCount || 0));

    const orphans = [];
    if (bridgeDiagnostics.orphans && bridgeDiagnostics.orphans.forEach) {
      bridgeDiagnostics.orphans.forEach((value, key) => {
        orphans.push({
          id: key,
          requiredBridgeCount: value?.requiredBridgeCount ?? null,
          totalHops: value?.totalHops ?? null,
          reason: value?.reason
        });
      });
    }
    orphans.sort((a, b) => (b.requiredBridgeCount || 0) - (a.requiredBridgeCount || 0));
    return { connectors, orphans };
  }, [bridgeDiagnostics]);

  const contextHandle = contextMenu?.node
    ? normalizeHandle(contextMenu.node.username || contextMenu.node.id)
    : null;
  const contextIsCustomSeed = contextHandle ? customSeedHandleSet.has(contextHandle) : false;
  const contextIsSeed = contextHandle ? effectiveSeedSet.has(contextHandle) : false;

  const seedList = useMemo(() => {
    const unique = new Map();
    graphData.nodes.forEach((node) => {
      if (effectiveSeedSet.has(node.idLower)) {
        unique.set(node.idLower, node);
      }
    });
    customSeedHandleSet.forEach((seed) => {
      if (!unique.has(seed)) {
        unique.set(seed, { id: seed, username: seed, display_name: seed, idLower: seed });
      }
    });
    return Array.from(unique.values());
  }, [graphData.nodes, effectiveSeedSet, customSeedHandleSet]);

  const selectedNeighbors = useMemo(() => {
    if (!selectedNodeId) return new Set();
    return neighborMap.get(selectedNodeId) || new Set();
  }, [neighborMap, selectedNodeId]);

  const getNodeColor = useCallback((node) => {
    if (node.id === selectedNodeId) return COLORS.selectedNode;
    if (node.orphanInfo) return COLORS.orphanNode;
    if (node.isBridge) return COLORS.bridgeNode;
    if (selectedNeighbors.has(node.id)) return COLORS.neighborNode;
    if (node.isSeed) return COLORS.seedNode;
    if (node.shadow) return COLORS.shadowNode;
    return COLORS.baseNode;
  }, [selectedNodeId, selectedNeighbors]);

  const getLinkStyle = (link) => {
    const sourceId = typeof link.source === "object" ? link.source.id : link.source;
    const targetId = typeof link.target === "object" ? link.target.id : link.target;
    const isSelectedEdge =
      selectedNodeId && (sourceId === selectedNodeId || targetId === selectedNodeId);
    if (isSelectedEdge) {
      return { color: COLORS.selectedEdge, width: 1.5, dash: [] };
    }

    const connectsNeighbors =
      selectedNodeId && selectedNeighbors.has(sourceId) && selectedNeighbors.has(targetId);
    if (connectsNeighbors) {
      return { color: COLORS.neighborEdge, width: 1.2, dash: [] };
    }

    if (link.shadow) {
      return { color: `rgba(203, 213, 225, ${edgeOpacity})`, width: 0.6, dash: [3, 5] };
    }

    if (link.mutual) {
      return { color: `rgba(224, 242, 254, ${edgeOpacity})`, width: 0.8, dash: [] };
    }

    return { color: `rgba(125, 211, 252, ${edgeOpacity * 0.6})`, width: 0.7, dash: [6, 4] };
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

  const focusOnNode = useCallback((node) => {
    if (!graphRef.current || !node) return;
    const duration = 800;
    graphRef.current.centerAt(node.x, node.y, duration);
    graphRef.current.zoom(2.2, duration);
  }, []);

  const addNodeToCustomSeeds = useCallback(async (node) => {
    if (!node) return;
    const normalized = normalizeHandle(node.username || node.id);
    if (!normalized) return;

    const baseSeeds = activeSeedList;
    if (baseSeeds.some((seed) => normalizeHandle(seed) === normalized)) {
      setContextMenu(null);
      return;
    }

    const updated = sanitizeSeedList([...baseSeeds, normalized]);
    applyCustomSeedList(updated, { keepPresetName: true });
    try {
      await persistSeedsToServer(updated);
    } catch (err) {
      console.error("Failed to persist seed addition:", err);
      if (typeof window !== "undefined" && window.alert) {
        window.alert(err.message || "Failed to save seeds. They remain local only.");
      }
    } finally {
      setContextMenu(null);
    }
  }, [activeSeedList, applyCustomSeedList, persistSeedsToServer]);

  const removeNodeFromCustomSeeds = useCallback(async (node) => {
    if (!node) return;
    const normalized = normalizeHandle(node.username || node.id);
    if (!normalized) return;

    const baseSeeds = activeSeedList;
    if (!baseSeeds.some((seed) => normalizeHandle(seed) === normalized)) {
      setContextMenu(null);
      return;
    }

    if (baseSeeds.length <= 1) {
      if (typeof window !== "undefined" && window.alert) {
        window.alert("Keep at least one seed in your Part of Twitter.");
      }
      setContextMenu(null);
      return;
    }

    const updated = sanitizeSeedList(baseSeeds.filter((seed) => normalizeHandle(seed) !== normalized));
    applyCustomSeedList(updated, { keepPresetName: true });
    try {
      await persistSeedsToServer(updated);
    } catch (err) {
      console.error("Failed to persist seed removal:", err);
      if (typeof window !== "undefined" && window.alert) {
        window.alert(err.message || "Failed to save seeds. They remain local only.");
      }
    } finally {
      setContextMenu(null);
    }
  }, [activeSeedList, applyCustomSeedList, persistSeedsToServer]);

  const handleWeightChange = (key) => (event) => {
    const value = Number(event.target.value);
    setWeights((prev) => ({ ...prev, [key]: value }));
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
          const tpotness = getTpotnessFor(node.id, node.username);
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
    await recomputeMetrics();
  };

  if (error) return <div className="status-message">Error loading graph: {error.message}</div>;
  if (loading) return <div className="status-message">Loading graph structure…</div>;
  if (!data) return <div className="status-message">Waiting for data…</div>;

  return (
    <div className="layout">
      <GraphControlPanel
        panelOpen={panelOpen} setPanelOpen={setPanelOpen}
        backendAvailable={backendAvailable} computing={computing}
        handleDownloadCsv={handleDownloadCsv} handleRefreshData={handleRefreshData}
        graphStats={graphStats}
        mutualOnly={mutualOnly} setMutualOnly={setMutualOnly}
        edgeOpacity={edgeOpacity} setEdgeOpacity={setEdgeOpacity}
        includeShadows={includeShadows} setIncludeShadows={setIncludeShadows}
        weights={weights} handleWeightChange={handleWeightChange}
        bridgeSummary={bridgeSummary} nodeLookup={nodeLookup}
        subgraphSize={subgraphSize} setSubgraphSize={setSubgraphSize}
        linkDistance={linkDistance} setLinkDistance={setLinkDistance}
        chargeStrength={chargeStrength} setChargeStrength={setChargeStrength}
        presetName={presetName} handlePresetChange={handlePresetChange} availablePresets={availablePresets}
        seedTextarea={seedTextarea} setSeedTextarea={setSeedTextarea} handleApplyCustomSeeds={handleApplyCustomSeeds}
        myAccount={myAccount} setMyAccount={setMyAccount}
        excludeFollowing={excludeFollowing} setExcludeFollowing={setExcludeFollowing}
        myFollowingSet={myFollowingSet}
        topEntries={topEntries} discoveryMetrics={discoveryMetrics}
        selectedNodeId={selectedNodeId} setSelectedNodeId={setSelectedNodeId}
        seedList={seedList}
        getTpotnessFor={getTpotnessFor} describePath={describePath}
      />

      <div className="graph-container">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          enableNodeDrag={true}
          nodeColor={getNodeColor}
          linkColor={(link) => getLinkStyle(link).color}
          linkWidth={(link) => getLinkStyle(link).width}
          linkDirectionalParticles={(link) => (link.mutual ? 0 : 2)}
          linkDirectionalParticleWidth={1.6}
          linkDirectionalParticleColor={(link) => getLinkStyle(link).color}
          linkDirectionalArrowLength={(link) => (link.mutual ? 0 : 8)}
          linkDirectionalArrowRelPos={(link) => (link.mutual ? 0.5 : 0.92)}
          linkDirectionalArrowColor={(link) => getLinkStyle(link).color}
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
            const tpotness = getTpotnessFor(node.id, node.username);
            const name = node.display_name || node.username || node.id;
            const distanceLabel = Number.isFinite(node.hopDistance)
              ? node.hopDistance
              : "∞";
            const provenanceLabel = node.provenance || (node.shadow ? "shadow" : "archive");
            const statusLabel = node.orphanInfo
              ? `🚧 needs ${node.orphanInfo.requiredBridgeCount}+ bridge nodes`
              : node.isBridge
                ? "Bridge connector"
                : "";
            return `${name}\nProvenance: ${provenanceLabel}\nTPOT-ness: ${(tpotness * 100).toFixed(1)}\nMutual edges: ${node.mutualCount}\nSeed touches: ${node.seedTouchCount}\nHop distance: ${distanceLabel}\nPageRank: ${(node.pagerank ?? 0).toFixed(3)}\nBetweenness: ${(node.betweenness ?? 0).toFixed(3)}\nEngagement: ${(node.engagement ?? 0).toFixed(3)}${statusLabel ? `\nStatus: ${statusLabel}` : ""}`;
          }}
          nodeCanvasObjectMode={() => "replace"}
          nodeCanvasObject={(node, ctx, globalScale) => {
            // Calculate zoom-responsive radius - size based on betweenness centrality
            const betweenness = node.betweenness ?? 0;
            const baseRadius = 4 + (betweenness * 20); // Scale 4-8 based on betweenness
            const radius = baseRadius / Math.sqrt(globalScale);

            // Get node color
            const color = getNodeColor(node);

            // Draw circle
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();

            // Optional: Add border for selected nodes
            if (node.id === selectedNodeId) {
              ctx.strokeStyle = COLORS.selectedNode;
              ctx.lineWidth = 2 / globalScale;
              ctx.stroke();
            } else if (node.orphanInfo) {
              ctx.strokeStyle = COLORS.orphanNode;
              ctx.lineWidth = 2 / globalScale;
              ctx.stroke();
            } else if (node.isBridge) {
              ctx.strokeStyle = COLORS.bridgeNode;
              ctx.lineWidth = 1.5 / globalScale;
              ctx.stroke();
            }

            // Draw label - black text for better readability
            const label = node.username || node.id;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "#0284c7";
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillText(label, node.x + radius + 2, node.y);
          }}
          onNodeClick={(node) => {
            setSelectedNodeId(node.id === selectedNodeId ? null : node.id);
          }}
          onNodeRightClick={(node, event) => {
            event.preventDefault();
            setContextMenu({
              node,
              x: event.clientX,
              y: event.clientY
            });
          }}
        />
      </div>

      {contextMenu && (
        <div
          className="context-menu"
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 1000
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="context-menu-item"
            onClick={() => {
              const username = contextMenu.node.username || contextMenu.node.id;
              navigator.clipboard.writeText(username);
              setContextMenu(null);
            }}
          >
            Copy @{contextMenu.node.username || contextMenu.node.id}
          </button>
          <button
            className="context-menu-item"
            onClick={() => {
              if (contextIsCustomSeed) {
                removeNodeFromCustomSeeds(contextMenu.node);
              } else {
                addNodeToCustomSeeds(contextMenu.node);
              }
            }}
          >
            {contextIsCustomSeed ? 'Remove from custom seeds' : 'Add as custom seed'}
          </button>
          {!contextIsCustomSeed && contextIsSeed && (
            <div className="context-menu-hint">
              Already part of the active preset
            </div>
          )}
          {contextMenu.node.bridgeConnectorInfo && (
            <div className="context-menu-hint">
              Bridge connector for {contextMenu.node.bridgeConnectorInfo.supports.length} node{contextMenu.node.bridgeConnectorInfo.supports.length === 1 ? '' : 's'}
            </div>
          )}
          {contextMenu.node.orphanInfo && (
            <div className="context-menu-hint" style={{ color: '#f87171' }}>
              Needs {contextMenu.node.orphanInfo.requiredBridgeCount}+ bridge nodes
            </div>
          )}
          <button
            className="context-menu-item"
            onClick={() => {
              const username = contextMenu.node.username || contextMenu.node.id;
              window.open(`https://twitter.com/${username}`, '_blank');
              setContextMenu(null);
            }}
          >
            Open on Twitter
          </button>
          <button
            className="context-menu-item"
            onClick={() => {
              focusOnNode(contextMenu.node);
              setContextMenu(null);
            }}
          >
            Center & zoom here
          </button>
        </div>
      )}
    </div>
  );
}
