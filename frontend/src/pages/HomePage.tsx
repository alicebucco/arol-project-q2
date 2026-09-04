import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, readableError } from "../api/client";
import { QrScanner } from "../components/QrScanner";
import { AppFooter } from "../components/layout/AppFooter";
import { AppHeader } from "../components/layout/AppHeader";
import { useNotifications } from "../components/layout/Notifications";
import type { MachineSummary } from "../types";

export function HomePage() {
  const [machines, setMachines] = useState<MachineSummary[]>([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [isScannerOpen, setIsScannerOpen] = useState(false); const navigate = useNavigate(); const { notify } = useNotifications();
  useEffect(() => { apiGet<MachineSummary[]>("/machines").then(setMachines).catch((loadError: unknown) => { const message = readableError(loadError, "Unable to load the machine list."); setError(message); notify(message, "error"); }).finally(() => setLoading(false)); }, [notify]);
  return <div className="app-shell"><AppHeader /><main className="page-content"><p className="eyebrow dark-eyebrow">YOUR EQUIPMENT</p><h1>Connected Machines</h1><p className="page-intro">Select a machine to view its technical documentation and telemetry, or scan a QR code to link a new one.</p><button className="qr-scanner-launcher" type="button" onClick={() => setIsScannerOpen(true)}><span aria-hidden="true">⌁</span> Scan QR code</button>{loading && <p className="status-message">Loading machines…</p>}{error && <p className="status-message error-message">{error}</p>}{!loading && !error && machines.length === 0 && <p className="status-message">No machines are available for your company.</p>}{!loading && !error && machines.length > 0 && <section className="machine-grid" aria-label="Machine list">{machines.map((machine) => <button key={machine.machine_id} className="machine-card" type="button" onClick={() => navigate(`/machines/${machine.machine_id}`)}><span className="machine-id">{machine.machine_id}</span><strong>{machine.model_code}</strong><span>{machine.plant_location ?? "Location unavailable"}</span><small>Serial {machine.serial_number}</small><span className="card-arrow" aria-hidden="true">→</span></button>)}</section>}</main>{isScannerOpen && <QrScanner onClose={() => setIsScannerOpen(false)} onDetected={(qrValue) => { setIsScannerOpen(false); navigate(`/machines/${encodeURIComponent(qrValue)}`); }} />}<AppFooter /></div>;
}
