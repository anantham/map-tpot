const LOG_ENDPOINT = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/log`
  : 'http://localhost:5001/api/log';

const LEVELS = ['debug', 'info', 'warn', 'error'];

function logToBackend(entry) {
  try {
    fetch(LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    }).catch(() => {});
  } catch (_) {
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
