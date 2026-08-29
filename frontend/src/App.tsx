import { createContext, FormEvent, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { BrowserQRCodeReader } from "@zxing/browser";

const USER_ID_STORAGE_KEY = "arol.user-id";
const ACCESS_TOKEN_STORAGE_KEY = "arol.access-token";
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

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  agent?: string;
  sources?: ManualSearchResult[];
  data?: ChatData | null;
};

type ChatResponse = {
  answer: string;
  agent: string;
  sources: ManualSearchResult[];
  data: ChatData | null;
};

type AlarmRecord = {
  alarm_id: string;
  timestamp: string;
  alarm_code: string;
  severity: string;
  alarm_status: string;
};

type TelemetryRecord = {
  timestamp: string;
  operational_status: string;
  production_rate_bph: number;
  uptime_percentage: number;
  alarm_count: number;
  temperature_c: number | null;
  energy_kwh: number | null;
  health_note: string | null;
};

type MaintenanceTicketRecord = {
  ticket_id: string;
  alarm_id: string | null;
  ticket_type: string;
  ticket_status: string;
  priority: string;
  created_date: string;
  owner_role: string;
};

type OrderRecord = {
  order_id: string;
  quote_id: string;
  order_status: string;
  shipment_status: string;
};

type QuoteRecord = {
  quote_id: string;
  valid_until: string | null;
  revision_number: number | null;
  revision_status: string | null;
  discount_rate: number | null;
  line_total: number;
};

type ChatData = {
  machine_id?: string;
  alarms?: AlarmRecord[];
  telemetry?: TelemetryRecord[];
  maintenance_tickets?: MaintenanceTicketRecord[];
  orders?: OrderRecord[];
  quotes?: QuoteRecord[];
};

type ServiceTicket = MaintenanceTicketRecord & {
  machine_id: string;
  serial_number: string;
};

type ManualSearchResult = {
  citation: {
    source: "manual";
    file: string;
    page: number;
    section: string;
  };
  excerpt: string;
  title: string;
  highlights: string[];
  relevance: number;
  similarity: number;
};

function manualRelevanceLabel(score: number) {
  if (score >= 0.7) return "High relevance";
  if (score >= 0.55) return "Relevant match";
  return "Possible match";
}

type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  user: {
    user_id: string;
    company_id: string;
    visibility: string;
  };
};

type NotificationKind = "success" | "error" | "info";

type Notification = {
  id: number;
  kind: NotificationKind;
  message: string;
};

type NotificationContextValue = {
  notify: (message: string, kind?: NotificationKind) => void;
};

const NotificationContext = createContext<NotificationContextValue | null>(null);

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function activeUserId() {
  return localStorage.getItem(USER_ID_STORAGE_KEY);
}

function activeAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
}

function authorizationHeader(): Record<string, string> {
  const token = activeAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function readableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status >= 500) return "The service is temporarily unavailable. Please try again shortly.";
    return error.message || fallback;
  }
  if (error instanceof TypeError) return "Network error. Check your connection and try again.";
  return error instanceof Error ? error.message : fallback;
}

function handleUnauthorized(status: number) {
  if (status !== 401 || !activeAccessToken()) return;
  localStorage.removeItem(USER_ID_STORAGE_KEY);
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  sessionStorage.setItem("arol.session-notice", "Your session has expired. Please sign in again.");
  window.setTimeout(() => window.location.assign("/login"), 0);
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authorizationHeader(),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(body?.detail ?? "Unable to load the requested data.", response.status);
  }
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authorizationHeader(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(errorBody?.detail ?? "Unable to send the question.", response.status);
  }
  return response.json() as Promise<T>;
}

async function publicPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(errorBody?.detail ?? "Unable to sign in.", response.status);
  }
  return response.json() as Promise<T>;
}

async function fetchManualPdf(machineId: string, sourceFile: string): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/machines/${encodeURIComponent(machineId)}/manuals/files/${encodeURIComponent(sourceFile)}`,
    { headers: authorizationHeader() },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(body?.detail ?? "Unable to open the manual.", response.status);
  }
  return response.blob();
}

function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const notify = useCallback((message: string, kind: NotificationKind = "info") => {
    const id = Date.now() + Math.floor(Math.random() * 1_000);
    setNotifications((current) => [...current, { id, kind, message }]);
    window.setTimeout(() => setNotifications((current) => current.filter((item) => item.id !== id)), 5_000);
  }, []);

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      <div className="notification-stack" aria-live="polite" aria-atomic="true">
        {notifications.map((notification) => <div key={notification.id} className={`notification notification-${notification.kind}`} role="status">{notification.message}</div>)}
      </div>
    </NotificationContext.Provider>
  );
}

function useNotifications() {
  const context = useContext(NotificationContext);
  if (context === null) throw new Error("Notifications must be used within NotificationProvider.");
  return context;
}

function AppHeader() {
  const navigate = useNavigate();
  const userId = activeUserId();
  const { notify } = useNotifications();

  function logout() {
    localStorage.removeItem(USER_ID_STORAGE_KEY);
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    notify("You have been signed out.", "info");
    navigate("/login");
  }

  return (
    <header className="app-header">
      <button className="wordmark" type="button" onClick={() => navigate("/home")} aria-label="Go to home">AROL</button>
      <nav className="header-nav" aria-label="Main navigation">
        <button type="button" onClick={() => navigate("/orders")}>Orders</button>
        <button type="button" onClick={() => navigate("/quotes")}>Quotes</button>
        <button type="button" onClick={() => navigate("/service")}>Support</button>
      </nav>
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
          <p>AROL S.P.A. – Viale Italia, 193 · 14053 Canelli (Asti), Italy</p>
          <p>Tax ID and VAT no. 03217610967 · REA AT 108104</p>
        </div>
        <nav className="footer-nav" aria-label="AROL links">
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
          <a href="https://www.privacylab.it/informativa.php?12701471129&lang=en" target="_blank" rel="noreferrer">Privacy Policy</a>
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
  const { notify } = useNotifications();
  const [userId, setUserId] = useState(() => localStorage.getItem(USER_ID_STORAGE_KEY) ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(() => {
    const notice = sessionStorage.getItem("arol.session-notice") ?? "";
    sessionStorage.removeItem("arol.session-notice");
    return notice;
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryQrValue = new URLSearchParams(location.search).get("qr")?.trim();
  const qrValue = routeQrValue ?? queryQrValue;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedUserId = userId.trim().toUpperCase();
    if (!normalizedUserId) {
      setError("Enter your user ID.");
      return;
    }
    if (password.length < 8) {
      setError("The password must contain at least 8 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      const session = await publicPost<LoginResponse>("/auth/login", {
        user_id: normalizedUserId,
        password,
      });
      localStorage.setItem(USER_ID_STORAGE_KEY, session.user.user_id);
      localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, session.access_token);
      notify(`Signed in as ${session.user.user_id}.`, "success");
      navigate(qrValue ? `/machines/${encodeURIComponent(qrValue)}` : "/home");
    } catch (loginError) {
      const message = loginError instanceof ApiError && loginError.status === 401
        ? "Invalid credentials. Check your details and try again."
        : readableError(loginError, "Unable to sign in.");
      setError(message);
      notify(message, "error");
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
              Machine detected: <strong>{qrValue}</strong>
            </p>
          )}

          <label htmlFor="user-id">User ID</label>
          <input
            id="user-id"
            name="user-id"
            autoComplete="username"
            placeholder="E.g. USR-001"
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
            <p id="user-id-help" className="field-help">Enter your user ID and password.</p>
          )}

          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setError("");
            }}
            minLength={8}
            required
          />

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Log in"} <span aria-hidden="true">→</span>
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
  const [isScannerOpen, setIsScannerOpen] = useState(false);
  const navigate = useNavigate();
  const { notify } = useNotifications();

  useEffect(() => {
    apiGet<MachineSummary[]>("/machines")
      .then(setMachines)
      .catch((loadError: unknown) => {
        const message = readableError(loadError, "Unable to load the machine list.");
        setError(message);
        notify(message, "error");
      })
      .finally(() => setLoading(false));
  }, [notify]);

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page-content">
        <p className="eyebrow dark-eyebrow">YOUR EQUIPMENT</p>
        <h1>Connected Machines</h1>
        <p className="page-intro">Select a machine to view its technical documentation and telemetry, or scan a QR code to link a new one.</p>
        <button className="qr-scanner-launcher" type="button" onClick={() => setIsScannerOpen(true)}>
          <span aria-hidden="true">⌁</span> Scan QR code
        </button>
        {loading && <p className="status-message">Loading machines…</p>}
        {error && <p className="status-message error-message">{error}</p>}
        {!loading && !error && machines.length === 0 && <p className="status-message">No machines are available for your company.</p>}
        {!loading && !error && machines.length > 0 && (
          <section className="machine-grid" aria-label="Machine list">
            {machines.map((machine) => (
              <button key={machine.machine_id} className="machine-card" type="button" onClick={() => navigate(`/machines/${machine.machine_id}`)}>
                <span className="machine-id">{machine.machine_id}</span>
                <strong>{machine.model_code}</strong>
                <span>{machine.plant_location ?? "Location unavailable"}</span>
                <small>Serial {machine.serial_number}</small>
                <span className="card-arrow" aria-hidden="true">→</span>
              </button>
            ))}
          </section>
        )}
      </main>
      {isScannerOpen && <QrScanner onClose={() => setIsScannerOpen(false)} onDetected={(qrValue) => {
        setIsScannerOpen(false);
        navigate(`/machines/${encodeURIComponent(qrValue)}`);
      }} />}
      <AppFooter />
    </div>
  );
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" }).format(value);
}

function ChatStructuredData({ data }: { data: ChatData }) {
  const hasRecords = Boolean(
    data.alarms?.length
    || data.telemetry?.length
    || data.maintenance_tickets?.length
    || data.orders?.length
    || data.quotes?.length,
  );
  if (!hasRecords) return null;

  return (
    <section className="chat-data" aria-label="Retrieved records">
      {data.alarms && data.alarms.length > 0 && (
        <article className="chat-data-card">
          <h4>Recent alarms</h4>
          <div className="chat-data-table-wrap"><table><thead><tr><th>Date</th><th>Code</th><th>Severity</th><th>Status</th></tr></thead><tbody>
            {data.alarms.map((alarm) => <tr key={alarm.alarm_id}><td>{formatDateTime(alarm.timestamp)}</td><td>{alarm.alarm_code}</td><td>{alarm.severity}</td><td>{alarm.alarm_status}</td></tr>)}
          </tbody></table></div>
        </article>
      )}
      {data.telemetry && data.telemetry.length > 0 && (
        <article className="chat-data-card">
          <h4>Latest telemetry</h4>
          <div className="chat-data-table-wrap"><table><thead><tr><th>Date</th><th>Status</th><th>Production</th><th>Uptime</th><th>Temp.</th></tr></thead><tbody>
            {data.telemetry.map((entry) => <tr key={entry.timestamp}><td>{formatDateTime(entry.timestamp)}</td><td>{entry.operational_status}</td><td>{entry.production_rate_bph.toLocaleString("en-GB")} bph</td><td>{entry.uptime_percentage}%</td><td>{entry.temperature_c ?? "—"}{entry.temperature_c !== null ? " °C" : ""}</td></tr>)}
          </tbody></table></div>
        </article>
      )}
      {data.maintenance_tickets && data.maintenance_tickets.length > 0 && (
        <article className="chat-data-card">
          <h4>Maintenance tickets</h4>
          <div className="chat-data-table-wrap"><table><thead><tr><th>Date</th><th>Ticket</th><th>Priority</th><th>Status</th></tr></thead><tbody>
            {data.maintenance_tickets.map((ticket) => <tr key={ticket.ticket_id}><td>{formatDateTime(ticket.created_date)}</td><td>{ticket.ticket_id}</td><td>{ticket.priority}</td><td>{ticket.ticket_status}</td></tr>)}
          </tbody></table></div>
        </article>
      )}
      {data.orders && data.orders.length > 0 && (
        <article className="chat-data-card">
          <h4>Orders</h4>
          <div className="chat-data-table-wrap"><table><thead><tr><th>Order</th><th>Status</th><th>Shipment</th></tr></thead><tbody>
            {data.orders.map((order) => <tr key={order.order_id}><td>{order.order_id}</td><td>{order.order_status}</td><td>{order.shipment_status}</td></tr>)}
          </tbody></table></div>
        </article>
      )}
      {data.quotes && data.quotes.length > 0 && (
        <article className="chat-data-card">
          <h4>Quotes</h4>
          <div className="chat-data-table-wrap"><table><thead><tr><th>Quote</th><th>Status</th><th>Total</th></tr></thead><tbody>
            {data.quotes.map((quote) => <tr key={quote.quote_id}><td>{quote.quote_id}</td><td>{quote.revision_status ?? "—"}</td><td>{formatCurrency(quote.line_total)}</td></tr>)}
          </tbody></table></div>
        </article>
      )}
    </section>
  );
}

function OrdersPage() {
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { notify } = useNotifications();

  useEffect(() => {
    apiGet<OrderRecord[]>("/orders")
      .then(setOrders)
      .catch((loadError: unknown) => {
        const message = readableError(loadError, "Unable to load orders.");
        setError(message);
        notify(message, "error");
      })
      .finally(() => setLoading(false));
  }, [notify]);

  return <RecordsLayout eyebrow="ORDERS" title="Your orders" intro="Review order and shipment status." loading={loading} error={error} empty={orders.length === 0 ? "No orders available." : undefined}>
    <div className="records-table-wrap"><table className="records-table"><thead><tr><th>Order</th><th>Quote</th><th>Order status</th><th>Shipment</th></tr></thead><tbody>
      {orders.map((order) => <tr key={order.order_id}><td>{order.order_id}</td><td>{order.quote_id}</td><td>{order.order_status}</td><td>{order.shipment_status}</td></tr>)}
    </tbody></table></div>
  </RecordsLayout>;
}

function QuotesPage() {
  const [quotes, setQuotes] = useState<QuoteRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { notify } = useNotifications();

  useEffect(() => {
    apiGet<QuoteRecord[]>("/quotes")
      .then(setQuotes)
      .catch((loadError: unknown) => {
        const message = readableError(loadError, "Unable to load quotes.");
        setError(message);
        notify(message, "error");
      })
      .finally(() => setLoading(false));
  }, [notify]);

  return <RecordsLayout eyebrow="QUOTES" title="Quotes" intro="Review quote revisions, validity, discounts and totals." loading={loading} error={error} empty={quotes.length === 0 ? "No quotes available." : undefined}>
    <div className="records-table-wrap"><table className="records-table"><thead><tr><th>Quote</th><th>Revision</th><th>Status</th><th>Valid until</th><th>Discount</th><th>Total</th></tr></thead><tbody>
      {quotes.map((quote) => <tr key={quote.quote_id}><td>{quote.quote_id}</td><td>{quote.revision_number ?? "—"}</td><td>{quote.revision_status ?? "—"}</td><td>{quote.valid_until ? formatDateTime(quote.valid_until) : "—"}</td><td>{quote.discount_rate === null ? "—" : `${(quote.discount_rate * 100).toLocaleString("en-GB")}%`}</td><td>{formatCurrency(quote.line_total)}</td></tr>)}
    </tbody></table></div>
  </RecordsLayout>;
}

function ServicePage() {
  const [tickets, setTickets] = useState<ServiceTicket[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { notify } = useNotifications();

  useEffect(() => {
    let isCurrent = true;
    apiGet<MachineSummary[]>("/machines")
      .then(async (machines) => {
        const ticketGroups = await Promise.all(machines.map(async (machine) => {
          const machineTickets = await apiGet<MaintenanceTicketRecord[]>(`/machines/${encodeURIComponent(machine.machine_id)}/maintenance-tickets?limit=20`);
          return machineTickets.map((ticket) => ({ ...ticket, machine_id: machine.machine_id, serial_number: machine.serial_number }));
        }));
        if (isCurrent) setTickets(ticketGroups.flat().sort((first, second) => second.created_date.localeCompare(first.created_date)));
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        const message = readableError(loadError, "Unable to load support tickets.");
        setError(message);
        notify(message, "error");
      })
      .finally(() => { if (isCurrent) setLoading(false); });
    return () => { isCurrent = false; };
  }, [notify]);

  return <RecordsLayout eyebrow="AFTER-SALES SERVICE" title="After-sales support" intro="Review maintenance tickets for your company's machines." loading={loading} error={error} empty={tickets.length === 0 ? "No support tickets available." : undefined}>
    <div className="records-table-wrap"><table className="records-table"><thead><tr><th>Ticket</th><th>Machine</th><th>Date</th><th>Type</th><th>Priority</th><th>Status</th><th>Owner</th></tr></thead><tbody>
      {tickets.map((ticket) => <tr key={`${ticket.machine_id}-${ticket.ticket_id}`}><td>{ticket.ticket_id}</td><td>{ticket.machine_id}<small>Serial {ticket.serial_number}</small></td><td>{formatDateTime(ticket.created_date)}</td><td>{ticket.ticket_type}</td><td>{ticket.priority}</td><td>{ticket.ticket_status}</td><td>{ticket.owner_role}</td></tr>)}
    </tbody></table></div>
  </RecordsLayout>;
}

function RecordsLayout({ eyebrow, title, intro, loading, error, empty, children }: { eyebrow: string; title: string; intro: string; loading: boolean; error: string; empty?: string; children: ReactNode }) {
  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page-content records-page">
        <p className="eyebrow dark-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-intro">{intro}</p>
        {loading && <p className="status-message">Loading data…</p>}
        {error && <p className="status-message error-message">{error}</p>}
        {!loading && !error && empty && <p className="status-message">{empty}</p>}
        {!loading && !error && !empty && children}
      </main>
      <AppFooter />
    </div>
  );
}

function QrScanner({ onClose, onDetected }: { onClose: () => void; onDetected: (value: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Starting camera…");

  useEffect(() => {
    const reader = new BrowserQRCodeReader();
    let active = true;
    let hasDetected = false;
    let stream: MediaStream | undefined;
    let stopScanner: (() => void) | undefined;
    let noResultTimer: number | undefined;
    let detectedTimer: number | undefined;

    async function startScanner() {
      if (!videoRef.current || !navigator.mediaDevices?.getUserMedia) {
        setError("The camera is not supported by this browser.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia(
          { video: { facingMode: { ideal: "environment" } }, audio: false },
        );
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        if (!active) return;
        setStatus("Point the camera at the machine QR code.");
        noResultTimer = window.setTimeout(() => {
          if (active && !hasDetected) setStatus("Camera is active, but no QR code has been detected yet.");
        }, 5_000);
        const controls = await reader.decodeFromStream(
          stream,
          videoRef.current,
          (result) => {
            const value = result?.getText().trim();
            if (active && !hasDetected && value) {
              hasDetected = true;
              window.clearTimeout(noResultTimer);
              setStatus(`QR code detected: ${value}. Opening machine…`);
              detectedTimer = window.setTimeout(() => onDetected(value), 350);
            }
          },
        );
        stopScanner = () => controls.stop();
        if (!active) stopScanner();
      } catch (scanError) {
        if (!active) return;
        if (scanError instanceof DOMException && scanError.name === "NotAllowedError") {
          setError("Camera access was denied. Allow camera access in your browser and try again.");
        } else {
          setError("Unable to start the camera. Check that it is not being used by another application.");
        }
      }
    }

    startScanner();
    return () => {
      active = false;
      window.clearTimeout(noResultTimer);
      window.clearTimeout(detectedTimer);
      stopScanner?.();
      stream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [onDetected]);

  return (
    <div className="qr-scanner-backdrop" role="presentation" onClick={onClose}>
      <section className="qr-scanner-dialog" role="dialog" aria-modal="true" aria-labelledby="qr-scanner-title" onClick={(event) => event.stopPropagation()}>
        <div className="qr-scanner-heading">
          <div><p className="eyebrow dark-eyebrow">QR SCANNER</p><h2 id="qr-scanner-title">Scan the QR code</h2></div>
          <button className="chat-close-button" type="button" onClick={onClose} aria-label="Close scanner">×</button>
        </div>
        <p className="qr-scanner-status" role="status">{status}</p>
        {!error && <video className="qr-video" ref={videoRef} autoPlay muted playsInline />}
        {error && <p className="status-message error-message">{error}</p>}
        {!error && <p className="qr-scanner-help">Keep the entire QR code in the frame, well lit and free of reflections. If it is not read after a few seconds, move the code closer or farther away.</p>}
        <button className="qr-scanner-close" type="button" onClick={onClose}>Cancel</button>
      </section>
    </div>
  );
}

function AssistantChat({ machineId, onClose }: { machineId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [openingSource, setOpeningSource] = useState<string | null>(null);
  const { notify } = useNotifications();

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || isSending) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: message,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError("");
    setIsSending(true);

    try {
      const result = await apiPost<ChatResponse>("/chat", {
        message,
        machine_id: machineId,
      });
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: result.answer,
          agent: result.agent,
          sources: result.sources,
          data: result.data,
        },
      ]);
    } catch (sendError) {
      const errorMessage = readableError(sendError, "Unable to send the question.");
      setError(errorMessage);
      notify(errorMessage, "error");
    } finally {
      setIsSending(false);
    }
  }

  async function openManualSource(source: ManualSearchResult, sourceKey: string) {
    const manualWindow = window.open("", "_blank");
    if (!manualWindow) {
      const message = "Your browser blocked the new tab. Allow pop-ups for this site and try again.";
      setError(message);
      notify(message, "error");
      return;
    }

    setError("");
    setOpeningSource(sourceKey);
    try {
      const pdf = await fetchManualPdf(machineId, source.citation.file);
      const pdfUrl = URL.createObjectURL(pdf);
      manualWindow.location.href = `${pdfUrl}#page=${source.citation.page}`;
      window.setTimeout(() => URL.revokeObjectURL(pdfUrl), 60_000);
      notify(`Opening ${source.citation.file} at page ${source.citation.page}.`, "success");
    } catch (openError) {
      manualWindow.close();
      const message = readableError(openError, "Unable to open the manual.");
      setError(message);
      notify(message, "error");
    } finally {
      setOpeningSource(null);
    }
  }

  return (
    <>
      <div className="chat-drawer-backdrop" aria-hidden="true" onClick={onClose} />
      <section className="assistant-chat" role="dialog" aria-modal="true" aria-labelledby="assistant-chat-title">
      <div className="assistant-chat-heading">
        <div>
          <p className="eyebrow dark-eyebrow">AROL ASSISTANT</p>
          <h2 id="assistant-chat-title">Ask about this machine</h2>
        </div>
        <div className="chat-heading-actions">
          <span className="chat-machine-context">{machineId}</span>
          <button className="chat-close-button" type="button" onClick={onClose} aria-label="Close chat">×</button>
        </div>
      </div>
      <p className="chat-intro">Ask about alarms, telemetry, maintenance, manuals, orders and quotes.</p>
      <div className="chat-history" aria-live="polite">
        {messages.length === 0 && (
          <p className="chat-empty">For example: “Are there any recent alarms?” or “Find safety instructions in the manual”.</p>
        )}
        {messages.map((message) => (
          <article key={message.id} className={`chat-message chat-message-${message.role}`}>
            <span className="chat-message-label">{message.role === "user" ? "You" : "AROL Assistant"}</span>
            <p>{message.content}</p>
            {message.sources && message.sources.length > 0 && (
              <div className="chat-manual-sources" aria-label="Manual sources">
                {message.sources.map((source, index) => (
                  <article className="chat-manual-source" key={`${source.citation.file}-${source.citation.page}-${index}`}>
                    <div className="chat-manual-source-heading">
                      <strong>{source.title}</strong>
                      <span>{manualRelevanceLabel(source.relevance)}</span>
                    </div>
                    <p>{source.excerpt}</p>
                    {source.highlights.length > 0 && (
                      <div className="chat-manual-highlights">
                        {source.highlights.map((term) => <mark key={term}>{term}</mark>)}
                      </div>
                    )}
                    <div className="chat-manual-source-footer">
                      <small>{source.citation.file} · Page {source.citation.page} · {source.citation.section}</small>
                      <button
                        type="button"
                        className="chat-open-manual-button"
                        onClick={() => openManualSource(source, `${message.id}-${index}`)}
                        disabled={openingSource !== null}
                      >
                        {openingSource === `${message.id}-${index}` ? "Opening…" : "Open source"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            {message.data && <ChatStructuredData data={message.data} />}
            {message.agent && <small>Agent: {message.agent}</small>}
          </article>
        ))}
        {isSending && <p className="chat-thinking">AROL Assistant is preparing a response…</p>}
      </div>
      {error && <p className="status-message error-message">{error}</p>}
      <form className="chat-form" onSubmit={sendMessage}>
        <label className="sr-only" htmlFor="chat-message">Question for AROL Assistant</label>
        <textarea
          id="chat-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Write a question about this machine…"
          rows={3}
          disabled={isSending}
        />
        <button type="submit" disabled={isSending || !draft.trim()}>
          {isSending ? "Sending…" : "Send question"}
        </button>
      </form>
      </section>
    </>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" });
}

function OperationalData({ machineId }: { machineId: string }) {
  const [alarms, setAlarms] = useState<AlarmRecord[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryRecord[]>([]);
  const [tickets, setTickets] = useState<MaintenanceTicketRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const { notify } = useNotifications();

  useEffect(() => {
    let isCurrent = true;
    setLoading(true);
    setError("");
    Promise.all([
      apiGet<AlarmRecord[]>(`/machines/${encodeURIComponent(machineId)}/alarms?limit=5`),
      apiGet<TelemetryRecord[]>(`/machines/${encodeURIComponent(machineId)}/telemetry?limit=6`),
      apiGet<MaintenanceTicketRecord[]>(`/machines/${encodeURIComponent(machineId)}/maintenance-tickets?limit=5`),
    ])
      .then(([loadedAlarms, loadedTelemetry, loadedTickets]) => {
        if (!isCurrent) return;
        setAlarms(loadedAlarms);
        setTelemetry(loadedTelemetry);
        setTickets(loadedTickets);
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) return;
        const message = readableError(loadError, "Unable to load operational data.");
        setError(message);
        notify(message, "error");
      })
      .finally(() => {
        if (isCurrent) setLoading(false);
      });
    return () => { isCurrent = false; };
  }, [machineId, notify]);

  return (
    <section className="operational-data" aria-labelledby="operational-data-title">
      <p className="eyebrow dark-eyebrow">OPERATIONAL DATA</p>
      <h2 id="operational-data-title">Machine operational status</h2>
      {loading && <p className="status-message">Loading telemetry, alarms and maintenance data…</p>}
      {error && <p className="status-message error-message">{error}</p>}
      {!loading && !error && (
        <div className="operational-grid">
          <article className="data-panel">
            <h3>Recent telemetry</h3>
            {telemetry.length === 0 ? <p className="data-empty">No telemetry available.</p> : (
              <div className="data-table-wrap"><table><thead><tr><th>Date</th><th>Status</th><th>Production</th><th>Uptime</th><th>Temp.</th></tr></thead><tbody>
                {telemetry.map((entry) => <tr key={entry.timestamp}><td>{formatDateTime(entry.timestamp)}</td><td>{entry.operational_status}</td><td>{entry.production_rate_bph.toLocaleString("en-GB")} bph</td><td>{entry.uptime_percentage}%</td><td>{entry.temperature_c ?? "—"}{entry.temperature_c !== null ? " °C" : ""}</td></tr>)}
              </tbody></table></div>
            )}
          </article>
          <article className="data-panel">
            <h3>Recent alarms</h3>
            {alarms.length === 0 ? <p className="data-empty">No recent alarms.</p> : (
              <div className="data-table-wrap"><table><thead><tr><th>Date</th><th>Code</th><th>Severity</th><th>Status</th></tr></thead><tbody>
                {alarms.map((alarm) => <tr key={alarm.alarm_id}><td>{formatDateTime(alarm.timestamp)}</td><td>{alarm.alarm_code}</td><td><span className={`severity severity-${alarm.severity.toLowerCase()}`}>{alarm.severity}</span></td><td>{alarm.alarm_status}</td></tr>)}
              </tbody></table></div>
            )}
          </article>
          <article className="data-panel data-panel-wide">
            <h3>Maintenance tickets</h3>
            {tickets.length === 0 ? <p className="data-empty">No maintenance tickets available.</p> : (
              <div className="data-table-wrap"><table><thead><tr><th>ID</th><th>Opening date</th><th>Type</th><th>Priority</th><th>Status</th><th>Owner</th></tr></thead><tbody>
                {tickets.map((ticket) => <tr key={ticket.ticket_id}><td>{ticket.ticket_id}</td><td>{formatDateTime(ticket.created_date)}</td><td>{ticket.ticket_type}</td><td>{ticket.priority}</td><td>{ticket.ticket_status}</td><td>{ticket.owner_role}</td></tr>)}
              </tbody></table></div>
            )}
          </article>
        </div>
      )}
    </section>
  );
}

function ManualSearch({ machineId }: { machineId: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ManualSearchResult[]>([]);
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [openingResult, setOpeningResult] = useState<number | null>(null);
  const { notify } = useNotifications();

  async function searchManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery || isSearching) return;

    setError("");
    setIsSearching(true);
    setHasSearched(true);
    try {
      const loadedResults = await apiGet<ManualSearchResult[]>(
        `/machines/${encodeURIComponent(machineId)}/manuals/search?query=${encodeURIComponent(normalizedQuery)}&limit=5`,
      );
      setResults(loadedResults);
    } catch (searchError) {
      const message = readableError(searchError, "Unable to search the manual.");
      setResults([]);
      setError(message);
      notify(message, "error");
    } finally {
      setIsSearching(false);
    }
  }

  async function openManual(result: ManualSearchResult, index: number) {
    // Opening the tab synchronously keeps this action permitted by browser
    // popup protection; the protected PDF is loaded into it afterwards.
    const manualWindow = window.open("", "_blank");
    if (!manualWindow) {
      const message = "Your browser blocked the new tab. Allow pop-ups for this site and try again.";
      setError(message);
      notify(message, "error");
      return;
    }

    setError("");
    setOpeningResult(index);
    try {
      const pdf = await fetchManualPdf(machineId, result.citation.file);
      const pdfUrl = URL.createObjectURL(pdf);
      manualWindow.location.href = `${pdfUrl}#page=${result.citation.page}`;
      window.setTimeout(() => URL.revokeObjectURL(pdfUrl), 60_000);
      notify(`Opening ${result.citation.file} at page ${result.citation.page}.`, "success");
    } catch (openError) {
      manualWindow.close();
      const message = readableError(openError, "Unable to open the manual.");
      setError(message);
      notify(message, "error");
    } finally {
      setOpeningResult(null);
    }
  }

  return (
    <section className="manual-search" aria-labelledby="manual-search-title">
      <div>
        <p className="eyebrow dark-eyebrow">TECHNICAL MANUALS</p>
        <h2 id="manual-search-title">Search this machine's manuals</h2>
        <p>Results come exclusively from local manuals associated with {machineId}.</p>
      </div>
      <form className="manual-search-form" onSubmit={searchManual}>
        <label className="sr-only" htmlFor="manual-query">Search the manual</label>
        <input
          id="manual-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="E.g. safety instructions or pneumatic pressure"
          disabled={isSearching}
        />
        <button type="submit" disabled={isSearching || !query.trim()}>
          {isSearching ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="status-message error-message">{error}</p>}
      {hasSearched && !isSearching && !error && results.length === 0 && (
        <p className="status-message">No relevant passage was found in this machine's manual.</p>
      )}
      {results.length > 0 && (
        <div className="manual-results" aria-live="polite">
          {results.map((result, index) => (
            <article className="manual-result" key={`${result.citation.file}-${result.citation.page}-${index}`}>
              <div className="manual-result-summary">
                <h3>{result.title}</h3>
                <span className="manual-relevance">{manualRelevanceLabel(result.relevance)}</span>
              </div>
              <div className="manual-citation">
                <div>
                  <strong>{result.citation.file}</strong>
                  <span>Page {result.citation.page} · {result.citation.section}</span>
                </div>
                <button type="button" className="open-manual-button" onClick={() => openManual(result, index)} disabled={openingResult !== null}>
                  {openingResult === index ? "Opening…" : `Open at page ${result.citation.page}`}
                </button>
              </div>
              <p>{result.excerpt}</p>
              {result.highlights.length > 0 && (
                <div className="manual-highlights" aria-label="Matched terms">
                  <span>Matched terms</span>
                  {result.highlights.map((term) => <mark key={term}>{term}</mark>)}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MachinePage() {
  const { qrValue } = useParams();
  const navigate = useNavigate();
  const [machine, setMachine] = useState<MachineContext | null>(null);
  const [error, setError] = useState("");
  const [isChatOpen, setIsChatOpen] = useState(false);
  const { notify } = useNotifications();

  useEffect(() => {
    if (!qrValue) return;
    apiGet<MachineContext>(`/machines/lookup/${encodeURIComponent(qrValue)}`)
      .then(setMachine)
      .catch((loadError: unknown) => {
        const message = readableError(loadError, "Unable to load the machine context.");
        setError(message);
        notify(message, "error");
      });
  }, [qrValue, notify]);

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
            <OperationalData machineId={machine.machine_id} />
            <ManualSearch machineId={machine.machine_id} />
            <button className="assistant-launcher" type="button" onClick={() => setIsChatOpen(true)} aria-label="Open AROL Assistant" title="Open AROL Assistant">
              <span aria-hidden="true">Chat</span>
            </button>
            {isChatOpen && <AssistantChat machineId={machine.machine_id} onClose={() => setIsChatOpen(false)} />}
            <section className="next-actions" aria-label="Machine features">
              <article><strong>AROL Assistant</strong><span>The chat is connected to the machine context and available backend agents.</span></article>
              <article><strong>Operational Data</strong><span>View live alarms, IoT telemetry and maintenance tickets for this machine.</span></article>
            </section>
          </>
        )}
      </main>
      <AppFooter />
    </div>
  );
}

function RequireSession({ children }: { children: ReactNode }) {
  return activeAccessToken() ? children : <Navigate to="/login" replace />;
}

function MachineRoute() {
  const { qrValue } = useParams();
  return activeAccessToken() ? <MachinePage /> : <LoginPage qrValue={qrValue} />;
}

export default function App() {
  return (
    <NotificationProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/machines/:qrValue" element={<MachineRoute />} />
        <Route path="/home" element={<RequireSession><HomePage /></RequireSession>} />
        <Route path="/orders" element={<RequireSession><OrdersPage /></RequireSession>} />
        <Route path="/quotes" element={<RequireSession><QuotesPage /></RequireSession>} />
        <Route path="/service" element={<RequireSession><ServicePage /></RequireSession>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </NotificationProvider>
  );
}
