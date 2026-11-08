import { motion } from 'framer-motion';
export default function ConfidenceMeter({ value, verdict }: { value: number; verdict: string }) {
  const pct = Math.round(value * 100);
  const color = verdict === 'LIKELY_REAL' ? '#22c55e' : verdict === 'LIKELY_AI_MANIPULATED' ? '#ef4444' : '#eab308';
  const R = 54, C = 2 * Math.PI * R;
  return (
    <div className="flex items-center gap-4">
      <div className="relative h-32 w-32">
        <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
          <circle cx="64" cy="64" r={R} fill="none" strokeWidth="10" className="stroke-white/10" />
          <motion.circle cx="64" cy="64" r={R} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
            strokeDasharray={C} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: C - (C * pct) / 100 }} transition={{ duration: 1.2 }} />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div><div className="text-2xl font-bold">{pct}%</div><div className="text-xs text-slate-400">Confidence</div></div>
        </div>
      </div>
      <p className="max-w-[220px] text-xs text-slate-400">Confidence reflects forensic evidence strength — never absolute proof.</p>
    </div>
  );
}
