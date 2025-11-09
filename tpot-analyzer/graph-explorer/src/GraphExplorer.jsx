import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import { fetchGraphData, computeMetrics, checkHealth } from "./data";
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

const sanitizeSeedList = (handles = []) => dedupeHandles(handles);

export default function GraphExplorer({ dataUrl = "/analysis_output.json" }) {
  const [graphStructure, setGraphStructure] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(null);

  // Check backend health on mount
  useEffect(() => {
    const checkBackend = async () => {
      const isHealthy = await checkHealth();
      setBackendAvailable(isHealthy);
      if (!isHealthy) {
        console.warn("Backend API not available. Some features will be limited.");
      }
    };
    checkBackend();
  }, []);
  const [panelOpen, setPanelOpen] = useState(true);
  const [mutualOnly, setMutualOnly] = useState(false);
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });
  const [linkDistance, setLinkDistance] = useState(140);
  const [chargeStrength, setChargeStrength] = useState(-220);
  const [edgeOpacity, setEdgeOpacity] = useState(0.25); // Default opacity for edges
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [seedTextarea, setSeedTextarea] = useState("");
  const [customSeeds, setCustomSeeds] = useState([]);
  const [presetName, setPresetName] = useState("Adi's Seeds");
  const [includeShadows, setIncludeShadows] = useState(true);
  const [subgraphSize, setSubgraphSize] = useState(50);
  const [contextMenu, setContextMenu] = useState(null);
  const [myAccount, setMyAccount] = useState(''); // User's own account for filtering
  const [excludeFollowing, setExcludeFollowing] = useState(false); // Filter out accounts I follow

  const graphRef = useRef(null);

  const applyCustomSeedList = useCallback((nextSeeds, { keepPresetName = false } = {}) => {
    const sanitized = sanitizeSeedList(Array.isArray(nextSeeds) ? nextSeeds : []);
    setCustomSeeds(sanitized);
    setSeedTextarea(sanitized.join("\n"));
    if (!keepPresetName) {
      setPresetName("Custom");
    }
  }, []);

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

  const activeSeedList = useMemo(() => {
    if (customSeeds.length > 0) {
      return customSeeds;
    }
    return DEFAULT_PRESETS[presetName] || [];
  }, [customSeeds, presetName]);

  // Load initial graph structure
  useEffect(() => {
    const loadGraph = async () => {
      if (!backendAvailable) return;

      try {
        console.log('[GraphExplorer] Loading graph structure...');
        setLoading(true);
        const structure = await fetchGraphData({
          includeShadow: includeShadows,
          mutualOnly: false, // Load all edges, filter in UI
          minFollowers: 0,
        });
        setGraphStructure(structure);
        console.log('[GraphExplorer] Graph structure loaded - graph can now display!');
      } catch (err) {
        console.error("Failed to load graph structure:", err);
        setError(err);
      } finally {
        setLoading(false);
      }
    };
    loadGraph();
  }, [backendAvailable, includeShadows]);

  // Compute metrics when seeds or weights change
  const recomputeMetrics = useCallback(async () => {
    if (!backendAvailable || !graphStructure) return;

    try {
      setComputing(true);
      console.log(`[GraphExplorer] Computing metrics with ${activeSeedList.length} seeds (non-blocking)...`);
      const result = await computeMetrics({
        seeds: activeSeedList,
        weights: [weights.pr, weights.bt, weights.eng],
        alpha: 0.85,
        resolution: 1.0,
        includeShadow: includeShadows,
        mutualOnly: false,
        minFollowers: 0,
      });

      setMetrics(result);
      console.log('[GraphExplorer] Metrics computed! Tooltips and node sizing updated.');
    } catch (err) {
      console.error("Failed to compute metrics:", err);
      setError(err);
    } finally {
      setComputing(false);
    }
  }, [backendAvailable, graphStructure, activeSeedList, weights, includeShadows]);

  // Trigger metric recomputation when dependencies change
  useEffect(() => {
    recomputeMetrics();
  }, [recomputeMetrics]);

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
  const customSeedHandleSet = useMemo(() => toLowerSet(customSeeds), [customSeeds]);
  const effectiveSeedSet = useMemo(() => new Set([...resolvedSeeds, ...activeSeedHandleSet]), [resolvedSeeds, activeSeedHandleSet]);

  const metricsData = data?.metrics ?? EMPTY_METRICS;

  // Use composite score from backend (already computed with all three weights)
  const tpotnessScores = useMemo(() => {
    return metricsData?.composite ?? {};
  }, [metricsData]);
  const metricsReady = useMemo(() => Object.keys(tpotnessScores).length > 0, [tpotnessScores]);

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
          visibleShadowEdges: 0,
          usingStructuralFallback: false
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

    const fallbackIds = !metricsReady
      ? Object.keys(nodesMeta).slice(0, Math.max(subgraphSize, 50))
      : [];
    const topNIds = metricsReady
      ? Object.entries(tpotnessScores)
          .sort(([, a], [, b]) => b - a)
          .slice(0, subgraphSize)
          .map(([id]) => id)
      : [];

    // Build allowed set with both account IDs and usernames for matching
    const allowedNodeSet = new Set(metricsReady ? topNIds : fallbackIds);

    // Add seed nodes to the allowed set (they should always be visible)
    nodeIds.forEach((rawId) => {
      const id = String(rawId);
      const meta = nodesMeta[id] || {};
      const usernameLower = meta.username ? String(meta.username).toLowerCase() : null;
      const idLower = id.toLowerCase();

      // Check if this node is a seed by any of its identifiers
      if (effectiveSeedSet.has(idLower) ||
          (usernameLower && effectiveSeedSet.has(usernameLower))) {
        allowedNodeSet.add(id);  // Add the actual account ID
      }
    });

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
        community: metricsData.communities?.[id],
        pagerank: metricsData.pagerank?.[id],
        betweenness: metricsData.betweenness?.[id],
        engagement: metricsData.engagement?.[id],
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
          mutual: !!edge.mutual,
          shadow: !!edge.shadow
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
        visibleShadowEdges: filteredLinks.filter((edge) => edge.shadow).length,
        usingStructuralFallback: !metricsReady
      }
    };
  }, [data, tpotnessScores, effectiveSeedSet, includeShadows, metricsData, mutualOnly, metricsReady]);

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

  const totalWeight = weights.pr + weights.bt + weights.eng;
  const selectedNeighbors = selectedNodeId ? neighborMap.get(selectedNodeId) || new Set() : new Set();

  const getNodeColor = useCallback((node) => {
    if (node.id === selectedNodeId) return COLORS.selectedNode;
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

  const addNodeToCustomSeeds = useCallback((node) => {
    if (!node) return;
    const normalized = normalizeHandle(node.username || node.id);
    if (!normalized) return;
    applyCustomSeedList([...customSeeds, normalized]);
    setContextMenu(null);
  }, [applyCustomSeedList, customSeeds]);

  const removeNodeFromCustomSeeds = useCallback((node) => {
    if (!node) return;
    const normalized = normalizeHandle(node.username || node.id);
    if (!normalized) return;
    applyCustomSeedList(customSeeds.filter((seed) => normalizeHandle(seed) !== normalized), { keepPresetName: false });
    setContextMenu(null);
  }, [applyCustomSeedList, customSeeds]);

  const handleWeightChange = (key) => (event) => {
    const value = Number(event.target.value);
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const handlePresetChange = (event) => {
    const name = event.target.value;
    setPresetName(name);
    const presetSeeds = DEFAULT_PRESETS[name] || [];
    applyCustomSeedList(presetSeeds, { keepPresetName: true });
  };

  const handleApplyCustomSeeds = () => {
    const lines = seedTextarea
      .split(/[,\n]/)
      .map((line) => line.trim())
      .filter(Boolean);
    applyCustomSeedList(lines);
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
    await recomputeMetrics();
  };

  if (error) return <div className="status-message">Error loading graph: {error.message}</div>;
  if (loading) return <div className="status-message">Loading graph structure…</div>;
  if (!data) return <div className="status-message">Waiting for data…</div>;

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
                Ranked by weighted composite: {weights.pr.toFixed(2)}·PR + {weights.bt.toFixed(2)}·BT + {weights.eng.toFixed(2)}·ENG
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
            const tpotness = tpotnessScores[node.id] ?? 0;
            const name = node.display_name || node.username || node.id;
            const distanceLabel = Number.isFinite(node.hopDistance)
              ? node.hopDistance
              : "∞";
            const provenanceLabel = node.provenance || (node.shadow ? "shadow" : "archive");
            return `${name}\nProvenance: ${provenanceLabel}\nTPOT-ness: ${(tpotness * 100).toFixed(1)}\nMutual edges: ${node.mutualCount}\nSeed touches: ${node.seedTouchCount}\nHop distance: ${distanceLabel}\nPageRank: ${(node.pagerank ?? 0).toFixed(3)}\nBetweenness: ${(node.betweenness ?? 0).toFixed(3)}\nEngagement: ${(node.engagement ?? 0).toFixed(3)}`;
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
            }

            // Draw label - black text for better readability
            const label = node.display_name || node.username || node.id;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "#000000"; // Black text
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
