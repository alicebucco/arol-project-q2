export type MachineSummary = {
  machine_id: string;
  serial_number: string;
  model_code: string;
  model_description: string | null;
  plant_location: string | null;
  configuration_profile: string | null;
};

export type MachineContext = MachineSummary & {
  company_id: string;
  company_name: string;
  model_id: string;
  operational_context: string;
  delivery_date: string | null;
  plc_family: string | null;
  software_version: string | null;
};

export type AlarmRecord = { alarm_id: string; timestamp: string; alarm_code: string; severity: string; alarm_status: string };
export type AlarmPattern = { alarm_code: string; occurrences: number; first_seen: string; last_seen: string; latest_status: string };
export type ProductionAssessment = {
  nominal_production_rate_bph: number | null;
  production_vs_nominal_percent: number | null;
  status: "within_expected_range" | "below_nominal_reference" | "above_nominal_reference" | "not_assessed";
  reason: string;
};
export type TelemetryRecord = {
  timestamp: string; operational_status: string; production_rate_bph: number; uptime_percentage: number;
  alarm_count: number; temperature_c: number | null; energy_kwh: number | null; health_note: string | null;
  production_assessment?: ProductionAssessment | null;
};
export type MaintenanceTicketRecord = {
  ticket_id: string; alarm_id: string | null; ticket_type: string; ticket_status: string;
  priority: string; created_date: string; owner_role: string;
};
export type OrderRecord = { order_id: string; quote_id: string; order_status: string; shipment_status: string };
export type OrderItem = { quote_line_id: string; machine_id: string | null; description: string | null; price: number };
export type OrderDetail = OrderRecord & {
  currency: string | null;
  approved_revision: { revision_number: number; revision_status: string; discount_rate: number | null } | null;
  items: OrderItem[];
  fulfillment: { order_line_id: string; fulfillment_status: string }[];
};
export type UserProfile = {
  user_id: string; company_id: string; visibility: string; first_name: string; last_name: string;
  email: string; job_title: string; company_name: string; country: string; city: string;
  sector: string; currency: string; locale: string;
};
export type QuoteRecord = {
  quote_id: string; valid_until: string | null; validity_status: "Valid" | "Expired" | "Unknown";
  revision_number: number | null; revision_status: string | null; discount_rate: number | null; line_total: number;
};
export type QuoteLineDetail = { quote_line_id: string; machine_id: string | null; description: string | null; price: number };
export type QuoteRevisionDetail = {
  quote_revision_id: string; revision_number: number; revision_status: string; discount_rate: number | null;
  issued_at: string | null; change_summary: string | null; line_total: number; lines: QuoteLineDetail[];
};
export type QuoteLineChange = {
  change: "added" | "removed" | "price_changed"; machine_id: string | null; description: string | null;
  previous_price: number | null; current_price: number | null;
};
export type QuoteHistory = {
  quote_id: string; valid_until: string | null; validity_status: "Valid" | "Expired" | "Unknown";
  currency: string | null; created_at: string | null; description: string | null;
  revisions: QuoteRevisionDetail[]; latest_comparison: QuoteLineChange[];
};
export type MaintenanceObservation = {
  machine_id: string; observed_productive_hours: number; first_snapshot: string | null; last_snapshot: string | null;
  snapshot_count: number; documented_threshold_hours: number[]; reached_threshold_hours: number[];
  next_threshold_hours: number | null; scope_note: string;
};
export type ChatData = {
  machine_id?: string; alarms?: AlarmRecord[]; alarm_patterns?: AlarmPattern[]; telemetry?: TelemetryRecord[];
  maintenance_tickets?: MaintenanceTicketRecord[]; orders?: OrderRecord[]; quotes?: QuoteRecord[];
  maintenance_observation?: MaintenanceObservation;
};
export type ManualSearchResult = {
  citation: { source: "manual"; chunk_id?: string | null; file: string; page: number; section: string };
  excerpt: string; title: string; highlights: string[]; relevance: number; similarity: number;
  similarity_threshold_met?: boolean; alarm_code_match?: "not_requested" | "exact_in_passage" | "semantic_only";
  excerpt_is_complete_chunk?: boolean; section_category?: string | null;
  section_category_is_inferred?: boolean; documented_section_title?: string | null;
};
export type ChatAgent = "iot" | "manuals" | "service" | "orders";
export type ChatMessage = { id: number; role: "user" | "assistant"; content: string; agent?: ChatAgent[] | null; sources?: ManualSearchResult[]; data?: ChatData | null };
export type ChatResponse = { answer: string; agent: ChatAgent[] | null; sources: ManualSearchResult[]; data: ChatData | null };
export type ServiceTicket = MaintenanceTicketRecord & { machine_id: string; serial_number: string };
export type LoginResponse = { access_token: string; token_type: "bearer"; user: { user_id: string; company_id: string; visibility: string } };
