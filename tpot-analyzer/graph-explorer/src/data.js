// This file will contain the logic for fetching data from the backend.
// For now, it provides placeholder data to allow for UI development.

const mockData = {
  graph: {
    nodes: {
      '1': { username: 'seed1', followers_count: 1000 },
      '2': { username: 'seed2', followers_count: 2000 },
      '3': { username: 'node3', followers_count: 500 },
      '4': { username: 'node4', followers_count: 800 },
      '5': { username: 'node5', followers_count: 1200 },
    },
    edges: [
      { source: '1', target: '2', mutual: true },
      { source: '1', target: '3', mutual: true },
      { source: '2', target: '4', mutual: false },
      { source: '3', target: '5', mutual: true },
    ],
  },
  metrics: {
    pagerank: {
      '1': 0.25,
      '2': 0.2,
      '3': 0.15,
      '4': 0.1,
      '5': 0.05,
    },
    betweenness: {
        '1': 0.5,
        '2': 0.4,
        '3': 0.3,
        '4': 0.2,
        '5': 0.1,
    },
    communities: {
        '1': 0,
        '2': 0,
        '3': 0,
        '4': 1,
        '5': 0,
    },
    engagement: {},
  },
  seeds: ['seed1', 'seed2'],
  resolved_seeds: ['1', '2'],
};

export const fetchGraphData = async () => {
  const response = await fetch('http://localhost:5001/api/graph-data');
  if (!response.ok) {
    throw new Error('Failed to fetch graph data from the local API server.');
  }
  return response.json();
};