/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        void: '#05060f', panel: '#0b0e1d', neon: '#8b5cf6', cyan2: '#22d3ee',
        real: '#22c55e', fake: '#ef4444', warn: '#eab308',
      },
      boxShadow: { glow: '0 0 24px rgba(139,92,246,.35)' },
    },
  },
  plugins: [],
};
