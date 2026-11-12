import { test, expect, Page } from "@playwright/test";

// Each test uses its own token (= its own user) and job id, so tests are independent.
async function login(page: Page, token: string) {
  await page.goto("/");
  await page.getByLabel("Access token").fill(token);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
}
async function analyseAndOpen(page: Page, job: string) {
  await page.getByLabel("Job id").fill(job);
  await page.getByRole("button", { name: "Analyse" }).click();
  await page.getByRole("link", { name: /Review proposal/ }).click();
  await expect(page.getByRole("heading", { name: "Cover letter" })).toBeVisible();
}

test("1. onboarding: sign in, see empty inbox, then analyse a job", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await login(page, "tok-1");
  await expect(page.getByText("No jobs yet")).toBeVisible();          // clear empty state
  await page.getByLabel("Job id").fill("j1");
  await page.getByRole("button", { name: "Analyse" }).click();
  await expect(page.getByTestId("job-card")).toHaveCount(1);
  await expect(page.getByText("bid", { exact: true })).toBeVisible();
});

test("2. approving a proposal submits it", async ({ page }) => {
  await login(page, "tok-2");
  await analyseAndOpen(page, "j2");
  await expect(page.getByText(/Connects cost/)).toBeVisible();        // dry-run preview is shown
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Status: submitted/)).toBeVisible();
});

test("3. rejecting needs a reason and sends nothing", async ({ page }) => {
  await login(page, "tok-3");
  await analyseAndOpen(page, "j3");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  const confirm = page.getByRole("button", { name: "Reject", exact: true });
  await expect(confirm).toBeDisabled();                                // reason required
  await page.getByLabel("Rejection reason").fill("too generic");
  await confirm.click();
  await expect(page.getByText(/Status: rejected/)).toBeVisible();
});

test("4. editing the draft then approving submits the edited version", async ({ page }) => {
  await login(page, "tok-4");
  await analyseAndOpen(page, "j4");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Edit cover letter").fill("I built a RAG chatbot on pgvector. Happy to share details.");
  await page.getByRole("button", { name: "Approve edited version" }).click();
  await expect(page.getByText(/Status: submitted/)).toBeVisible();
  await page.reload();                                                  // refresh never loses state
  await expect(page.getByText(/Status: submitted/)).toBeVisible();
});

test("5. degraded mode: banner appears when the API is unreachable", async ({ page }) => {
  await login(page, "tok-5");
  await page.route("**/api/health", (r) => r.abort());
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toBeVisible();
  await expect(page.getByTestId("degraded-banner")).toContainText(/pending approvals are safe/);
});

test("6. claim shows its evidence on hover and keyboard focus; unsupported claim removed", async ({ page }) => {
  await login(page, "tok-6");
  await analyseAndOpen(page, "j6");
  const claim = page.getByTestId("claim").first();
  await claim.hover();
  await expect(page.getByRole("tooltip")).toContainText("pgvector");
  await page.mouse.move(0, 0);
  await claim.focus();                                                  // keyboard accessible
  await expect(page.getByRole("tooltip")).toBeVisible();
  await expect(page.getByTestId("letter")).not.toContainText("moon");
});

test("7. page refresh keeps a pending approval", async ({ page }) => {
  await login(page, "tok-7");
  await analyseAndOpen(page, "j7");
  await page.reload();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeVisible();
});

test("8. messages: interview request shows calendar slots; approving sends the reply", async ({ page }) => {
  await login(page, "tok-8");
  await page.goto("/messages");
  await page.getByLabel("Conversation id").fill("m1");
  await page.getByRole("button", { name: "Draft reply" }).click();
  await page.getByRole("link", { name: /Review reply/ }).click();
  await expect(page.getByTestId("intent")).toHaveText("interview_request");
  await expect(page.getByText("Interview slots (from your calendar)")).toBeVisible();
  await expect(page.getByText(/Connects cost/)).toHaveCount(0);        // messages cost nothing; no price shown
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Status: sent/)).toBeVisible();
});

test("9. messages: a scam message is flagged and no reply is drafted", async ({ page }) => {
  await login(page, "tok-9");
  await page.goto("/messages");
  await page.getByLabel("Conversation id").fill("m2");
  await page.getByRole("button", { name: "Draft reply" }).click();
  await page.getByRole("link", { name: "Open" }).click();
  await expect(page.getByTestId("intent")).toHaveText("scam_signal");  // rules override the naive LLM
  await expect(page.getByText(/Flagged as a possible scam/)).toBeVisible();
  await expect(page.getByTestId("reply")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
});
