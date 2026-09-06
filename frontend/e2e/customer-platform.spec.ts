import { expect, Page, test } from "@playwright/test";

const machine = {
  machine_id: "MCH-0001",
  serial_number: "15610",
  model_code: "TS-EURO-PK-TWIN-CHUTE-D",
  model_description: "Rotary closing machine",
  plant_location: "Novara Plant 1 - Bottling Line 3",
  configuration_profile: "Twin chute / 20 heads",
};

const manualResult = {
  citation: { source: "manual", file: "MCH-0001-manual.pdf", page: 12, section: "Safety" },
  title: "Safety instructions",
  excerpt: "Disconnect the machine before maintenance.",
  highlights: ["maintenance"],
  relevance: 0.86,
  similarity: 0.86,
};

async function mockApi(page: Page, unavailableMachines = false) {
  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (request.method() === "POST" && url.pathname === "/auth/login") {
      return json({ access_token: "test-token", token_type: "bearer", user: { user_id: "USR-001", company_id: "CMP-001", visibility: "company" } });
    }
    if (url.pathname === "/machines") {
      return unavailableMachines ? route.abort("failed") : json([machine]);
    }
    if (url.pathname === "/machines/lookup/MCH-0001") {
      return json({ ...machine, company_id: "CMP-001", company_name: "Valgrande Bevande S.p.A.", model_id: "MDL-100", operational_context: "Twin chute configuration" });
    }
    if (url.pathname.endsWith("/alarms")) {
      return json([{ alarm_id: "ALM-001", timestamp: "2026-08-05T09:30:00Z", alarm_code: "A10", severity: "High", alarm_status: "Open" }]);
    }
    if (url.pathname.endsWith("/telemetry")) {
      return json([{ timestamp: "2026-08-05T09:30:00Z", operational_status: "Running", production_rate_bph: 40000, uptime_percentage: 98.2, alarm_count: 1, temperature_c: 24, energy_kwh: 12.4, health_note: null }]);
    }
    if (url.pathname.endsWith("/maintenance-tickets")) {
      return json([{ ticket_id: "TCK-001", alarm_id: "ALM-001", ticket_type: "Corrective", ticket_status: "Open", priority: "High", created_date: "2026-08-05T09:00:00Z", owner_role: "Service" }]);
    }
    if (url.pathname.endsWith("/maintenance-observation")) {
      return json({ machine_id: "MCH-0001", observed_productive_hours: 42.5, first_snapshot: "2026-08-05T00:00:00Z", last_snapshot: "2026-08-05T23:00:00Z", snapshot_count: 24, documented_threshold_hours: [40, 500], reached_threshold_hours: [40], next_threshold_hours: 500, scope_note: "Observed window only." });
    }
    if (url.pathname.endsWith("/manuals/search")) {
      return json([manualResult]);
    }
    if (url.pathname.includes("/manuals/files/")) {
      return route.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.4\n% mock manual" });
    }
    if (request.method() === "POST" && url.pathname === "/chat") {
      return json({ answer: "Disconnect the machine before maintenance.", agent: ["manuals"], sources: [manualResult], data: null });
    }
    return json({ detail: `Unexpected mocked request: ${request.method()} ${url.pathname}` }, 404);
  });
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User ID").fill("USR-001");
  await page.getByLabel("Password").fill("development-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/home$/);
}

test("a user can sign in, view a machine and sign out", async ({ page }) => {
  await mockApi(page);
  await signIn(page);

  await expect(page.getByRole("heading", { name: "Connected Machines" })).toBeVisible();
  await page.getByRole("button", { name: /MCH-0001/ }).click();
  await expect(page).toHaveURL(/\/machines\/MCH-0001$/);
  await expect(page.getByRole("heading", { name: "Machine operational status" })).toBeVisible();
  await expect(page.getByText("Recent telemetry")).toBeVisible();
  await expect(page.getByText("A10")).toBeVisible();

  await page.getByRole("button", { name: "Sign Out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("You have been signed out.")).toBeVisible();
});

test("manual search and chat render trusted manual sources", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await page.getByRole("button", { name: /MCH-0001/ }).click();

  await page.getByLabel("Search the manual").fill("safety maintenance");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Safety instructions").first()).toBeVisible();
  const manualPopup = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Open at page 12" }).click();
  const popup = await manualPopup;
  await expect(popup).toHaveURL(/^blob:/);
  await expect(page.getByText("Opening MCH-0001-manual.pdf at page 12.")).toBeVisible();

  await page.getByRole("button", { name: "Open AROL Assistant" }).click();
  await page.getByLabel("Question for AROL Assistant").fill("How do I perform maintenance safely?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Disconnect the machine before maintenance.").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Open source" })).toBeVisible();
});

test("the QR scanner can be opened and closed without changing the current page", async ({ page }) => {
  await mockApi(page);
  await signIn(page);

  await page.getByRole("button", { name: "Scan QR code" }).click();
  await expect(page.getByRole("heading", { name: "Scan the QR code" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("heading", { name: "Connected Machines" })).toBeVisible();
});

test("a network failure is shown as an actionable error", async ({ page }) => {
  await mockApi(page, true);
  await page.goto("/login");
  await page.evaluate(() => localStorage.setItem("arol.access-token", "test-token"));
  await page.goto("/home");

  await expect(page.getByText("Network error. Check your connection and try again.").first()).toBeVisible();
});
