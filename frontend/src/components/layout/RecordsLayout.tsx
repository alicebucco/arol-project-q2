import type { ReactNode } from "react";
import { AppFooter } from "./AppFooter";
import { AppHeader } from "./AppHeader";

export function RecordsLayout({ eyebrow, title, intro, loading, error, empty, children }: { eyebrow: string; title: string; intro: string; loading: boolean; error: string; empty?: string; children: ReactNode }) {
  return <div className="app-shell"><AppHeader /><main className="page-content records-page">
    <p className="eyebrow dark-eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-intro">{intro}</p>
    {loading && <p className="status-message">Loading data…</p>}{error && <p className="status-message error-message">{error}</p>}
    {!loading && !error && empty && <p className="status-message">{empty}</p>}{!loading && !error && !empty && children}
  </main><AppFooter /></div>;
}
