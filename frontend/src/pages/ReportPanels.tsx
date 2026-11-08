import type { Report } from '../types';

export function Spectrum({ data }: { data: number[][] }) {
  if (!data) return <p className="text-xs text-slate-500">No spectrum.</p>;
  const flat = data.flat();
  const mx = Math.max(...flat, 1);
  return (
    <svg viewBox="0 0 64 64" className="mt-2 w-full rounded-lg bg-black" role="img" aria-label="Frequency spectrum">
      {data.map((row, y) => row.map((v, x) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={`rgba(139,92,246,${(v / mx).toFixed(2)})`} />
      )))}
    </svg>
  );
}

export function VisualTab({ report, preview, heat, setHeat, opacity, setOpacity }: any) {
  return (
    <div className="grid gap-4 md:grid-cols-4">
      {preview && <div className="glass p-3"><p className="text-xs">Original Image</p><img src={preview} className="mt-2 rounded-lg" alt="original" /></div>}
      <div className="glass p-3"><p className="text-xs">Noise Residual Map</p><img src={`data:image/png;base64,${report.artifacts.residual_b64}`} className="mt-2 rounded-lg" alt="residual" /></div>
      <div className="glass p-3">
        <p className="text-xs">Heatmap (Suspicious Areas)</p>
        <div className="relative mt-2">
          {preview && <img src={preview} className="rounded-lg" alt="base" />}
          {heat && <img src={`data:image/png;base64,${report.artifacts.heatmap_b64}`} className="absolute inset-0 rounded-lg" style={{ opacity }} alt="heat" />}
        </div>
        <label className="mt-2 flex items-center gap-2 text-xs"><input type="checkbox" checked={heat} onChange={(e) => setHeat(e.target.checked)} /> Heatmap ON/OFF</label>
        <input type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(+e.target.value)} className="w-full" aria-label="Heatmap opacity" />
      </div>
      <div className="glass p-3"><p className="text-xs">Frequency Spectrum</p><Spectrum data={report.artifacts.spectrum} /></div>
    </div>
  );
}

export function MetadataPanel({ report }: { report: Report }) {
  const m = report.detectors.find((d) => d.method === 'METADATA')?.details || {};
  const rows: [string, any][] = [['File Name', report.analysis.filename], ['File Size', `${(report.image_info.size_bytes / 1024).toFixed(1)} KB`], ['Dimensions', `${report.image_info.width} x ${report.image_info.height}`], ['Camera Make', m.make || '—'], ['Camera Model', m.model || '—'], ['Date Taken', m.datetime || '—'], ['Software', m.software || '—'], ['GPS', m.has_gps ? 'Present — hidden for privacy' : 'Not present']];
  return (
    <div className="glass p-4"><p className="font-semibold">Metadata Information</p>
      <table className="mt-2 w-full text-sm">
        <tbody>{rows.map(([k, v]) => (<tr key={k} className="border-b border-white/5"><td className="py-1.5 pr-4 text-slate-400">{k}</td><td>{String(v)}</td></tr>))}</tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">Metadata can be stripped or forged — never treat as proof.</p></div>
  );
}

export function ForensicPanel({ report }: { report: Report }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="glass p-4"><p className="font-semibold">Detector vote breakdown</p>
        <p className="text-xs text-slate-500">Higher = more camera-like. Greyed rows do not apply to this file format.</p>
        {report.breakdown.map((b) => (
          <div key={b.method} className={`mt-2 ${b.applied === false ? 'opacity-40' : ''}`}>
            <div className="flex justify-between text-xs">
              <span>{b.label || b.method}</span>
              <span>{b.applied === false ? 'not applicable' : `${Math.round(b.score * 100)}%`}</span>
            </div>
            <div className="h-2 rounded bg-white/10"><div className="h-full rounded bg-gradient-to-r from-violet-500 to-cyan-300" style={{ width: `${b.score * 100}%` }} /></div>
            <p className="text-xs text-slate-500">{b.interpretation}</p></div>
        ))}</div>
      <div className="glass space-y-3 p-4">
        <p className="font-semibold">ELA</p>
        {report.artifacts.ela_b64 && <img src={`data:image/png;base64,${report.artifacts.ela_b64}`} className="rounded-lg" alt="ELA" />}
        <p className="font-semibold">Wavelet LL / LH / HL / HH</p>
        <div className="grid grid-cols-4 gap-2">
          {report.artifacts.wavelet && Object.entries(report.artifacts.wavelet).map(([k, v]) => (
            <div key={k}><img src={`data:image/png;base64,${v}`} className="rounded-lg" alt={k} /><p className="text-center text-xs">{k}</p></div>
          ))}
        </div>
      </div>
    </div>
  );
}

const DIRECTION_META: Record<string, { label: string; cls: string }> = {
  supports_camera: { label: 'Supports camera', cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' },
  supports_ai: { label: 'Supports synthetic', cls: 'border-red-500/40 bg-red-500/10 text-red-300' },
  neutral: { label: 'Neutral', cls: 'border-amber-500/40 bg-amber-500/10 text-amber-300' },
};

export function ExplainPanel({ report }: { report: Report }) {
  const n = report.narrative;
  return (
    <div className="space-y-4">
      <div className="glass p-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">Deep image analysis</p>
        <p className="mt-2 text-lg font-semibold text-slate-100">{n?.headline || 'Why was this image flagged?'}</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">{n?.summary || report.explanation}</p>
        {n?.engine && <p className="mt-3 text-[11px] uppercase tracking-wide text-slate-500">{n.engine}</p>}
      </div>

      {!!n?.key_findings?.length && (
        <div className="grid gap-3 md:grid-cols-2">
          {n.key_findings.map((f) => {
            const m = DIRECTION_META[f.direction] || DIRECTION_META.neutral;
            return (
              <div key={f.title} className={`rounded-xl border p-4 ${m.cls}`}>
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold">{f.title}</p>
                  <span className="shrink-0 rounded-full border border-current px-2 py-0.5 text-[10px] uppercase tracking-wide">{m.label}</span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-300">{f.detail}</p>
              </div>
            );
          })}
        </div>
      )}

      {!!n?.sections?.length && (
        <div className="space-y-3">
          {n.sections.map((sec) => (
            <div key={sec.title} className="glass p-5">
              <p className="text-sm font-semibold text-violet-200">{sec.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-slate-300">{sec.body}</p>
            </div>
          ))}
        </div>
      )}

      {!!n?.detector_notes?.length ? (
        <div className="glass p-5">
          <p className="font-semibold">How each detector was read</p>
          <p className="mt-1 text-xs text-slate-500">Scores are camera-likeness (higher = more camera-like); weight is that detector&apos;s influence on the final score.</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead><tr className="text-left text-xs text-slate-500">
                <th className="pb-1 pr-3">Detector</th><th className="pb-1 pr-3">What it measures</th>
                <th className="pb-1 pr-3">Reading</th><th className="pb-1 pr-3">Score</th><th className="pb-1">Weight</th>
              </tr></thead>
              <tbody>{n.detector_notes.map((d) => (
                <tr key={d.method} className={`border-t border-white/5 align-top ${d.applied ? '' : 'opacity-50'}`}>
                  <td className="py-2 pr-3 font-medium">{d.title}</td>
                  <td className="py-2 pr-3 text-xs text-slate-400">{d.what_it_measures}</td>
                  <td className="py-2 pr-3 text-xs text-slate-300">{d.reading}</td>
                  <td className="py-2 pr-3">{Math.round(d.score * 100)}%</td>
                  <td className="py-2">{Math.round(d.weight * 100)}%</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="glass p-5"><p className="font-semibold">Why was this image flagged?</p>
          <table className="mt-3 w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-500"><th>Method</th><th>Result</th><th>Confidence</th></tr></thead>
            <tbody>{report.detectors.map((d) => (
              <tr key={d.method} className="border-t border-white/5"><td>{report.breakdown.find((b) => b.method === d.method)?.label || d.method}</td>
                <td className={d.score > 0.6 ? 'text-green-400' : d.score < 0.4 ? 'text-red-400' : 'text-yellow-300'}>{d.score > 0.6 ? 'Real' : d.score < 0.4 ? 'Fake' : 'Mixed'} · {Math.round(d.score * 100)}%</td>
                <td>{Math.round(d.confidence * 100)}%</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {!!n?.next_steps?.length && (
        <div className="glass p-5">
          <p className="font-semibold">What to do next</p>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-slate-300">
            {n.next_steps.map((step) => <li key={step}>{step}</li>)}
          </ol>
        </div>
      )}

      <p className="text-xs text-slate-500">{n?.confidence_note || 'Limitations: PRNU needs reference conditions; recompression destroys traces; scores are evidence, not proof.'}</p>
    </div>
  );
}
