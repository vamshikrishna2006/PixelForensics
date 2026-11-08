import { VisualTab, MetadataPanel, ForensicPanel, ExplainPanel } from './ReportPanels';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useParams, Link } from 'react-router-dom';
import { useAuth, describeError } from '../services/auth';
import type { Report } from '../types';
import { verdictMeta } from '../types';
import ConfidenceMeter from '../components/ConfidenceMeter';
import { Download, ArrowLeft, ShieldCheck, AlertTriangle, HelpCircle, Loader2 } from 'lucide-react';

export default function ReportPage() {
  const { id } = useParams();
  const loc = useLocation() as any;
  const { authFetch } = useAuth();
  const [report, setReport] = useState<Report | null>(loc.state?.report || null);
  const [tab, setTab] = useState('visual');
  const [heat, setHeat] = useState(true);
  const [opacity, setOpacity] = useState(0.55);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);
  const pdfBusyRef = useRef(false); // synchronous guard against double-clicks

  useEffect(() => {
    if (!report) authFetch(`/api/analysis/${id}`).then((r) => r.json()).then(setReport).catch(() => {});
  }, []);
  if (!report) return <p className="p-8">Loading report…</p>;
  const meta = verdictMeta[report.analysis.verdict];
  const Icon = report.analysis.verdict === 'LIKELY_REAL' ? ShieldCheck : report.analysis.verdict === 'INCONCLUSIVE' ? HelpCircle : AlertTriangle;
  const download = async (kind: 'pdf' | 'json') => {
    // The PDF button shows a loading state and must not fire twice.
    if (kind === 'pdf') {
      if (pdfBusyRef.current) return;
      pdfBusyRef.current = true;
      setPdfBusy(true);
      setDlError(null);
    }
    try {
      const r = await authFetch(`/api/report/${id}/${kind}`);
      if (!r.ok) throw new Error(`Report generation failed (HTTP ${r.status}).`);
      const cd = r.headers.get('content-disposition') || '';
      const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const serverName = m ? decodeURIComponent(m[1]) : null;
      const fallback = `${report?.report_name || 'PixelForensics-Report'}-Forensic-Report.${kind}`;
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement('a');
      a.href = u; a.download = serverName || fallback;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(u);
    } catch (e) {
      const msg = describeError(e, 'Could not generate the report. Please try again.');
      if (kind === 'pdf') setDlError(msg); else alert(msg);
    } finally {
      if (kind === 'pdf') { pdfBusyRef.current = false; setPdfBusy(false); }
    }
  };

  return (
    <div className="min-h-screen space-y-4 bg-void p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/dashboard" className="flex items-center gap-1 text-sm text-slate-300"><ArrowLeft size={14} /> Back to Dashboard</Link>
          <span className="ml-auto flex gap-2">
            <button onClick={() => download('json')} className="rounded-xl border border-white/10 px-3 py-1.5 text-xs">JSON</button>
            <button onClick={() => download('pdf')} disabled={pdfBusy}
              className="flex items-center gap-1 rounded-xl bg-violet-600 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60">
              {pdfBusy
                ? <><Loader2 size={12} className="animate-spin" /> Generating Report...</>
                : <><Download size={12} /> Download Report</>}
            </button>
          </span>
        </div>
        {dlError && <p className="text-right text-xs text-red-400">{dlError}</p>}
        <div className={`flex flex-wrap items-center gap-4 rounded-2xl border p-5 ${meta.bg}`}>
          <Icon size={40} className={meta.color} />
          <div><p className={`text-2xl font-bold ${meta.color}`}>{meta.label}</p>
            <p className="max-w-xl text-sm text-slate-300">{report.explanation}</p></div>
          <div className="ml-auto"><ConfidenceMeter value={report.analysis.confidence} verdict={report.analysis.verdict} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {['visual', 'metadata', 'forensic', 'explainable'].map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`rounded-xl px-4 py-2 text-sm capitalize ${tab === t ? 'bg-violet-600/40 border border-violet-400/50' : 'border border-white/10'}`}>{t === 'visual' ? 'Visual Analysis' : t === 'explainable' ? 'Explainable AI' : t}</button>
          ))}
        </div>
        {tab === 'visual' && <VisualTab report={report} preview={loc.state?.preview} heat={heat} setHeat={setHeat} opacity={opacity} setOpacity={setOpacity} />}
        {tab === 'metadata' && <MetadataPanel report={report} />}
        {tab === 'forensic' && <ForensicPanel report={report} />}
        {tab === 'explainable' && <ExplainPanel report={report} />}
        <div className="glass p-4">
          <p className="font-semibold">Suspicious Regions ({report.regions.length})</p>
          {report.regions.map((r) => (
            <p key={r.id} className="mt-1 text-sm text-slate-300">Region #{r.id} — x:{r.x} y:{r.y} w:{r.width} h:{r.height} — {r.reason}</p>
          ))}
          {report.regions.length === 0 && <p className="text-sm text-slate-500">No localized manipulation signal detected (not a guarantee).</p>}
        </div>
      </div>
    </div>
  );
}
