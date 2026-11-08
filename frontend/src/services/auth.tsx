import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import type { User } from '../types';
import { supabase } from './supabase';

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const GUEST_MODE = import.meta.env.VITE_GUEST_ACCESS_MODE === 'true';
const VERIFY_TIMEOUT_MS = 4000;   // never hang the app if the API is down
const REVALIDATE_THROTTLE_MS = 15000;

interface Ctx {
  user: User | null; token: string | null; ready: boolean;
  login: (identifier: string, password: string) => Promise<User>;
  register: (u: string, e: string, p: string, c: string) => Promise<User>;
  logout: () => void; authFetch: (path: string, init?: RequestInit) => Promise<Response>;
  notice: string | null; dismissNotice: () => void;
}
const AuthCtx = createContext<Ctx>(null as any);
export const useAuth = () => useContext(AuthCtx);

/** Result of asking the backend to identify a token. */
type MeResult =
  | { kind: 'user'; user: User }
  | { kind: 'unauthorized' }
  | { kind: 'unreachable' }
  | { kind: 'error'; status: number };

/** Thrown when the provider (Supabase) authenticated but /api/auth/me did not succeed. */
class AuthSyncError extends Error {
  constructor(public reason: 'unauthorized' | 'unreachable' | 'server') {
    super(reason);
    this.name = 'AuthSyncError';
  }
}

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

/** True only when the JWT carries an `exp` that is already in the past. */
function tokenExpired(t: string | null): boolean {
  if (!t) return true;
  const part = t.split('.')[1];
  if (!part) return false; // not a JWT (opaque token) — let the server decide
  try {
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '=');
    const payload = JSON.parse(atob(b64));
    return typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

/**
 * Ask the backend who this token belongs to. Unlike the old helper, this
 * distinguishes "token rejected" (401) from "backend unreachable" so callers
 * never mistake a network blip for an expired session.
 */
async function fetchMeResult(t: string): Promise<MeResult> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), VERIFY_TIMEOUT_MS);
  try {
    const r = await fetch(`${API}/api/auth/me`, {
      headers: { Authorization: `Bearer ${t}` },
      signal: ctrl.signal,
    });
    if (r.ok) {
      try {
        return { kind: 'user', user: (await r.json()) as User };
      } catch {
        return { kind: 'error', status: r.status };
      }
    }
    if (r.status === 401 || r.status === 403) return { kind: 'unauthorized' };
    return { kind: 'error', status: r.status };
  } catch {
    return { kind: 'unreachable' };
  } finally {
    window.clearTimeout(timer);
  }
}

function isTransient(res: MeResult): boolean {
  return res.kind === 'unreachable' || (res.kind === 'error' && res.status >= 500);
}

/** Supabase rejected the credentials themselves (safe to try a legacy local login). */
function isInvalidCredentials(err: any): boolean {
  const m = String(err?.message || '').toLowerCase();
  return m.includes('invalid login credentials') || m.includes('invalid credentials') || m.includes('invalid_grant');
}

/** Map Supabase auth errors to a friendly, non-leaky message. */
function supabaseAuthMessage(err: any): string {
  const m = String(err?.message || '').toLowerCase();
  if (m.includes('email not confirmed')) return 'Please confirm your email address, then sign in.';
  if (m.includes('rate limit') || m.includes('too many')) return 'Too many attempts. Please wait a moment and try again.';
  if (m.includes('fetch') || m.includes('network') || m.includes('timeout') || m.includes('failed to')) {
    return 'Unable to connect to the server. Please try again.';
  }
  return 'Incorrect email or password.';
}

/** Race a promise against a timeout so a paused/unreachable Supabase project can't block login state. */
function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([p, new Promise<T>((resolve) => window.setTimeout(() => resolve(fallback), ms))]);
}

const OFFLINE_MSG =
  `Backend API is not reachable at ${API}. Start it first: cd backend, then ` +
  `.venv\\Scripts\\activate && uvicorn app.main:app --reload`;

/** Any HTTP response means the API is up; only a network/CORS failure counts as down. */
async function apiReachable(): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 2500);
  try {
    await fetch(`${API}/api/health`, { signal: ctrl.signal });
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

async function readDetail(r: Response, fallback: string): Promise<string> {
  try {
    const j = await r.json();
    return j?.detail || fallback;
  } catch {
    return fallback;
  }
}

/** Turn a failed request into a message that tells the user what to do. */
export function describeError(e: unknown, fallback = 'Something went wrong.'): string {
  if (e instanceof TypeError) {
    return `Could not reach the backend API at ${API}. Make sure it is running: cd backend, ` +
      `.venv\\Scripts\\activate, then uvicorn app.main:app --reload`;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Never trust localStorage for identity: `user` is only populated after the
  // backend confirms the token. `ready` flips once that first check finishes.
  const [user, setUser] = useState<User | null>(() => {
    if (GUEST_MODE) {
      let guestId = localStorage.getItem('pf_guest_id');
      if (!guestId) {
        guestId = crypto.randomUUID();
        localStorage.setItem('pf_guest_id', guestId);
      }
      return { id: guestId, username: `guest_${guestId.slice(0,6)}`, email: `guest_${guestId.slice(0,6)}@guest.local`, role: 'CUSTOMER' } as User;
    }
    return null;
  });
  const [token, setToken] = useState<string | null>(() => GUEST_MODE ? 'guest' : localStorage.getItem('pf_token'));
  const [ready, setReady] = useState(() => GUEST_MODE);
  const [notice, setNotice] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(token);
  const lastCheck = useRef(0);
  // True while login()/register() own the auth flow, so restore() (which also
  // runs on tab visibility) never fights an in-progress sign-in.
  const loginBusyRef = useRef(false);
  useEffect(() => { tokenRef.current = token; }, [token]);

  const clearSession = useCallback((msg?: string) => {
    setUser(null); setToken(null); tokenRef.current = null;
    localStorage.removeItem('pf_token');
    localStorage.removeItem('pf_user');
    // Clears Supabase's own stored session too. `scope: 'local'` removes it
    // without a network call, so logout still works while Supabase is paused.
    if (supabase) supabase.auth.signOut({ scope: 'local' }).catch(() => {});
    if (msg) setNotice(msg);
  }, []);

  const save = (t: string, u: User) => {
    setToken(t); tokenRef.current = t; setUser(u);
    localStorage.setItem('pf_token', t);
    localStorage.setItem('pf_user', JSON.stringify(u));
  };

  /**
   * Verify the token with the backend and return the authoritative profile.
   * Retries transient failures and can refresh the Supabase token once it has
   * been rejected (e.g. a token signed by a just-rotated key).
   */
  const syncProfile = useCallback(
    async (accessToken: string, allowRefresh: boolean): Promise<{ user: User; token: string }> => {
      let tok = accessToken;
      let res = await fetchMeResult(tok);

      if (allowRefresh && supabase && res.kind === 'unauthorized') {
        for (let i = 0; i < 2 && res.kind === 'unauthorized'; i++) {
          try {
            const rf = await supabase.auth.refreshSession();
            const fresh = rf.data.session?.access_token;
            if (!fresh) break;
            tok = fresh;
          } catch { break; }
          await sleep(300 * (i + 1));
          res = await fetchMeResult(tok);
        }
      }

      for (let i = 0; i < 2 && isTransient(res); i++) {
        await sleep(400 * (i + 1));
        res = await fetchMeResult(tok);
      }

      if (res.kind === 'user') return { user: res.user, token: tok };
      if (res.kind === 'unreachable') throw new AuthSyncError('unreachable');
      if (res.kind === 'unauthorized') throw new AuthSyncError('unauthorized');
      throw new AuthSyncError('server');
    },
    [],
  );

  /** Validate whatever credentials we have. Network failures keep the session. */
  const restore = useCallback(async (): Promise<boolean> => {
    if (loginBusyRef.current) return true;

    // 1) Supabase session (preferred when configured)
    if (supabase) {
      try {
        const sb = await withTimeout(supabase.auth.getSession(), VERIFY_TIMEOUT_MS, null as any);
        let sbToken = sb?.data?.session?.access_token;
        if (sbToken) {
          if (tokenExpired(sbToken)) {
            try {
              const rf = await withTimeout(supabase.auth.refreshSession(), VERIFY_TIMEOUT_MS, null as any);
              sbToken = rf?.data?.session?.access_token || sbToken;
            } catch { /* keep going, the backend will decide */ }
          }
          let res = await fetchMeResult(sbToken);
          if (res.kind === 'unauthorized') {
            try {
              const rf = await withTimeout(supabase.auth.refreshSession(), VERIFY_TIMEOUT_MS, null as any);
              const fresh = rf?.data?.session?.access_token;
              if (fresh) { sbToken = fresh; res = await fetchMeResult(sbToken); }
            } catch { /* ignore */ }
          }
          if (res.kind === 'user') {
            setUser(res.user); setToken(sbToken); tokenRef.current = sbToken;
            localStorage.setItem('pf_user', JSON.stringify(res.user));
            return true;
          }
          if (isTransient(res)) {
            // Backend temporarily unavailable: keep the existing session rather
            // than logging the user out on a tab switch.
            return !!tokenRef.current;
          }
        }
      } catch { /* fall through to local token */ }
    }

    // 2) Local JWT
    const cached = localStorage.getItem('pf_token');
    if (cached && !tokenExpired(cached)) {
      const res = await fetchMeResult(cached);
      if (res.kind === 'user') {
        setUser(res.user); setToken(cached); tokenRef.current = cached;
        localStorage.setItem('pf_user', JSON.stringify(res.user));
        return true;
      }
      if (isTransient(res)) return !!tokenRef.current;
    }

    const hadCredential = !!(localStorage.getItem('pf_token') || localStorage.getItem('pf_user'));
    clearSession(hadCredential ? 'Your session has expired. Please sign in again.' : undefined);
    return false;
  }, [clearSession]);

  // Verify on load — this is what removes the phantom "Logout" header after
  // the backend is stopped or the token goes stale.
  useEffect(() => {
    let alive = true;
    restore().finally(() => { if (alive) setReady(true); });
    return () => { alive = false; };
  }, [restore]);

  // Re-check when the user comes back to the tab (throttled, never during login).
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (loginBusyRef.current) return;
      if (Date.now() - lastCheck.current < REVALIDATE_THROTTLE_MS) return;
      lastCheck.current = Date.now();
      void restore();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [restore]);

  // Keep tabs in sync when one of them logs in/out.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'pf_token') {
        if (!e.newValue) { setUser(null); setToken(null); tokenRef.current = null; }
        else void restore();
      }
      if (e.key === 'pf_user' && !e.newValue) setUser(null);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [restore]);

  const authFetch = async (path: string, init: RequestInit = {}) => {
    // Prefer Supabase session token when Supabase is configured (Option B),
    // fall back to local JWT otherwise. Same backend accepts both in dual-mode.
    let tok = tokenRef.current ?? localStorage.getItem('pf_token');
    if (supabase) {
      try {
        const sb = await withTimeout(supabase.auth.getSession(), VERIFY_TIMEOUT_MS, null as any);
        if (sb?.data?.session?.access_token) tok = sb.data.session.access_token;
      } catch { /* keep local token */ }
    }
    const headers: Record<string, string> = { ...(init.headers || {}) as Record<string, string> };
    if (tok) headers.Authorization = `Bearer ${tok}`;
    if (GUEST_MODE) {
      const guestId = localStorage.getItem('pf_guest_id');
      if (guestId) headers['X-Guest-Id'] = guestId;
    }
    const res = await fetch(`${API}${path}`, {
      ...init,
      headers,
    });
    // A rejected token means the session is gone (expired, server restarted,
    // account disabled). Log out instead of leaving a stale header behind.
    if (res.status === 401 && !GUEST_MODE) clearSession('Your session has expired. Please sign in again.');
    return res;
  };

  const login = async (identifier: string, password: string) => {
    if (loginBusyRef.current) throw new Error('Sign-in is already in progress.');
    loginBusyRef.current = true;
    try {
      if (!(await apiReachable())) {
        throw new Error('Unable to connect to the server. Please try again.');
      }

      // ------------------------------------------------------------------
      // Option B: Supabase is the primary provider for email accounts.
      // ------------------------------------------------------------------
      if (supabase && identifier.includes('@')) {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: identifier.trim(), password,
        });

        if (!error) {
          // Provider authentication succeeded. From this point we must NOT fall
          // back to local login: a profile-sync problem is not a login failure.
          let accessToken: string | undefined = data.session?.access_token;
          if (!accessToken) {
            try {
              const { data: s } = await supabase.auth.getSession();
              accessToken = s.session?.access_token;
            } catch { /* ignore */ }
          }
          if (!accessToken) {
            throw new Error('Your account was authenticated, but no valid session was returned. Please try again.');
          }

          try {
            const { user: u, token: verified } = await syncProfile(accessToken, true);
            save(verified, u);
            setNotice(null);
            return u;
          } catch (e) {
            if (e instanceof AuthSyncError && e.reason === 'unreachable') {
              throw new Error('Unable to connect to the server. Please try again.');
            }
            throw new Error('Your account was authenticated, but profile synchronization could not be completed. Please try again.');
          }
        }

        // Supabase sign-in failed. Only fall through to the legacy local login
        // for a genuine credential rejection; surface other errors directly.
        if (!isInvalidCredentials(error)) {
          throw new Error(supabaseAuthMessage(error));
        }
      }

      // ------------------------------------------------------------------
      // Local JWT (legacy accounts, or Supabase not configured/identifier).
      // ------------------------------------------------------------------
      let r: Response;
      try {
        r = await fetch(`${API}/api/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ identifier, password }),
        });
      } catch {
        throw new Error('Unable to connect to the server. Please try again.');
      }
      if (r.status === 401) throw new Error('Incorrect email or password.');
      if (!r.ok) throw new Error('Unable to sign in right now. Please try again.');
      const d = await r.json();
      save(d.access_token, d.user as User);
      setNotice(null);
      return d.user as User;
    } finally {
      loginBusyRef.current = false;
    }
  };

  const register = async (username: string, email: string, password: string, confirm_password: string) => {
    if (!(await apiReachable())) throw new Error(OFFLINE_MSG);

    // Option B: Supabase signup first; backend profile via /me + /sync (trigger disabled).
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(), password,
        options: { data: { username: username.trim() } },
      });
      if (error) throw new Error(supabaseAuthMessage(error));
      const sbToken = data.session?.access_token;
      if (sbToken) {
        try {
          const { user: me, token: verified } = await syncProfile(sbToken, false);
          // Best-effort audit entry; never blocks account creation.
          try {
            await fetch(`${API}/api/auth/sync`, { method: 'POST', headers: { Authorization: `Bearer ${verified}` } });
          } catch { /* ignore */ }
          save(verified, me);
          setNotice(null);
          return me;
        } catch {
          throw new Error('Your account was created, but profile synchronization could not be completed. Please sign in.');
        }
      }
      // email-confirm required (no session): user must confirm then Sign In
      if (data.user && !data.session) {
        throw new Error('Account created. Check your email to confirm, then Sign In.');
      }
      throw new Error('Account created. Please Sign In.');
    }
    let r: Response;
    try {
      r = await fetch(`${API}/api/auth/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password, confirm_password }),
      });
    } catch {
      throw new Error(`Backend API is not reachable at ${API}.`);
    }
    if (!r.ok) throw new Error(await readDetail(r, 'Registration failed'));
    const d = await r.json();
    save(d.access_token, d.user as User);
    setNotice(null);
    return d.user as User;
  };

  const logout = () => clearSession();
  const dismissNotice = useCallback(() => setNotice(null), []);

  return <AuthCtx.Provider value={{ user, token, ready, login, register, logout, authFetch, notice, dismissNotice }}>{children}</AuthCtx.Provider>;
}
export { API };