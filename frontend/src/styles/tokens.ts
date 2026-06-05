// Design tokens — single source of truth.
// Mirrored as CSS vars in ./tokens.css for use inside .module.css files.
// Source: frontend-design/remix/project/design/tokens-a.jsx (TA · "Sunset Notebook")

export const tokens = {
  color: {
    bg: '#fbf5ec',
    bgAlt: '#f5ecdc',
    surface: '#ffffff',
    ink: '#2b211a',
    inkDim: '#7a6a5e',
    inkSubtle: '#a89888',
    line: '#ecdfce',
    lineSoft: '#f3e8d4',
    primary: '#c96442',
    primarySoft: '#fbeee2',
    primaryHover: '#b35636',
    sun: '#f0a86b',
    ok: '#7ba66a',
    warn: '#d49640',
    danger: '#c14a3a',
  },
  shadow: {
    base: '0 1px 0 rgba(180,140,100,0.08), 0 8px 24px rgba(100,60,30,0.07)',
    lg: '0 1px 0 rgba(180,140,100,0.08), 0 20px 40px rgba(100,60,30,0.11)',
  },
  radius: {
    sm: 10,
    md: 14,
    lg: 20,
  },
  font: {
    body: "'Pretendard', system-ui, -apple-system, sans-serif",
    mono: "'JetBrains Mono', 'Pretendard', ui-monospace, monospace",
  },
} as const;

export type Tokens = typeof tokens;
