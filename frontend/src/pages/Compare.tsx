import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useAuth, describeError } from '../services/auth';

export default function ComparePage() {
  const { authFetch } = useAuth();
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    if (files.length < 2) { alert('Select 2-4 images.'); return; }
    setBusy(true);
    const fd = new FormData();
    files.slice(0, 4).forEach((f) => fd.append('files', f));
    try {
      const r = await authFetch('/api/compare', { method: 'POST', body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || 'Compare failed');
      setResult(await r.json());
    } catch (e: any) { alert(describeError(e, 'Compare failed.')); }
    setBusy(false);
  };
  return (
    <div className="min-h-screen bg-void p-4">
      <div className="mx-auto max-w-4xl space-y-4">
        <Link to="/dashboard" className="flex items-center gap-1 text-sm text-slate-300"><ArrowLeft size={14} /> Back to Dashboard</Link>
        <h1 className="text-2xl font-bold">Compare Camera Fingerprints</h1>
        <p className="text-sm text-slate-400">Upload 2-4 images. Residual cross-correlation hints whether they share a source pipeline.</p>
        <input type="file" multiple accept="image/jpeg,image/png,image/webp" className="input"
          onChange={(e) => setFiles(Array.from(e.target.files || []))} />
        <button onClick={go} disabled={busy} className="btn-primary disabled:opacity-50">{busy ? 'Comparing…' : 'Compare'}</button>
        {result && (
          <div className="glass space-y-2 p-5">
            <p className="font-semibold">Verdict: {result.verdict} (mean correlation {result.mean_correlation})</p>
            {result.pairs.map((p: any, i: number) => (
              <p key={i} className="text-sm text-slate-300">{p.a} vs {p.b}: {p.correlation} — {p.interpretation}</p>
            ))}
            <p className="text-xs text-slate-500">{result.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}
