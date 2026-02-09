import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import { fetchGraphData, fetchGraphSettings, checkHealth, computeMetrics, saveSeedList } from "./data";
import { DEFAULT_PRESETS, DEFAULT_WEIGHTS as DEFAULT_DISCOVERY_WEIGHTS } from "./config";

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

const BRIDGE_CONFIG = {
  maxBridgeNodesPerPath: 5,
  maxBridgeHops: 8,
  maxTotalBridgeNodes: 50
};

export default function GraphExplorer({ dataUrl: _dataUrl = "/analysis_output.json" }) {
  const [graphStructure, setGraphStructure] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(null);
  const metricsInFlightRef = useRef(false); // Guard against concurrent metric computations
  const [panelOpen, setPanelOpen] = useState(true);
  const [mutualOnly, setMutualOnly] = useState(false);
  const [graphSettings, setGraphSettings] = useState(null);
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
  const [weights, setWeights] = useState({ pr: 0.4, bt: 0.3, eng: 0.3 });

  const availablePresets = useMemo(() => {
    const lists = graphSettings?.lists;
    if (lists && Object.keys(lists).length > 0) {
      return lists;
    }
    return DEFAULT_PRESETS;
  }, [graphSettings]);

  // Placeholder for future fallback mode using a static analysis JSON blob.
  void _dataUrl;

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

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const state = await fetchGraphSettings();
        setGraphSettings(state);
        const autoShadow = state?.settings?.auto_include_shadow;
        if (typeof autoShadow === "boolean") {
          setIncludeShadows(autoShadow);
        }
      } catch (err) {
        console.error("Failed to load graph settings:", err);
      }
    };
    loadSettings();
  }, []);

  useEffect(() => {
    if (!graphSettings || customSeeds.length > 0) return;
    const active = graphSettings.active_list;
    if (!active || !availablePresets[active]) return;
    if (presetName !== active) {
      setPresetName(active);
    }
    setSeedTextarea((availablePresets[active] || []).join("\n"));
  }, [graphSettings, availablePresets, customSeeds.length, presetName]);

  const determineEditableSeedListName = useCallback(() => {
    const presetNames = new Set(graphSettings?.preset_names || []);
    const userListNames = new Set(graphSettings?.user_list_names || []);
    const existingLists = new Set(Object.keys(graphSettings?.lists || {}));

    let active = graphSettings?.active_list || presetName || "graph_explorer";
    if (!presetNames.has(active) || userListNames.has(active)) {
      return active;
    }

    let candidate = `${active}_custom`;
    let counter = 1;
    while (existingLists.has(candidate)) {
      candidate = `${active}_custom_${counter++}`;
    }
    return candidate;
  }, [graphSettings, presetName]);

  const persistSeedsToServer = useCallback(async (nextSeeds) => {
    if (!Array.isArray(nextSeeds) || nextSeeds.length === 0) {
      throw new Error("Add at least one account before saving seeds.");
    }
    const sanitized = sanitizeSeedList(nextSeeds);
    if (!sanitized.length) {
      throw new Error("None of the handles were valid.");
    }
    const targetName = determineEditableSeedListName();
    const state = await saveSeedList({
      name: targetName,
      seeds: sanitized,
      setActive: true
    });
    if (state) {
      setGraphSettings(state);
      setPresetName(state.active_list || targetName);
    }
    return state;
  }, [determineEditableSeedListName]);

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
    return availablePresets[presetName] || [];
  }, [customSeeds, presetName, availablePresets]);

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

    // Guard: prevent concurrent calls (React StrictMode protection)
    if (metricsInFlightRef.current) {
      console.log('[GraphExplorer] Metrics computation already in progress, skipping...');
      return;
    }

    try {
      metricsInFlightRef.current = true;
      setComputing(true);
      console.log(`[GraphExplorer] Computing base metrics with ${activeSeedList.length} seeds...`);
      const weightVector = [weights.pr, weights.bt, weights.eng];
      const result = await computeMetrics({
        seeds: activeSeedList,
        weights: weightVector,
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
      metricsInFlightRef.current = false;
    }
  }, [backendAvailable, graphStructure, activeSeedList, includeShadows, weights]);

  // Trigger metric recomputation when dependencies change
  useEffect(() => {
    recomputeMetrics();
  }, [recomputeMetrics]);

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
  const customSeedHandleSet = useMemo(() => toLowerSet(customSeeds), [customSeeds]);
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

  const { graphData, graphStats, bridgeDiagnostics } = useMemo(() => {
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
          usingStructuralFallback: false,
          bridgeNodeCount: 0,
          orphanCount: 0
        },
        bridgeDiagnostics: {
          connectors: new Map(),
          targets: new Map(),
          orphans: new Map()
        }
      };
    }

    const nodesMeta = (() => {
      const rawNodes = data.graph?.nodes;
      if (Array.isArray(rawNodes)) {
        const byId = {};
        rawNodes.forEach((node) => {
          const id = node?.id;
          if (id === undefined || id === null) return;
          byId[String(id)] = node;
        });
        return byId;
      }
      if (rawNodes && typeof rawNodes === "object") {
        return rawNodes;
      }
      return {};
    })();

    const edges = Array.isArray(data.graph?.edges) ? data.graph.edges : [];
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
    const seedNodeSet = new Set();

    // Add seed nodes to the allowed set (they should always be visible)
    nodeIds.forEach((rawId) => {
      const id = String(rawId);
      const meta = nodesMeta[id] || {};
      const usernameLower = meta.username ? String(meta.username).toLowerCase() : null;
      const idLower = id.toLowerCase();

      if (
        effectiveSeedSet.has(idLower) ||
        (usernameLower && effectiveSeedSet.has(usernameLower))
      ) {
        allowedNodeSet.add(id);
        seedNodeSet.add(id);
      }
    });

    const bridgeConnectorMap = new Map();
    const bridgeTargetMap = new Map();
    const orphanInfoMap = new Map();

    const computeReachableWithinAllowed = () => {
      const reachable = new Set();
      const queue = [];

      seedNodeSet.forEach((seedId) => {
        if (allowedNodeSet.has(seedId)) {
          reachable.add(seedId);
          queue.push(seedId);
        }
      });

      while (queue.length) {
        const current = queue.shift();
        const neighbors = mutualAdjacency.get(current);
        if (!neighbors) continue;
        neighbors.forEach((neighbor) => {
          if (!allowedNodeSet.has(neighbor) || reachable.has(neighbor)) return;
          reachable.add(neighbor);
          queue.push(neighbor);
        });
      }
      return reachable;
    };

    const findBridgePath = (targetId) => {
      const queue = [
        {
          node: targetId,
          path: [targetId],
          hops: 0,
          bridges: 0,
          score: 0
        }
      ];
      const visited = new Set([targetId]);

      while (queue.length) {
        queue.sort((a, b) => a.score - b.score);
        const current = queue.shift();
        if (current.hops >= BRIDGE_CONFIG.maxBridgeHops) {
          continue;
        }
        const neighbors = mutualAdjacency.get(current.node);
        if (!neighbors) continue;

        for (const neighbor of neighbors) {
          if (visited.has(neighbor)) continue;
          const isAllowedNeighbor = allowedNodeSet.has(neighbor) || seedNodeSet.has(neighbor);
          const nextBridgeCount = isAllowedNeighbor ? current.bridges : current.bridges + 1;
          if (nextBridgeCount > BRIDGE_CONFIG.maxBridgeNodesPerPath) continue;
          const nextHops = current.hops + 1;
          const nextPath = [...current.path, neighbor];

          if (seedNodeSet.has(neighbor)) {
            const fullPath = [...nextPath].reverse();
            const bridgeNodes = fullPath.filter(
              (nodeId) => !allowedNodeSet.has(nodeId) && !seedNodeSet.has(nodeId)
            );
            return {
              path: fullPath,
              bridgeNodes,
              totalHops: nextHops,
              requiredBridgeCount: bridgeNodes.length
            };
          }

          visited.add(neighbor);
          const neighborScore = getTpotnessFor(neighbor, nodesMeta[neighbor]?.username);
          const penalty = 1 - (Number.isFinite(neighborScore) ? neighborScore : 0);
          queue.push({
            node: neighbor,
            path: nextPath,
            hops: nextHops,
            bridges: nextBridgeCount,
            score: nextHops + penalty * 0.75
          });
        }
      }

      return null;
    };

    const enforceConnectivity = () => {
      let reachable = computeReachableWithinAllowed();
      const collectOrphans = () =>
        [...allowedNodeSet].filter((id) => !reachable.has(id) && !seedNodeSet.has(id));
      let orphans = collectOrphans();
      let bridgeBudget = 0;
      let iterations = 0;

      while (
        orphans.length > 0 &&
        bridgeBudget < BRIDGE_CONFIG.maxTotalBridgeNodes &&
        iterations < 100
      ) {
        const targetId = orphans.shift();
        const result = findBridgePath(targetId);

        if (result) {
          if (result.bridgeNodes.length === 0) {
            // Path found using existing nodes; treat as connected.
            bridgeTargetMap.set(targetId, {
              path: result.path,
              bridgeCount: 0,
              totalHops: result.totalHops
            });
            reachable = computeReachableWithinAllowed();
            orphans = collectOrphans();
            iterations += 1;
            continue;
          }

          const addedNow = [];
          result.bridgeNodes.forEach((connectorId) => {
            if (!allowedNodeSet.has(connectorId)) {
              if (bridgeBudget >= BRIDGE_CONFIG.maxTotalBridgeNodes) {
                return;
              }
              allowedNodeSet.add(connectorId);
              addedNow.push(connectorId);
              bridgeBudget += 1;
            }
          });

          addedNow.forEach((connectorId) => {
            if (!bridgeConnectorMap.has(connectorId)) {
              bridgeConnectorMap.set(connectorId, {
                supports: new Set(),
                samples: []
              });
            }
            const entry = bridgeConnectorMap.get(connectorId);
            entry.supports.add(targetId);
            entry.samples.push({
              target: targetId,
              path: result.path,
              bridgeCount: result.bridgeNodes.length,
              totalHops: result.totalHops
            });
            if (entry.samples.length > 3) {
              entry.samples = entry.samples.slice(-3);
            }
          });
          if (bridgeBudget >= BRIDGE_CONFIG.maxTotalBridgeNodes) {
            break;
          }

          bridgeTargetMap.set(targetId, {
            path: result.path,
            bridgeCount: result.bridgeNodes.length,
            totalHops: result.totalHops
          });

          reachable = computeReachableWithinAllowed();
          orphans = collectOrphans();
        } else {
          orphanInfoMap.set(targetId, {
            requiredBridgeCount: BRIDGE_CONFIG.maxBridgeNodesPerPath + 1,
            totalHops: null,
            reason: "NO_PATH"
          });
        }

        iterations += 1;
      }

      if (orphans.length > 0) {
        orphans.forEach((id) => {
          if (!orphanInfoMap.has(id)) {
            orphanInfoMap.set(id, {
              requiredBridgeCount: BRIDGE_CONFIG.maxBridgeNodesPerPath + 1,
              totalHops: null,
              reason: "BRIDGE_BUDGET"
            });
          }
        });
      }
    };

    enforceConnectivity();

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
      const tpotnessScore = getTpotnessFor(id, meta.username);
      const val = 10 + inGroupScore * 26 + (isSeed ? 6 : 0) + (isShadow ? 2 : 0);
      const connectorInfo = bridgeConnectorMap.get(id);
      const targetBridgeInfo = bridgeTargetMap.get(id);
      const orphanInfo = orphanInfoMap.get(id);

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
        isBridge: Boolean(connectorInfo),
        bridgeConnectorInfo: connectorInfo
          ? {
              supports: Array.from(connectorInfo.supports),
              samples: connectorInfo.samples
            }
          : null,
        bridgeTargetInfo: targetBridgeInfo || null,
        orphanInfo: orphanInfo || null,
        neighbors: [],
        ...meta
      };
    }).filter(Boolean);



    const bridgeDiagnostics = {
      connectors: bridgeConnectorMap,
      targets: bridgeTargetMap,
      orphans: orphanInfoMap
    };

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
        totalNodes: (() => {
          const raw = data.graph?.directed_nodes;
          if (typeof raw === "number") return raw;
          if (Array.isArray(raw)) return raw.length;
          if (raw && typeof raw === "object") return Object.keys(raw).length;
          return nodeIds.length;
        })(),
        totalDirectedEdges: (() => {
          const raw = data.graph?.directed_edges;
          if (typeof raw === "number") return raw;
          if (Array.isArray(raw)) return raw.length;
          if (raw && typeof raw === "object") return Object.keys(raw).length;
          return edges.length;
        })(),
        totalUndirectedEdges: (() => {
          const raw = data.graph?.undirected_edges;
          if (typeof raw === "number") return raw;
          if (Array.isArray(raw)) return raw.length;
          if (raw && typeof raw === "object") return Object.keys(raw).length;
          return 0;
        })(),
        mutualEdgeCount,
        visibleEdges: filteredLinks.length,
        visibleMutualEdges,
        visibleShadowNodes: nodes.filter((node) => node.shadow).length,
        visibleShadowEdges: filteredLinks.filter((edge) => edge.shadow).length,
        usingStructuralFallback: !metricsReady,
        bridgeNodeCount: bridgeConnectorMap.size,
        orphanCount: orphanInfoMap.size
      },
      bridgeDiagnostics
    };
  }, [data, tpotnessScores, effectiveSeedSet, includeShadows, metricsData, mutualOnly, metricsReady, getTpotnessFor, subgraphSize]);

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

  const handlePresetChange = (event) => {
    const name = event.target.value;
    setPresetName(name);
    if (name === "Custom") {
      applyCustomSeedList(customSeeds, { keepPresetName: true });
      return;
    }
    const presetSeeds = availablePresets[name] || [];
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
