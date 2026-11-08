import { Link } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, AlertTriangle, HelpCircle, BadgeCheck } from 'lucide-react';
import { verdictMeta } from '../types';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const sampleItems = [
  { id: 'demo-1', filename: 'sample-landscape.jpg', verdict: 'LIKELY_REAL', confidence: 0.92, created_at: '2026-01-12T10:00:00Z' },
  { id: 'demo-2', filename: 'sample-portrait.png', verdict: 'INCONCLUSIVE', confidence: 0.61, created_at: '2026-01-11T14:23:00Z' },
  { id: 'demo-3', filename: 'city-ai-example.webp', verdict: 'LIKELY_AI_MANIPULATED', confidence: 0.87, created_at: '2026-01-10T09:15:00Z' },
];

const sampleReport = {
  analysis: { verdict: 'LIKELY_REAL', confidence: 0.92, filename: 'sample-landscape.jpg' },
  explanation: 'PRNU residual consistency and low ELA error suggest an authentic camera capture. FFT radial peakiness is within typical bounds.',
  detectors: [
    { method: 'PRNU', score: 0.88, confidence: 0.9, interpretation: 'Strong sensor fingerprint correlation' },
    { method: 'ELA', score: 0.15, confidence: 0.85, interpretation: 'Low recompression artifacts' },
    { method: 'FFT', score: 0.22, confidence: 0.8, interpretation: 'Natural frequency distribution' },
  ],
};

export default function DemoPage() {
  if (!DEMO_MODE) {
    return (
      <div className="min-h-screen bg-void p-8 text-center">
        <p className="text-slate-400">Demo mode is disabled. Set VITE_DEMO_MODE=true to enable.</p>
        <Link to="/" className="mt-4 inline-block text-violet-300">Back to Home</Link>
      </div>
    );
  }

  const meta = verdictMeta[sampleReport.analysis.verdict];

  return (
    <div className="min-h-screen bg-void text-white">
      <div className="border-b border-amber-500/30 bg-amber-500/10">
        <div className="mx-auto max-w-6xl px-4 py-2 text-center text-sm font-semibold text-amber-200">
          DEMO MODE — Sample data only. No real analysis is performed. Sign-in is disabled for this temporary presentation.
        </div>
      </div>

      <div className="mx-auto max-w-6xl p-4 space-y-6">
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-1 text-sm text-slate-300"><ArrowLeft size={14} /> Back to Home</Link>
          <h1 className="ml-auto text-lg font-bold">PixelForensics Demo</h1>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          {[
            ['Total sample analyses', sampleItems.length],
            ['Likely Real', sampleItems.filter(i => i.verdict === 'LIKELY_REAL').length],
            ['Flagged', sampleItems.filter(i => i.verdict === 'LIKELY_AI_MANIPULATED').length],
            ['Inconclusive', sampleItems.filter(i => i.verdict === 'INCONCLUSIVE').length],
          ].map(([k, v]) => (
            <div key={k as string} className="glass card-hover p-4">
              <p className="text-xs text-slate-400">{k as string}</p>
              <p className="text-2xl font-bold">{v as number}</p>
            </div>
          ))}
        </div>

        <div className="glass p-4">
          <p className="font-semibold mb-2">Sample analysis history (static)</p>
          <div className="space-y-2">
            {sampleItems.map(i => {
              const vm = verdictMeta[i.verdict];
              return (
                <div key={i.id} className="flex items-center justify-between rounded-xl border border-white/10 px-3 py-2 text-sm">
                  <span className="truncate">{i.filename}</span>
                  <span className={vm.color}>{vm.label} · {Math.round(i.confidence * 100)}%</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className={`flex flex-wrap items-center gap-4 rounded-2xl border p-5 ${meta.bg}`}>
          {sampleReport.analysis.verdict === 'LIKELY_REAL' ? <ShieldCheck size={40} className={meta.color} /> : sampleReport.analysis.verdict === 'INCONCLUSIVE' ? <HelpCircle size={40} className={meta.color} /> : <AlertTriangle size={40} className={meta.color} />}
          <div>
            <p className={`text-2xl font-bold ${meta.color}`}>{meta.label}</p>
            <p className="max-w-xl text-sm text-slate-300">{sampleReport.explanation}</p>
          </div>
          <div className="ml-auto text-right">
            <p className="text-xs text-slate-400">Confidence</p>
            <p className="text-xl font-bold">{Math.round(sampleReport.analysis.confidence * 100)}%</p>
          </div>
        </div>

        <div className="glass p-4">
          <p className="font-semibold mb-3 flex items-center gap-2"><BadgeCheck size={16} className="text-cyan-300" /> Sample forensic indicators</p>
          <div className="grid gap-3 md:grid-cols-3">
            {sampleReport.detectors.map(d => (
              <div key={d.method} className="rounded-xl border border-white/10 p-3">
                <p className="font-semibold">{d.method}</p>
                <p className="text-xs text-slate-400">{d.interpretation}</p>
                <p className="mt-1 text-xs">Score: {d.score.toFixed(2)} · Confidence: {Math.round(d.confidence * 100)}%</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-slate-500">Heatmaps and frequency spectra are illustrated with sample images. No real image processing is performed in demo mode.</p>
        </div>

        <div className="glass p-4">
          <p className="font-semibold">Sample report</p>
          <p className="text-sm text-slate-300 mt-2">This is a static example report. In production, reports are generated from authenticated analyses and can be downloaded as PDF/JSON.</p>
          <div className="mt-3 flex gap-2">
            <button disabled className="rounded-xl border border-white/10 px-3 py-1.5 text-xs opacity-50">Download PDF (demo)</button>
            <button disabled className="rounded-xl border border-white/10 px-3 py-1.5 text-xs opacity-50">Download JSON (demo)</button>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600">Admin dashboard, user management, audit logs and real customer data remain protected server-side.</p>
      </div>
    </div>
  );
}
