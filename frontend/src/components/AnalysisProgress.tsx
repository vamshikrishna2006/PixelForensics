import { motion } from 'framer-motion';
const STAGES = ['Image validation', 'Metadata extraction', 'AI-content cue scan', 'Noise residual extraction', 'PRNU analysis', 'Frequency-domain analysis', 'Wavelet decomposition', 'Compression analysis', 'ELA analysis', 'Local consistency analysis', 'Forensic score aggregation', 'Report generation'];
export default function AnalysisProgress({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <div className="glass p-5">
      <p className="mb-3 font-semibold">Forensic pipeline running…</p>
      <div className="space-y-2">
        {STAGES.map((s, i) => (
          <motion.div key={s} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.12 }}
            className="flex items-center gap-3 text-sm">
            <motion.span animate={{ scale: [1, 1.4, 1] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.12 }}
              className="h-2.5 w-2.5 rounded-full bg-cyan-300" />
            <span className="text-slate-200">Stage {i + 1}: {s}</span>
            <span className="ml-auto text-cyan-300">●</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
