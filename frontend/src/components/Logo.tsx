import { motion } from 'framer-motion';

export default function Logo({ size = 40, compact = false }: { size?: number; compact?: boolean }) {
  return (
    <span className="group flex items-center gap-2.5">
      <span className="logo-wrap relative grid place-items-center" style={{ width: size, height: size }}>
        <motion.span
          className="absolute inset-0 rounded-2xl"
          style={{
            background: 'conic-gradient(from 0deg, #8b5cf6, #22d3ee, #f472b6, #8b5cf6)',
            filter: 'blur(1px)',
          }}
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 8, ease: 'linear' }}
        />
        <span className="absolute inset-[2px] rounded-[14px] bg-[#070b1d]" />
        <motion.span
          className="absolute inset-[2px] rounded-[14px] opacity-60"
          style={{ background: 'radial-gradient(circle at 30% 25%, rgba(139,92,246,.7), transparent 55%), radial-gradient(circle at 75% 75%, rgba(34,211,238,.55), transparent 55%)' }}
          animate={{ opacity: [0.45, 0.85, 0.45], scale: [1, 1.06, 1] }}
          transition={{ repeat: Infinity, duration: 3.2, ease: 'easeInOut' }}
        />
        {/* eye */}
        <motion.svg viewBox="0 0 32 32" width={size * 0.66} height={size * 0.66} className="relative z-10"
          animate={{ scale: [1, 1.05, 1] }} transition={{ repeat: Infinity, duration: 2.8 }}>
          <defs>
            <radialGradient id="pfIris" cx="50%" cy="45%" r="55%">
              <stop offset="0%" stopColor="#fff" />
              <stop offset="22%" stopColor="#22d3ee" />
              <stop offset="55%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#0b0e2a" />
            </radialGradient>
          </defs>
          <path d="M3 16C6.5 9.5 11.5 6.5 16 6.5S25.5 9.5 29 16C25.5 22.5 20.5 25.5 16 25.5S6.5 22.5 3 16Z" fill="none" stroke="white" strokeOpacity=".9" strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="16" cy="16" r="6.2" fill="url(#pfIris)" stroke="white" strokeOpacity=".8" strokeWidth="1" />
          <circle cx="16" cy="16" r="2.7" fill="#020617" />
          <circle cx="14.2" cy="13.8" r="1.2" fill="white" opacity=".95" />
          <motion.circle cx="16" cy="16" r="8.2" fill="none" stroke="#22d3ee" strokeOpacity=".7" strokeWidth="1"
            strokeDasharray="6 6" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 6, ease: 'linear' }} style={{ transformOrigin: '16px 16px' }} />
        </motion.svg>
        <span className="scan-eye" />
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block text-[17px] font-extrabold tracking-tight text-white">
            Pixel<span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-cyan-300 bg-clip-text text-transparent">Forensics</span>
          </span>
          <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-300/80">Science • Security • Truth</span>
        </span>
      )}
    </span>
  );
}
