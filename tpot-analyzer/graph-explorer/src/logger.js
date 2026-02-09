import { API_BASE_URL } from './config';

const LOG_ENDPOINT = `${API_BASE_URL}/api/log`;

const LEVELS = ['debug', 'info', 'warn', 'error'];

function logToBackend(entry) {
  try {
    fetch(LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    }).catch(() => {});
  } catch {
    // swallow
  }
}

function createLogger(namespace) {
  const log = (level, message, payload = {}) => {
    const entry = { level, message: `[${namespace}] ${message}`, payload };
    const consoleFn = console[level] || console.log;
    consoleFn(entry.message, payload);
    logToBackend(entry);
  };

  return {
    debug: (msg, p) => log('debug', msg, p),
    info: (msg, p) => log('info', msg, p),
    warn: (msg, p) => log('warn', msg, p),
    error: (msg, p) => log('error', msg, p),
  };
}

export const apiLog = createLogger('API');
export const clusterViewLog = createLogger('ClusterView');
export const canvasLog = createLogger('ClusterCanvas');
