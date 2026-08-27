import { FormEvent, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

const USER_ID_STORAGE_KEY = "arol.user-id";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type MachineSummary = {
  machine_id: string;
  serial_number: string;
  model_code: string;
  model_description: string | null;
  plant_location: string | null;
  configuration_profile: string | null;
};

type MachineContext = MachineSummary & {
  company_id: string;
  company_name: string;
  model_id: string;
  operational_context: string;
};

function activeUserId() {
  return localStorage.getItem(USER_ID_STORAGE_KEY);
}

async function apiGet<T>(path: string, userIdOverride?: string): Promise<T> {
  const userId = userIdOverride ?? activeUserId();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: userId ? { "X-User-Id": userId } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? "Impossibile caricare i dati richiesti.");
  }
  return response.json() as Promise<T>;
}

function AppHeader() {
  const navigate = useNavigate();
  const userId = activeUserId();

  function logout() {
    localStorage.removeItem(USER_ID_STORAGE_KEY);
    navigate("/login");
  }

  return (
    <header className="app-header">
      <button className="wordmark" type="button" onClick={() => navigate("/home")} aria-label="Vai alla home">AROL</button>
      <div className="header-actions">
        <span>{userId}</span>
        <button className="text-button" type="button" onClick={logout}>Sign Out</button>
      </div>
    </header>
  );
}

function AppFooter() {
  return (
    <footer className="app-footer">
      <div className="footer-main">
        <div className="footer-identity">
          <a className="footer-wordmark" href="https://www.arol.com" target="_blank" rel="noreferrer">AROL</a>
          <p>AROL S.P.A. – Viale Italia, 193 · 14053 Canelli (Asti), Italia</p>
          <p>C.F. e P.IVA 03217610967 · REA AT 108104</p>
        </div>
        <nav className="footer-nav" aria-label="Collegamenti AROL">
          <a href="https://www.arol.com/arol-canelli" target="_blank" rel="noreferrer">Company</a>
          <a href="https://www.arol.com/?Itemid=689" target="_blank" rel="noreferrer">Customer Care</a>
          <a href="https://www.arol.com/arol-work-with-us" target="_blank" rel="noreferrer">Work with us</a>
          <a href="https://www.arol.com/arol-contact" target="_blank" rel="noreferrer">Contacts</a>
        </nav>
      </div>
      <div className="footer-legal">
        <span>© {new Date().getFullYear()} AROL S.P.A.</span>
        <div>
          <a href="https://www.arol.com/terms-condition" target="_blank" rel="noreferrer">Terms &amp; Conditions</a>
          <a href="https://www.arol.com/legal-notes" target="_blank" rel="noreferrer">Legal Notice</a>
          <a href="https://www.arol.com/arol-contact" target="_blank" rel="noreferrer">Privacy Policy</a>
        </div>
      </div>
    </footer>
  );
}

type LoginPageProps = {
  qrValue?: string;
};

function LoginPage({ qrValue: routeQrValue }: LoginPageProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [userId, setUserId] = useState(() => localStorage.getItem(USER_ID_STORAGE_KEY) ?? "");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryQrValue = new URLSearchParams(location.search).get("qr")?.trim();
  const qrValue = routeQrValue ?? queryQrValue;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedUserId = userId.trim().toUpperCase();
    if (!normalizedUserId) {
      setError("Inserisci il tuo identificativo utente.");
      return;
    }

    setIsSubmitting(true);
    try {
      await apiGet("/auth/me", normalizedUserId);
      localStorage.setItem(USER_ID_STORAGE_KEY, normalizedUserId);
      navigate(qrValue ? `/machines/${encodeURIComponent(qrValue)}` : "/home");
    } catch {
      setError("Identificativo non riconosciuto. Verifica il codice e riprova.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="brand-panel" aria-label="AROL Customer Platform">
        <div className="brand-mark" aria-hidden="true">A</div>
        <p className="eyebrow">AROL CUSTOMER PLATFORM</p>
        <h1>The intelligent digital ecosystem for your machine fleet.</h1>
        <p className="brand-copy">
        Access IoT telemetry, maintenance schedules, technical manuals, and AI-powered support for your equipment.
        </p>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit} noValidate>
          <p className="eyebrow">AUTHENTICATION</p>
          <h2>Welcome</h2>
          <p className="login-intro">Enter your identifier to access the platform.</p>

          {qrValue && (
            <p className="qr-context" role="status">
              Macchina rilevata: <strong>{qrValue}</strong>
            </p>
          )}

          <label htmlFor="user-id">User ID</label>
          <input
            id="user-id"
            name="user-id"
            autoComplete="username"
            placeholder="Es. USR-001"
            value={userId}
            onChange={(event) => {
              setUserId(event.target.value);
              setError("");
            }}
            aria-describedby={error ? "user-id-error" : "user-id-help"}
          />
          {error ? (
            <p id="user-id-error" className="field-error" role="alert">{error}</p>
          ) : (
            <p id="user-id-help" className="field-help">Development environment: e.g. <code>USR-001</code>.</p>
          )}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Verifica in corso…" : "Log in"} <span aria-hidden="true">→</span>
          </button>
        </form>
      </section>
    </main>
  );
}

function HomePage() {
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    apiGet<MachineSummary[]>("/machines")
      .then(setMachines)
      .catch((loadError: Error) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page-content">
        <p className="eyebrow dark-eyebrow">YOUR EQUIPMENT</p>
        <h1>Connected Machines</h1>
        <p className="page-intro">Select a machine to view its technical documentation and telemetry, or scan a QR code to link a new one.</p>
        {loading && <p className="status-message">Caricamento macchine…</p>}
        {error && <p className="status-message error-message">{error}</p>}
        {!loading && !error && (
          <section className="machine-grid" aria-label="Elenco macchine">
            {machines.map((machine) => (
              <button key={machine.machine_id} className="machine-card" type="button" onClick={() => navigate(`/machines/${machine.machine_id}`)}>
                <span className="machine-id">{machine.machine_id}</span>
                <strong>{machine.model_code}</strong>
                <span>{machine.plant_location ?? "Posizione non disponibile"}</span>
                <small>Seriale {machine.serial_number}</small>
                <span className="card-arrow" aria-hidden="true">→</span>
              </button>
            ))}
          </section>
        )}
      </main>
      <AppFooter />
    </div>
  );
}

function MachinePage() {
  const { qrValue } = useParams();
  const navigate = useNavigate();
  const [machine, setMachine] = useState<MachineContext | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!qrValue) return;
    apiGet<MachineContext>(`/machines/lookup/${encodeURIComponent(qrValue)}`)
      .then(setMachine)
      .catch((loadError: Error) => setError(loadError.message));
  }, [qrValue]);

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page-content machine-page">
        <button className="back-link" type="button" onClick={() => navigate("/home")}>← All Machines</button>
        {error && <p className="status-message error-message">{error}</p>}
        {!machine && !error && <p className="status-message">Loading machine context...</p>}
        {machine && (
          <>
            <p className="eyebrow dark-eyebrow">CONNECTED MACHINE</p>
            <div className="machine-heading">
              <div>
                <h1>{machine.machine_id}</h1>
                <p>{machine.model_code} · Serial No. {machine.serial_number}</p>
              </div>
              <span className="qr-badge">QR Verified</span>
            </div>
            <section className="machine-overview">
              <article>
                <span>Customer</span>
                <strong>{machine.company_name}</strong>
              </article>
              <article>
                <span>Location</span>
                <strong>{machine.plant_location ?? "Not available"}</strong>
              </article>
              <article>
                <span>Model</span>
                <strong>{machine.model_description ?? machine.model_code}</strong>
              </article>
            </section>
            <section className="configuration-card">
              <p className="eyebrow dark-eyebrow">CONFIGURATION</p>
              <p>{machine.operational_context}</p>
            </section>
            <section className="next-actions" aria-label="Funzioni macchina">
              <article><strong>AROL Assistant</strong><span>AI Chat, technical manuals, and guided troubleshooting will be available here.</span></article>
              <article><strong>Operational Data</strong><span>Alarms, IoT telemetry, and maintenance schedules will be added in the next section.</span></article>
            </section>
          </>
        )}
      </main>
      <AppFooter />
    </div>
  );
}

function RequireSession({ children }: { children: ReactNode }) {
  return activeUserId() ? children : <Navigate to="/login" replace />;
}

function MachineRoute() {
  const { qrValue } = useParams();
  return activeUserId() ? <MachinePage /> : <LoginPage qrValue={qrValue} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/machines/:qrValue" element={<MachineRoute />} />
      <Route path="/home" element={<RequireSession><HomePage /></RequireSession>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
