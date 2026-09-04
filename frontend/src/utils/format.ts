import type { TelemetryRecord } from "../types";

export function formatCurrency(value: number, currency = "EUR") {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(value);
}

export function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" });
}

export function productionReference(entry: TelemetryRecord) {
  const assessment = entry.production_assessment;
  if (!assessment || assessment.nominal_production_rate_bph === null) return "Reference unavailable";
  if (assessment.production_vs_nominal_percent === null) return "Not assessed";
  const labels = {
    within_expected_range: "Within expected range", below_nominal_reference: "Below nominal reference",
    above_nominal_reference: "Above nominal reference", not_assessed: "Not assessed",
  };
  return `${assessment.production_vs_nominal_percent}% · ${labels[assessment.status]}`;
}

export function manualRelevanceLabel(score: number) {
  if (score >= 0.7) return "High relevance";
  if (score >= 0.55) return "Relevant match";
  return "Possible match";
}
