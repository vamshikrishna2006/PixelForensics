import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
const ThemeCtx = createContext<{ dark: boolean; toggle: () => void }>(null as any);
export const useTheme = () => useContext(ThemeCtx);
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(() => (localStorage.getItem('pf_theme') || 'dark') === 'dark');
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    document.documentElement.classList.toggle('light', !dark);
    localStorage.setItem('pf_theme', dark ? 'dark' : 'light');
  }, [dark]);
  return <ThemeCtx.Provider value={{ dark, toggle: () => setDark(!dark) }}>{children}</ThemeCtx.Provider>;
}
