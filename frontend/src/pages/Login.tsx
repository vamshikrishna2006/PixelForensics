import { useState } from 'react';
import { Navigate, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../services/auth';
import Navbar from '../components/Navbar';
import Logo from '../components/Logo';

export default function Login() {
  const [sp] = useSearchParams();
  const [mode, setMode] = useState(sp.get('mode') === 'signup' ? 'signup' : 'signin');
  const [username, setUsername] = useState(''); const [email, setEmail] = useState('');
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const { login, register, user, ready, notice, dismissNotice } = useAuth();
  const nav = useNavigate();

  // Only already-authenticated (verified) users skip the login page.
  if (ready && user) return <Navigate to={user.role === 'ADMIN' ? '/admin' : '/dashboard'} replace />;

  const strength = (p: string) => [p.length >= 8, /[A-Z]/.test(p), /[a-z]/.test(p), /\d/.test(p), /[^A-Za-z0-9]/.test(p)].filter(Boolean).length;

  const go = (u: any) => nav(u.role === 'ADMIN' ? '/admin' : '/dashboard', { replace: true });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;                 // never fire two sign-in requests
    setErr(''); dismissNotice();
    setBusy(true);
    try {
      if (mode === 'signin') go(await login(identifier, password));
      else go(await register(username, email, password, confirm));
    } catch (ex: any) {
      setErr(ex?.message || 'Sign-in failed. Please try again.');
    } finally {
      setBusy(false);                 // always restore the button
    }
  };
  return (
    <div className="relative min-h-screen overflow-clip bg-void"><Navbar publicMode />
      <div className="pointer-events-none absolute inset-0">
        <div className="orb orb-violet left-[-120px] top-[-60px] h-[420px] w-[420px]" />
        <div className="orb orb-cyan right-[-120px] top-[30%] h-[420px] w-[420px]" />
      </div>
      <div className="relative mx-auto grid max-w-5xl gap-6 px-4 py-10 md:grid-cols-2">
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="glass p-6">
          <Logo size={36} />
          <h1 className="text-2xl font-bold">{mode === 'signin' ? 'Welcome Back' : 'Create Account'}</h1>
          <p className="text-sm text-slate-400">One common login — role is decided securely by the backend.</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button type="button" disabled={busy} onClick={() => { setMode('signin'); setErr(''); }} className={`rounded-xl px-4 py-2 disabled:opacity-60 ${mode === 'signin' ? 'btn-primary' : 'border border-white/10'}`}>Sign In</button>
            <button type="button" disabled={busy} onClick={() => { setMode('signup'); setErr(''); }} className={`rounded-xl px-4 py-2 disabled:opacity-60 ${mode === 'signup' ? 'btn-primary' : 'border border-white/10'}`}>Sign Up</button>
          </div>
          <form onSubmit={submit} className="mt-4 space-y-3">
            {mode === 'signin' ? (<>
              <input className="input" placeholder="Email or Username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} disabled={busy} required />
              <input className="input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} required />
            </>) : (<>
              <input className="input" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} disabled={busy} required />
              <input className="input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={busy} required />
              <input className="input" type="password" placeholder="Password (8+, upper, lower, number, special)" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} required />
              <div className="h-2 overflow-hidden rounded bg-white/10"><div className="h-full bg-gradient-to-r from-violet-500 to-cyan-300 transition-all" style={{ width: `${(strength(password) / 5) * 100}%` }} /></div>
              <input className="input" type="password" placeholder="Confirm Password" value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={busy} required />
            </>)}
            {err ? (
              <p className="text-sm text-red-400">{err}</p>
            ) : notice ? (
              <p className="text-sm text-amber-300">{notice}</p>
            ) : null}
            <button
              disabled={busy}
              className="btn-primary flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy
                ? (mode === 'signin' ? 'Signing In...' : 'Creating Account...')
                : (mode === 'signin' ? 'Sign In →' : 'Create Account →')}
            </button>
          </form>
          <p className="mt-3 text-xs text-slate-500">Demo admin (seeded locally): admin@pixelforensics.com / Admin@12345</p>
          <Link to="/" className="mt-2 inline-block text-xs text-violet-300">← Back to Home</Link>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} className="glass scanline relative hidden overflow-hidden p-0 md:block">
          <img src="https://images.unsplash.com/photo-1538370965046-79c0d6907d47?q=80&w=900&auto=format&fit=crop" alt="Because the truth deserves a closer look" className="img-crazy h-64 w-full object-cover" loading="lazy" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#05060f] via-[#05060f]/40 to-transparent" />
          <div className="absolute bottom-0 p-8">
            <p className="text-2xl font-bold leading-snug">Because<br />the Truth<br />Deserves<br />a Closer Look</p>
            <p className="mt-3 text-sm text-slate-300">Sensor-noise forensics · explainable verdicts · downloadable reports.</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
