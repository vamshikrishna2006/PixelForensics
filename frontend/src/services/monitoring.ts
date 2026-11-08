/**
 * Lightweight frontend error reporting.
 *
 * Only an error message, stack, source label and the current path are sent.
 * Tokens, passwords, form values and image contents are never included.
 */
const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

let installed = false;
const recent = new Map<string, number>();
let minuteStart = Date.now();
let minuteCount = 0;

function canSend(key: string): boolean {
  const now = Date.now();
  if (now - minuteStart > 60_000) {
    minuteStart = now;
    minuteCount = 0;
  }
  if (minuteCount >= 10) return false;
  const last = recent.get(key) || 0;
  if (now - last < 60_000) return false;
  recent.set(key, now);
  minuteCount += 1;
  return true;
}

export function reportClientError(
  error: unknown,
  source: string,
  extra?: { componentStack?: string },
): void {
  const err = error instanceof Error ? error : new Error(String(error));
  const key = `${source}:${err.message}`;
  if (!canSend(key)) return;

  const body = JSON.stringify({
    message: err.message.slice(0, 500),
    stack: err.stack ? err.stack.slice(0, 4000) : undefined,
    source: source.slice(0, 64),
    url: window.location.pathname,
    component_stack: extra?.componentStack
      ? extra.componentStack.slice(0, 4000)
      : undefined,
  });

  // keepalive lets the report survive a page unload. Failures are ignored:
  // monitoring must never break the UI.
  void fetch(`${API}/api/client-errors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {});
}

export function initErrorMonitoring(): void {
  if (installed) return;
  installed = true;

  window.addEventListener('error', (event) => {
    reportClientError(event.error || event.message, 'window');
  });

  window.addEventListener('unhandledrejection', (event) => {
    reportClientError(event.reason, 'promise');
  });
}