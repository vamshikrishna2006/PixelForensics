import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { LogOut, RefreshCw } from 'lucide-react';
import { useAuth } from '../services/auth';

/** Traffic-light levels shared by every health tile. */
type Level = 'ok' | 'warn' | 'down' | 'unknown';

const levelStyle: Record<Level, { dot: string; text: string; chip: string; label: string }> = {
  ok: { dot: 'bg-green-500', text: 'text-green-400', chip: 'border-green-500/30 bg-green-500/10', label: 'Healthy' },
  warn: { dot: 'bg-yellow-400', text: 'text-yellow-300', chip: 'border-yellow-500/30 bg-yellow-500/10', label: 'Warning' },
  down: { dot: 'bg-red-500', text: 'text-red-400', chip: 'border-red-500/30 bg-red-500/10', label: 'Down' },
  unknown: { dot: 'bg-slate-500', text: 'text-slate-400', chip: 'border-white/10 bg-white/5', label: 'Unknown' },
};

function Chip({ level }: { level: Level }) {
  const s = levelStyle[level];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${s.chip} ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot} ${level === 'down' ? 'animate-pulse' : ''}`} />
      {s.label}
    </span>
  );
}

function Tile({ label, level, value, hint }: { label: string; level: Level; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-slate-400">{label}</p>
        <Chip level={level} />
      </div>
      <p className="mt-1 text-lg font-bold">{value}</p>
      {hint ? <p className="truncate text-xs text-slate-500" title={hint}>{hint}</p> : null}
    </div>
  );
}


export default function AdminPage() {
  const { authFetch, logout } = useAuth();
  const nav = useNavigate();
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [monitoring, setMonitoring] = useState<any>(null);
  const [monitoringError, setMonitoringError] = useState<string | null>(null);
  const [monitoringBusy, setMonitoringBusy] = useState(false);
  const [alertNote, setAlertNote] = useState<string | null>(null);

  const loadHealth = async () => {
    setChecking(true);
    try {
      const r = await authFetch('/api/admin/system-health');
      if (!r.ok) throw new Error(`System health check failed (HTTP ${r.status})`);
      setHealth(await r.json());
      setHealthError(null);
    } catch (e: any) {
      setHealth(null);
      setHealthError(e?.message || 'System health check failed.');
    } finally {
      setChecking(false);
    }
  };

  const loadMonitoring = async () => {
    setMonitoringBusy(true);
    try {
      const r = await authFetch('/api/admin/monitoring');
      if (!r.ok) throw new Error(`Monitoring check failed (HTTP ${r.status})`);
      setMonitoring(await r.json());
      setMonitoringError(null);
    } catch (e: any) {
      setMonitoring(null);
      setMonitoringError(e?.message || 'Monitoring check failed.');
    } finally {
      setMonitoringBusy(false);
    }
  };

  const runBackup = async () => {
    setMonitoringBusy(true);
    setAlertNote(null);
    try {
      const r = await authFetch('/api/admin/backups/run', { method: 'POST' });
      if (!r.ok) throw new Error('Backup could not be started.');
      await loadMonitoring();
    } catch (e: any) {
      setMonitoringError(e?.message || 'Backup could not be started.');
    } finally {
      setMonitoringBusy(false);
    }
  };

  const verifyRestore = async () => {
    setMonitoringBusy(true);
    setAlertNote(null);
    try {
      const r = await authFetch('/api/admin/backups/verify', { method: 'POST' });
      if (!r.ok) throw new Error('Restore verification could not be started.');
      await loadMonitoring();
    } catch (e: any) {
      setMonitoringError(e?.message || 'Restore verification could not be started.');
    } finally {
      setMonitoringBusy(false);
    }
  };

  const testAlert = async () => {
    setMonitoringBusy(true);
    try {
      const r = await authFetch('/api/admin/monitoring/test-alert', { method: 'POST' });
      if (!r.ok) throw new Error('Test alert could not be queued.');
      const data = await r.json();
      setAlertNote(data.note || 'Test alert recorded.');
      await loadMonitoring();
    } catch (e: any) {
      setMonitoringError(e?.message || 'Test alert could not be queued.');
    } finally {
      setMonitoringBusy(false);
    }
  };

  useEffect(() => {
    authFetch('/api/admin/statistics').then((r) => r.json()).then(setStats).catch(() => {});
    authFetch('/api/admin/users').then((r) => r.json()).then(setUsers).catch(() => {});
    void loadHealth();
    void loadMonitoring();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const pie = stats ? [
    { name: 'Real', value: stats.real }, { name: 'Flagged', value: stats.fake }, { name: 'Inconclusive', value: stats.inconclusive },
  ] : [];

  // --- health levels ------------------------------------------------------
  const apiLevel: Level = health ? 'ok' : healthError ? 'down' : 'unknown';
  const dbLevel: Level = !health ? (healthError ? 'down' : 'unknown') : health.database === 'healthy' ? 'ok' : 'down';
  const freeGb: number | null =
    typeof health?.disk_free_gb === 'number' ? health.disk_free_gb
      : typeof health?.storage_free_gb === 'number' ? health.storage_free_gb : null;
  const freeLevel: Level = freeGb == null ? 'unknown' : freeGb < 1 ? 'down' : freeGb < 5 ? 'warn' : 'ok';
  const storageLevel: Level = !health ? 'unknown'
    : !health.storage_writable ? 'down'
      : health.storage_exists === false ? 'warn' : 'ok';
  const usedPct: number | null = typeof health?.disk_used_pct === 'number' ? health.disk_used_pct : null;
  const usedLevel: Level = usedPct == null ? 'unknown' : usedPct >= 90 ? 'down' : usedPct >= 75 ? 'warn' : 'ok';
  const barColor = usedLevel === 'down' ? 'bg-red-500' : usedLevel === 'warn' ? 'bg-yellow-400' : 'bg-green-500';

  const levels = [apiLevel, dbLevel, freeLevel, storageLevel, usedLevel];
  const overall: Level = !health ? (healthError ? 'down' : 'unknown')
    : levels.includes('down') ? 'down' : levels.includes('warn') ? 'warn' : 'ok';

  const checkedAt = health?.checked_at ? new Date(health.checked_at).toLocaleTimeString() : null;

  const fmtTs = (value: unknown) => {
    if (!value) return 'Never';
    const date = new Date(String(value));
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  };
  const latestBackup = monitoring?.backup?.latest;
  const lastSuccess = monitoring?.backup?.last_success;
  const latestRestore = monitoring?.backup?.latest_restore;
  const backupLevel: Level = latestBackup
    ? latestBackup.status === 'success' ? 'ok' : latestBackup.status === 'failed' ? 'down' : 'warn'
    : 'unknown';
  const restoreLevel: Level = latestRestore
    ? latestRestore.status === 'success' ? 'ok' : latestRestore.status === 'failed' ? 'down' : 'warn'
    : 'unknown';
  const alertLevel: Level = monitoring
    ? monitoring.alert_delivery_configured ? 'ok' : 'warn'
    : 'unknown';
  const monitoringLevel: Level = monitoringError ? 'down' : monitoring ? 'ok' : 'unknown';
  const recentErrors: any[] = monitoring?.recent_errors || [];
  const recentAlerts: any[] = monitoring?.recent_alerts || [];

  return (
    <div className="min-h-screen bg-void p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">Admin Dashboard</h1>
          <Link to="/dashboard" className="ml-auto rounded-xl border border-white/10 px-4 py-2 text-sm">Customer view</Link>
          <button onClick={() => { logout(); nav('/'); }}
            className="flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2 text-sm transition hover:border-red-400/50 hover:bg-red-500/10 hover:text-red-300">
            <LogOut size={16} /> Logout
          </button>
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          {[['Total users', stats?.total_users], ['Total analyses', stats?.total_analyses], ['Avg processing (s)', stats?.avg_processing_s], ['Algorithm', stats?.algorithm_version]].map(([k, v]) => (
            <div key={k as string} className="glass p-4"><p className="text-xs text-slate-400">{k as string}</p><p className="text-xl font-bold">{String(v ?? '…')}</p></div>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="glass p-4"><p className="font-semibold">Verdict distribution</p>
            <div className="h-56"><ResponsiveContainer><PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" outerRadius={80} label>
                <Cell fill="#22c55e" /><Cell fill="#ef4444" /><Cell fill="#eab308" />
              </Pie><Tooltip /></PieChart></ResponsiveContainer></div></div>
          <div className="glass p-4"><p className="font-semibold">Verdict counts</p>
            <div className="h-56"><ResponsiveContainer><BarChart data={pie}>
              <XAxis dataKey="name" /><YAxis /><Tooltip /><Bar dataKey="value" fill="#8b5cf6" />
            </BarChart></ResponsiveContainer></div></div>
        </div>
        <div className="glass p-4">
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-semibold">System health</p>
            <Chip level={overall} />
            <span className="text-xs text-slate-500">
              {healthError ? healthError : checking ? 'Checking…' : checkedAt ? `Last checked ${checkedAt}` : 'No data yet'}
            </span>
            <button onClick={() => void loadHealth()} disabled={checking}
              className="ml-auto flex items-center gap-2 rounded-xl border border-white/10 px-3 py-1.5 text-xs transition hover:border-white/30 disabled:opacity-50">
              <RefreshCw size={14} className={checking ? 'animate-spin' : ''} /> {checking ? 'Checking…' : 'Re-check'}
            </button>
          </div>
          {healthError ? (
            <p className="mt-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{healthError}</p>
          ) : null}
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="API server" level={apiLevel} value={health ? 'Responding' : 'No response'}
              hint={health ? `Algorithm v${health.algorithm_version ?? '—'}` : 'Backend unreachable'} />
            <Tile label="Database" level={dbLevel}
              value={health ? (health.database === 'healthy' ? 'Connected' : 'Error') : 'Unknown'}
              hint={health?.database_latency_ms != null ? `${health.database_latency_ms} ms ping`
                : health?.database_detail ?? undefined} />
            <Tile label="Storage folder" level={storageLevel}
              value={health ? (health.storage_writable ? 'Writable' : 'Read-only / missing') : 'Unknown'}
              hint={health ? `${health.storage_files ?? 0} files · ${health.storage_size_mb ?? 0} MB` : undefined} />
            <Tile label="Free disk" level={freeLevel}
              value={freeGb != null ? `${freeGb} GB` : 'Unknown'}
              hint={health?.disk_total_gb != null ? `of ${health.disk_total_gb} GB total` : undefined} />
          </div>
          {usedPct != null ? (
            <div className="mt-4">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Disk usage</span>
                <span>{usedPct}% used · {freeGb ?? '—'} GB free</span>
              </div>
              <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-white/10">
                <div className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${Math.min(100, Math.max(0, usedPct))}%` }} />
              </div>
            </div>
          ) : null}
          <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3">
            <p>Analyses stored: <span className="font-semibold text-slate-200">{health?.total_analyses ?? stats?.total_analyses ?? '—'}</span></p>
            <p>Avg processing: <span className="font-semibold text-slate-200">{health?.avg_processing_s ?? stats?.avg_processing_s ?? '—'} s</span></p>
            <p className="truncate" title={health?.storage_path}>Storage path: <span className="font-semibold text-slate-200">{health?.storage_path ?? '—'}</span></p>
          </div>
        </div>
        <div className="glass p-4">
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-semibold">Monitoring &amp; backups</p>
            <Chip level={monitoringLevel} />
            <span className="text-xs text-slate-500">
              {monitoringError ? monitoringError : monitoring ? 'Live from the backend' : 'Loading...'}
            </span>
            <button onClick={() => void loadMonitoring()} disabled={monitoringBusy}
              className="ml-auto flex items-center gap-2 rounded-xl border border-white/10 px-3 py-1.5 text-xs transition hover:border-white/30 disabled:opacity-50">
              <RefreshCw size={14} className={monitoringBusy ? 'animate-spin' : ''} /> {monitoringBusy ? 'Checking...' : 'Refresh'}
            </button>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Tile label="Backup status" level={backupLevel}
              value={String(latestBackup?.status ?? 'Never')}
              hint={monitoring?.backup?.enabled ? 'Automatic daily schedule enabled' : 'In-process scheduler disabled'} />
            <Tile label="Last successful backup" level={lastSuccess ? 'ok' : 'warn'}
              value={lastSuccess ? fmtTs(lastSuccess.finished_at) : 'Never'}
              hint={monitoring?.backup ? `Retention ${monitoring.backup.retention_days} days` : undefined} />
            <Tile label="Restore verification" level={restoreLevel}
              value={String(latestRestore?.status ?? 'Not run')}
              hint={latestRestore?.finished_at ? fmtTs(latestRestore.finished_at) : 'Run a verification to check the latest backup'} />
            <Tile label="Failed analyses (24h)" level={monitoring ? (Number(monitoring.failed_analyses_24h) > 0 ? 'warn' : 'ok') : 'unknown'}
              value={monitoring ? String(monitoring.failed_analyses_24h ?? 0) : '—'}
              hint="Pipeline failures recorded in structured logs" />
            <Tile label="Critical errors (24h)" level={monitoring ? (Number(monitoring.critical_errors_24h) > 0 ? 'warn' : 'ok') : 'unknown'}
              value={monitoring ? String(monitoring.critical_errors_24h ?? 0) : '—'}
              hint="Error/critical records in the last 24 hours" />
            <Tile label="Alert delivery" level={alertLevel}
              value={monitoring?.alert_delivery_configured ? 'Configured' : 'Dashboard only'}
              hint={monitoring?.alert_delivery_configured ? 'Webhook or SMTP destination set' : 'No external destination configured'} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={() => void runBackup()} disabled={monitoringBusy}
              className="rounded-xl border border-white/10 px-3 py-1.5 text-xs transition hover:border-violet-400/50 disabled:opacity-50">
              Run backup now
            </button>
            <button onClick={() => void verifyRestore()} disabled={monitoringBusy}
              className="rounded-xl border border-white/10 px-3 py-1.5 text-xs transition hover:border-cyan-400/50 disabled:opacity-50">
              Verify restore
            </button>
            <button onClick={() => void testAlert()} disabled={monitoringBusy}
              className="rounded-xl border border-white/10 px-3 py-1.5 text-xs transition hover:border-amber-400/50 disabled:opacity-50">
              Test alert
            </button>
          </div>
          {alertNote ? (
            <p className="mt-2 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200">{alertNote}</p>
          ) : null}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <p className="text-sm font-semibold">Recent critical errors</p>
              <div className="mt-2 max-h-56 space-y-2 overflow-auto text-xs">
                {recentErrors.map((e, i) => (
                  <div key={`${e.request_id || 'error'}-${i}`} className="rounded-lg border border-white/10 bg-black/20 p-2">
                    <p className="text-slate-400">{fmtTs(e.timestamp)} · {e.category} · {e.severity}</p>
                    <p className="text-slate-200">{e.message}</p>
                    <p className="truncate text-slate-500">Request: {e.request_id || '—'}{e.path ? ` · ${e.path}` : ''}</p>
                  </div>
                ))}
                {recentErrors.length === 0 && <p className="text-slate-500">No critical errors recorded.</p>}
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold">Recent system alerts</p>
              <div className="mt-2 max-h-56 space-y-2 overflow-auto text-xs">
                {recentAlerts.map((a, i) => (
                  <div key={`${a.fingerprint || 'alert'}-${i}`} className="rounded-lg border border-white/10 bg-black/20 p-2">
                    <p className="text-slate-400">{fmtTs(a.timestamp)} · {a.category} · {a.severity}</p>
                    <p className="text-slate-200">{a.message}</p>
                    <p className="text-slate-500">Delivery: {a.delivery || 'unknown'} · occurrences: {a.occurrences_last_hour ?? '—'}</p>
                  </div>
                ))}
                {recentAlerts.length === 0 && <p className="text-slate-500">No alerts recorded.</p>}
              </div>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            External alerts are {monitoring?.alert_delivery_configured ? 'configured' : 'not configured; records are kept in the dashboard and server log only'}. No secrets are shown in this panel.
          </p>
        </div>
        <div className="glass p-4"><p className="font-semibold">Users ({users.length})</p>
          <div className="mt-2 max-h-72 overflow-auto text-sm">
            {users.map((u) => (<p key={u.id} className="border-b border-white/5 py-1">{u.username} · {u.email} · {u.role} · {u.status}</p>))}
          </div></div>
      </div>
    </div>
  );
}
