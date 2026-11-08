import Navbar from '../components/Navbar';
import Logo from '../components/Logo';
import { Reveal, Stagger, StaggerItem, Float } from '../components/Reveal';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ShieldCheck, ScanEye, ArrowRight, Cpu, Waves, Grid3X3 } from 'lucide-react';
import { PlayCircle, BadgeCheck, FileText, Fingerprint, Microscope, Sparkles, ChevronDown } from 'lucide-react';

const HERO_EYE = 'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?q=80&w=1200&auto=format&fit=crop';
const HERO_CITY = 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=800&auto=format&fit=crop';
const SHOWCASE = [
  { src: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=800&auto=format&fit=crop', tag: 'Landscape - Likely Real 92%', tint: 'border-green-400/40' },
  { src: 'https://images.unsplash.com/photo-1493514789931-586cb221d7a7?q=80&w=800&auto=format&fit=crop', tag: 'Portrait - Inconclusive 62%', tint: 'border-yellow-400/40' },
  { src: 'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?q=80&w=800&auto=format&fit=crop', tag: 'City AI - Flagged 87%', tint: 'border-red-400/40' },
  { src: 'https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=80&w=800&auto=format&fit=crop', tag: 'Night sky - Frequency scan', tint: 'border-cyan-300/40' },
];

const FEATURES = [
  ['Noise residual maps', 'Wavelet PRNU fingerprint extraction', 'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=600&auto=format&fit=crop'],
  ['Anomaly heatmaps', 'Suspicious-region localization', 'https://images.unsplash.com/photo-1563089145-599997674d42?q=80&w=600&auto=format&fit=crop'],
  ['Frequency spectrum', 'FFT radial + peakiness analysis', 'https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=600&auto=format&fit=crop'],
  ['Wavelet LL/LH/HL/HH', 'Multi-scale sub-band energy', 'https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?q=80&w=600&auto=format&fit=crop'],
  ['ELA viewer', 'Recompression error levels', 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=600&auto=format&fit=crop'],
  ['Metadata + GPS warn', 'EXIF consistency, privacy-safe', 'https://images.unsplash.com/photo-1502920917128-1aa500764cbd?q=80&w=600&auto=format&fit=crop'],
  ['Camera compare', 'Cross-correlation of residuals', 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=600&auto=format&fit=crop'],
  ['PDF + JSON reports', 'Downloadable evidence packs', 'https://images.unsplash.com/photo-1454391304352-2bf4678b1a7a?q=80&w=600&auto=format&fit=crop'],
];

export default function Landing() {
  return (
    <div id="home" className="relative min-h-screen overflow-clip bg-[#05060f]">
      <Navbar publicMode />
      <div className="pointer-events-none absolute inset-0">
        <div className="bg-grid absolute inset-0" />
        <div className="orb orb-violet left-[-120px] top-[-80px] h-[480px] w-[480px]" />
        <div className="orb orb-cyan right-[-140px] top-[20%] h-[520px] w-[520px]" />
        <div className="orb orb-pink bottom-[-160px] left-[30%] h-[420px] w-[420px] opacity-40" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(139,92,246,.18),transparent_62%)]" />
      </div>
      <section className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 pb-10 pt-12 md:grid-cols-[1.05fr_.95fr] md:pt-20">
        <Reveal>
          <p className="inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-200">
            <Sparkles size={13} /> Classical DIP - No black-box CNN
          </p>
          <h1 className="mt-4 text-5xl font-extrabold leading-[1.02] md:text-7xl">
            <span className="text-white">Pixel</span>
            <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-cyan-300 bg-clip-text text-transparent">Forensics</span>
          </h1>
          <p className="shimmer mt-3 text-xl font-semibold md:text-2xl">Uncover the Truth Behind Every Pixel.</p>
          <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-slate-400">
            Detect AI-generated images. Verify authenticity. Trust what you see - PRNU fingerprints, Fourier and wavelet forensics, ELA maps and explainable verdicts.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link to="/login?mode=signup" className="btn-primary flex items-center gap-2 px-6 py-3">
              <ScanEye size={17} /> Get Started <ArrowRight size={16} />
            </Link>
            <a href="#showcase" className="btn-ghost flex items-center gap-2 px-6 py-3">
              <PlayCircle size={17} className="text-cyan-300" /> Watch Demo
            </a>
          </div>
          <Stagger className="mt-8 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {[[BadgeCheck, 'AI Detection', 'Powered by Science'], [ShieldCheck, 'Real vs Fake', 'Explainable Results'], [FileText, 'Forensic Reports', 'Downloadable'], [Fingerprint, 'Trusted', 'Courts + Press']].map(([Icon, a, b]: any) => (
              <StaggerItem key={a as string} className="glass card-hover p-3">
                <Icon size={17} className="text-cyan-300" />
                <p className="mt-1.5 font-semibold text-white">{a as string}</p>
                <p className="text-xs text-slate-400">{b as string}</p>
              </StaggerItem>
            ))}
          </Stagger>
        </Reveal>
        <Reveal delay={0.15} className="relative">
          <Float>
            <div className="relative mx-auto aspect-square w-full max-w-[540px]">
              <div className="ring-spin absolute inset-0 rounded-full border border-dashed border-violet-400/30" />
              <div className="ring-spin-rev absolute inset-6 rounded-full border border-cyan-300/25" />
              <div className="absolute inset-12 overflow-hidden rounded-full border border-white/15 shadow-[0_0_120px_-10px_rgba(139,92,246,.8)]">
                <img src={HERO_EYE} alt="Forensic eye" className="img-crazy h-full w-full scale-110 object-cover" loading="eager" />
                <div className="scanline absolute inset-0" />
                <div className="absolute inset-0 bg-gradient-to-t from-[#05060f]/70 via-transparent to-violet-600/20" />
              </div>
              <motion.div animate={{ y: [0, -10, 0] }} transition={{ repeat: Infinity, duration: 4 }} className="glass-strong absolute -left-2 top-8 w-36 overflow-hidden p-2 md:-left-8">
                <img src={HERO_CITY} alt="scan thumb" className="img-crazy h-20 w-full rounded-lg object-cover" loading="lazy" />
                <p className="mt-1 text-[10px] font-semibold text-cyan-200">FFT SPECTRUM - LIVE</p>
              </motion.div>
              <motion.div animate={{ y: [0, 10, 0] }} transition={{ repeat: Infinity, duration: 5 }} className="glass-strong absolute -right-2 bottom-10 w-40 p-3 md:-right-6">
                <p className="flex items-center gap-1.5 text-xs font-bold text-green-300"><ShieldCheck size={15} /> Likely Real</p>
                <p className="mt-1 text-xl font-extrabold text-white">92% <span className="text-[10px] font-medium text-slate-400">confidence</span></p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <motion.div className="h-full rounded-full bg-gradient-to-r from-green-400 to-cyan-300" initial={{ width: 0 }} whileInView={{ width: '92%' }} viewport={{ once: true }} transition={{ duration: 1.4, delay: 0.4 }} />
                </div>
              </motion.div>
            </div>
          </Float>
        </Reveal>
      </section>
      <div className="relative flex justify-center pb-4">
        <motion.a href="#features" animate={{ y: [0, 8, 0] }} transition={{ repeat: Infinity, duration: 1.8 }} className="text-slate-500 hover:text-cyan-300"><ChevronDown /></motion.a>
      </div>
      <div className="relative overflow-hidden border-y border-white/10 bg-white/[.02] py-3">
        <div className="marquee text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
          {[0, 1].map((k) => (
            <span key={k} className="flex gap-10">
              {['PRNU fingerprints', 'Fourier spectra', 'Wavelet energy', 'ELA maps', 'JPEG ghosts', 'GLCM texture', 'Metadata checks', 'Explainable verdicts'].map((t) => (
                <span key={t} className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-violet-400 to-cyan-300" />{t}</span>
              ))}
            </span>
          ))}
        </div>
      </div>
      <section id="features" className="relative mx-auto max-w-7xl px-4 py-16 md:py-24">
        <Reveal className="text-center">
          <p className="text-xs font-bold uppercase tracking-[0.3em] text-violet-300">Capabilities</p>
          <h2 className="mt-2 text-3xl font-extrabold md:text-5xl">Forensics that <span className="bg-gradient-to-r from-violet-400 to-cyan-300 bg-clip-text text-transparent">shows its work</span></h2>
          <p className="mx-auto mt-3 max-w-2xl text-slate-400">Every score is traceable to classical signal processing you can inspect.</p>
        </Reveal>
        <Stagger className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(([t, d, img]) => (
            <StaggerItem key={t as string} className="glass card-hover group overflow-hidden p-0">
              <div className="relative h-32 overflow-hidden">
                <img src={img as string} alt={t as string} loading="lazy" className="img-crazy h-full w-full object-cover transition duration-700 group-hover:scale-110" />
                <div className="absolute inset-0 bg-gradient-to-t from-[#05060f] via-[#05060f]/20 to-transparent" />
              </div>
              <div className="p-4">
                <p className="flex items-center gap-2 text-sm font-bold text-white"><Microscope size={15} className="text-violet-300" />{t as string}</p>
                <p className="mt-1 text-xs text-slate-400">{d as string}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      <section id="how" className="relative border-y border-white/10 bg-gradient-to-b from-violet-950/40 to-transparent">
        <div className="mx-auto max-w-7xl px-4 py-16 md:py-24">
          <Reveal className="text-center">
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">Pipeline</p>
            <h2 className="mt-2 text-3xl font-extrabold md:text-5xl">How it works</h2>
          </Reveal>
          <Stagger className="mt-10 grid gap-4 md:grid-cols-4">
            {[['01 - Upload', 'Drag and drop JPG/PNG/WEBP. Validated, isolated per user.'], ['02 - Extract noise', 'Wavelet denoising isolates PRNU residual.'], ['03 - Multi-detector scan', 'FFT, wavelets, GLCM, ELA, JPEG and metadata vote.'], ['04 - Explainable verdict', 'Likely Real / AI-Manipulated / Inconclusive.']].map(([t, d]) => (
              <StaggerItem key={t} className="glass-strong card-hover relative overflow-hidden p-6">
                <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-violet-600/20 blur-2xl" />
                <p className="bg-gradient-to-r from-violet-300 to-cyan-300 bg-clip-text font-extrabold text-transparent">{t}</p>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">{d}</p>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      </section>
      <section id="showcase" className="relative mx-auto max-w-7xl px-4 py-16 md:py-24">
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-fuchsia-300">In the wild</p>
            <h2 className="mt-2 text-3xl font-extrabold md:text-5xl">See it catch <span className="bg-gradient-to-r from-fuchsia-400 to-cyan-300 bg-clip-text text-transparent">the unseen</span></h2>
          </div>
          <Link to="/login?mode=signup" className="btn-ghost text-sm">Try your own image</Link>
        </Reveal>
        <Stagger className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SHOWCASE.map((c) => (
            <StaggerItem key={c.src} className={'glass card-hover overflow-hidden border p-0 ' + c.tint}>
              <div className="group relative h-64 overflow-hidden">
                <img src={c.src} alt={c.tag} loading="lazy" className="img-crazy h-full w-full object-cover transition duration-700 group-hover:scale-110" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
                <div className="scanline absolute inset-0 opacity-0 transition group-hover:opacity-100" />
                <p className="absolute bottom-3 left-3 right-3 text-xs font-bold text-white">{c.tag}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </section>
      <section id="tech" className="relative border-t border-white/10">
        <div className="mx-auto max-w-7xl px-4 py-16 md:py-20">
          <Reveal className="text-center">
            <h2 className="text-3xl font-extrabold md:text-4xl">Classical DIP Technology - not just a CNN</h2>
          </Reveal>
          <Stagger className="mt-8 grid gap-4 md:grid-cols-3">
            {[[Cpu, 'PRNU sensor-noise analysis', 'Residual consistency, autocorrelation and block stats.'], [Waves, 'Fourier + Wavelet forensics', 'FFT spectra, radial peakiness, LL/LH/HL/HH energy.'], [Grid3X3, 'Compression and texture', 'ELA maps, JPEG ghost/blocking, GLCM texture.']].map(([Icon, t, d]: any) => (
              <StaggerItem key={t as string} className="glass card-hover p-6">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-violet-600 to-cyan-400 shadow-glow"><Icon size={20} /></span>
                <p className="mt-3 font-bold text-white">{t as string}</p>
                <p className="mt-1 text-sm text-slate-400">{d as string}</p>
              </StaggerItem>
            ))}
          </Stagger>
          <Reveal className="mx-auto mt-10 max-w-3xl text-center">
            <Link to="/login?mode=signup" className="btn-primary inline-flex items-center gap-2 px-8 py-3.5 text-base">Analyze an Image <ArrowRight size={17} /></Link>
            <p className="mt-3 text-xs text-slate-500">Investigative tool - evidence-based, never absolute proof.</p>
          </Reveal>
        </div>
      </section>
      <footer id="about" className="relative overflow-hidden border-t border-white/10">
        <img src="https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=1600&auto=format&fit=crop" alt="" aria-hidden className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-20" loading="lazy" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#05060f] via-[#05060f]/80 to-transparent" />
        <div className="relative mx-auto flex max-w-7xl flex-col items-center gap-4 px-4 py-10 text-center">
          <Logo />
          <p className="text-sm text-slate-400">PixelForensics - Science - Security - Truth. Not Just an Image. A Story. Lets Verify It.</p>
          <p className="text-xs text-slate-600">Classical forensics - PRNU - FFT - Wavelets - ELA - JPEG - Metadata</p>
        </div>
      </footer>
    </div>
  );
}


