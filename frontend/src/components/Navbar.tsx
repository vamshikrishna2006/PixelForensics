import { Link, useNavigate } from 'react-router-dom';
import { Moon, Sun } from 'lucide-react';
import { useAuth } from '../services/auth';
import { useTheme } from '../services/theme';
import Logo from './Logo';

export default function Navbar({ publicMode = false }: { publicMode?: boolean }) {
  const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
  const { user, ready, logout } = useAuth();
  const { dark, toggle } = useTheme();
  const nav = useNavigate();
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-[#05060f]/80 backdrop-blur-2xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
        <Link to="/" className="transition hover:scale-[1.02]">
          <Logo />
        </Link>
        {publicMode ? (
          <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
            <a href="#home" className="transition hover:text-white">Home</a>
            <a href="#features" className="transition hover:text-white">Features</a>
            <a href="#how" className="transition hover:text-white">How It Works</a>
            <a href="#showcase" className="transition hover:text-white">Showcase</a>
            <a href="#about" className="transition hover:text-white">About</a>
          </nav>
        ) : null}
        <div className="flex items-center gap-2">
          <button onClick={toggle} aria-label="Toggle theme" className="rounded-xl border border-white/10 bg-white/5 p-2.5 transition hover:border-cyan-300/50">{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
          {!ready ? null : user ? (
            <>
              <span className="hidden text-sm text-slate-300 sm:block">{user.username} · {user.role}</span>
              <button onClick={() => { logout(); nav('/'); }} className="rounded-xl border border-white/10 px-4 py-2 text-sm transition hover:border-white/30">Logout</button>
            </>
          ) : DEMO_MODE ? null : (
            <>
              <Link to="/login" className="rounded-xl border border-white/15 px-4 py-2 text-sm font-semibold transition hover:border-white/40 hover:bg-white/5">Sign In</Link>
              <Link to="/login?mode=signup" className="btn-primary text-sm">Sign Up</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

