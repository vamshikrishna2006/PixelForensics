import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, PlusCircle, History, GitCompareArrows, User, LogOut, ShieldCheck } from 'lucide-react';
import { useAuth } from '../services/auth';
import Logo from '../components/Logo';

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const link = ({ isActive }: any) => `flex items-center gap-2 rounded-xl px-4 py-2 text-sm ${isActive ? 'bg-violet-600/30 border border-violet-400/40' : 'hover:bg-white/5 border border-transparent'}`;
  return (
    <div className="flex min-h-screen bg-void">
      <aside className="hidden w-60 shrink-0 flex-col gap-1 border-r border-white/10 bg-black/20 p-4 md:flex">
        <div className="px-2 py-2"><Logo size={36} /></div>
        {user?.role === 'ADMIN' && (
          <NavLink to="/admin" className="mb-1 flex items-center gap-2 rounded-xl border border-violet-400/50 bg-violet-600/20 px-4 py-2 text-sm font-semibold text-violet-100 transition hover:bg-violet-600/30">
            <ShieldCheck size={16} /> Back to Admin Dashboard
          </NavLink>
        )}
        <NavLink to="/dashboard" end className={link}><LayoutDashboard size={16} /> Dashboard</NavLink>
        <NavLink to="/dashboard/new" className={link}><PlusCircle size={16} /> New Analysis</NavLink>
        <NavLink to="/dashboard/history" className={link}><History size={16} /> History</NavLink>
        <NavLink to="/compare" className={link}><GitCompareArrows size={16} /> Compare Images</NavLink>
        <NavLink to="/dashboard/profile" className={link}><User size={16} /> Profile</NavLink>
        <button onClick={() => { logout(); nav('/'); }} className="mt-auto flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2 text-sm"><LogOut size={16} /> Logout</button>
        <p className="px-2 text-xs text-slate-500">{user?.username}</p>
      </aside>
      <div className="flex-1">
        <div className="flex items-center gap-2 border-b border-white/10 p-3 md:hidden">
          <NavLink to="/dashboard" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs">Home</NavLink>
          <NavLink to="/dashboard/new" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs">New</NavLink>
          <NavLink to="/dashboard/history" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs">History</NavLink>
          <NavLink to="/compare" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs">Compare</NavLink>
          {user?.role === 'ADMIN' && (
            <NavLink to="/admin" title="Back to Admin Dashboard" className="ml-auto flex items-center gap-1 rounded-lg border border-violet-400/50 bg-violet-600/20 px-3 py-1.5 text-xs font-semibold text-violet-100">
              <ShieldCheck size={14} /> Admin
            </NavLink>
          )}
        </div>
        <main className="mx-auto max-w-6xl p-4"><Outlet /></main>
      </div>
    </div>
  );
}
