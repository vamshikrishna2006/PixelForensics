import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './services/auth';
import Landing from './pages/Landing';
import Login from './pages/Login';
import ReportPage from './pages/Report';
import ComparePage from './pages/Compare';
import AdminPage from './pages/Admin';
import DashboardLayout from './layouts/DashboardLayout';
import { DashboardHome, NewAnalysis, History, Profile } from './pages/Dashboard';
import type { JSX } from 'react';

const GUEST_MODE = import.meta.env.VITE_GUEST_ACCESS_MODE === 'true';

function Guard({ children, admin = false }: { children: JSX.Element; admin?: boolean }) {
  const { user, token, ready } = useAuth();
  // Wait for the token to be validated so a stale cached session can't flash the dashboard.
  if (!ready) return <div className="min-h-screen bg-void" />;
  if (GUEST_MODE && !admin) return children;
  if (!token || !user) return <Navigate to="/login" replace />;
  if (admin && user.role !== 'ADMIN') return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={GUEST_MODE ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/register" element={GUEST_MODE ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/dashboard" element={<Guard><DashboardLayout /></Guard>}> 
        <Route index element={<DashboardHome />} />
        <Route path="new" element={<NewAnalysis />} />
        <Route path="history" element={<History />} />
        <Route path="profile" element={<Profile />} />
      </Route>
      <Route path="/analysis/:id" element={<Guard><ReportPage /></Guard>} />
      <Route path="/report/:id" element={<Guard><ReportPage /></Guard>} />
      <Route path="/compare" element={<Guard><ComparePage /></Guard>} />
      <Route path="/admin" element={<Guard admin><AdminPage /></Guard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
