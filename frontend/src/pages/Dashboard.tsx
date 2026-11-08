import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth, describeError } from '../services/auth';
import type { AnalysisItem } from '../types';
import { verdictMeta } from '../types';
import { Reveal, Stagger, StaggerItem } from '../components/Reveal';
import UploadZone from '../components/UploadZone';
import AnalysisProgress from '../components/AnalysisProgress';

export function DashboardHome() {
  const { user, authFetch } = useAuth();
  const [items, setItems] = useState<AnalysisItem[]>([]);
  useEffect(() => {
    authFetch('/api/analysis/history').then((r) => r.json()).then(setItems).catch(() => {});
  }, []);
  return (
    <div className="relative space-y-5">
      <div className="pointer-events-none absolute inset-x-0 top-[-80px] -z-10 h-64">
        <div className="orb orb-violet left-[10%] top-0 h-56 w-72" />
        <div className="orb orb-cyan right-[5%] top-0 h-56 w-72" />
      </div>
      <Reveal>
      <div className="relative overflow-hidden rounded-2xl border border-white/10">
        <img src="https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=1600&auto=format&fit=crop" alt="Forensic sky" className="img-crazy h-40 w-full object-cover md:h-48" loading="lazy" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#05060f]/90 via-[#05060f]/45 to-transparent" />
        <div className="absolute inset-0 flex items-center p-5">
          <div><h1 className="text-2xl font-bold md:text-3xl">Welcome back, {user?.username}!</h1>
          <p className="text-sm text-slate-300">Let's uncover the truth behind your images.</p></div>
        </div>
      </div>
      </Reveal>
      <Stagger className="grid gap-4 md:grid-cols-4">
        {[['Total analyses', items.length], ['Likely Real', items.filter((i) => i.verdict === 'LIKELY_REAL').length], ['Flagged', items.filter((i) => i.verdict === 'LIKELY_AI_MANIPULATED').length], ['Inconclusive', items.filter((i) => i.verdict === 'INCONCLUSIVE').length]].map(([k, v]) => (
          <StaggerItem key={k as string} className="glass card-hover p-4"><p className="text-xs text-slate-400">{k as string}</p><p className="text-2xl font-bold">{v as number}</p></StaggerItem>
        ))}
      </Stagger>
      <Reveal className="glass p-4">
        <p className="font-semibold">Recent analyses</p>
        <div className="mt-2 space-y-2">
          {items.slice(0, 5).map((i) => (
            <Link key={i.id} to={`/report/${i.id}`} className="flex items-center justify-between rounded-xl border border-white/10 px-3 py-2 text-sm hover:border-violet-400">
              <span className="truncate">{i.filename}</span>
              <span className={verdictMeta[i.verdict]?.color}>{verdictMeta[i.verdict]?.label} · {Math.round(i.confidence * 100)}%</span>
            </Link>
          ))}
          {items.length === 0 && <p className="text-sm text-slate-500">No analyses yet — run your first scan below.</p>}
        </div>
      </Reveal>
      <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
      <Link to="/dashboard/new" className="btn-primary inline-block">+ New Image Analysis</Link>
      </motion.div>
    </div>
  );
}

export function NewAnalysis() {
  const { authFetch } = useAuth();
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await authFetch('/api/analyze', { method: 'POST', body: fd });
      if (!r.ok) {
        let msg = 'Analysis failed';
        try { const j = await r.json(); msg = (j as any).detail || msg; } catch {}
        throw new Error(`${msg} (HTTP ${r.status})`);
      }
      const report = await r.json();
      nav(`/report/${report.analysis.id}`, { state: { report, preview: URL.createObjectURL(file) } });
    } catch (e: any) { alert(describeError(e, 'Analysis failed.')); setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">New Analysis</h1>
      <UploadZone onFile={setFile} onAnalyze={go} busy={busy} />
      <AnalysisProgress active={busy} />
    </div>
  );
}

export function History() {
  const { authFetch } = useAuth();
  const [items, setItems] = useState<AnalysisItem[]>([]);
  const [q, setQ] = useState('');
  useEffect(() => {
    authFetch('/api/analysis/history').then((r) => r.json()).then(setItems).catch(() => {});
  }, []);
  const del = async (id: string) => {
    if (!confirm('Delete this analysis?')) return;
    await authFetch(`/api/analysis/${id}`, { method: 'DELETE' });
    setItems(items.filter((i) => i.id !== id));
  };
  const list = items.filter((i) => i.filename.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">My Analysis History</h1>
      <input className="input max-w-sm" placeholder="Search your analysis…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="space-y-2">
        {list.map((i) => (
          <div key={i.id} className="glass flex items-center justify-between gap-3 p-3">
            <div className="min-w-0"><p className="truncate text-sm font-semibold">{i.filename}</p>
              <p className="text-xs text-slate-500">{new Date(i.created_at).toLocaleString()}</p></div>
            <span className={`rounded-full border px-3 py-1 text-xs ${verdictMeta[i.verdict]?.bg} ${verdictMeta[i.verdict]?.color}`}>{verdictMeta[i.verdict]?.label} · {Math.round(i.confidence * 100)}%</span>
            <div className="flex gap-2">
              <Link to={`/report/${i.id}`} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs">Open</Link>
              <button onClick={() => del(i.id)} className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-300">Delete</button>
            </div>
          </div>
        ))}
        {list.length === 0 && <p className="text-sm text-slate-500">Nothing found.</p>}
      </div>
    </div>
  );
}

export function Profile() {
  const { user } = useAuth();
  return (
    <div className="glass space-y-2 p-6">
      <h1 className="text-2xl font-bold">Profile</h1>
      <p className="text-sm">Username: {user?.username}</p>
      <p className="text-sm">Email: {user?.email}</p>
      <p className="text-sm">Role: {user?.role} (enforced server-side)</p>
    </div>
  );
}
