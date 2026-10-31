import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const sample = JSON.parse(
  readFileSync(new URL("../src/sample.json", import.meta.url), "utf8"),
);

test("real API: create, inspect evidence, request correction, resume, archive, review and reopen", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.locator(".sidebar-footer")).toContainText(
    "Offline sample parser",
    { timeout: 15000 },
  );
  await page.getByRole("button", { name: "Load bakery sample" }).click();
  await page.getByLabel("Document ID", { exact: true }).fill("UI-E2E-BAKERY");
  await page.getByRole("button", { name: "Build review packet" }).click();
  await expect(
    page.getByRole("heading", { name: "UI-E2E-BAKERY", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("exceptions for review", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".rule-card")).toHaveCount(6);
  await expect(
    page
      .locator(".rule-card")
      .filter({ hasText: "P04" })
      .getByText("flag", { exact: true }),
  ).toBeVisible();
  await page
    .locator(".rule-card")
    .filter({ hasText: "P04" })
    .getByText("View supporting evidence")
    .click();
  await expect(
    page
      .locator(".rule-card")
      .filter({ hasText: "P04" })
      .locator("blockquote")
      .first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Agent activity" }).click();
  await expect(
    page.getByRole("heading", { name: "How the packet was produced" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Policy review", exact: true }).click();
  await page
    .getByLabel("Action", { exact: true })
    .selectOption("request_revision");
  await page.getByLabel("Your name").fill("UI Reviewer");
  await page
    .getByLabel("Review note")
    .fill("Please confirm the complete debt-service source.");
  await page
    .getByRole("button", { name: "Request changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Resolve the missing information" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Reviewer request: Please confirm the complete debt-service source.",
    ),
  ).toBeVisible();
  await page.getByLabel("Your name").fill("UI Analyst");
  await page
    .getByLabel("Review note")
    .fill("Reconfirmed the complete source supplied by the applicant.");
  await page
    .getByLabel("Complete corrected proposal")
    .fill(sample.proposal_text);
  await page
    .getByRole("button", { name: "Submit corrected proposal", exact: true })
    .click();
  await expect(page.getByLabel("Packet version")).toHaveValue("current");
  await expect(
    page.getByText("SAVED REVIEW · REVISION 2", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Packet version").selectOption("1");
  await expect(
    page.getByText("Viewing archived revision 1.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mark packet reviewed", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Packet version").selectOption("current");
  await page.getByLabel("Your name").fill("UI Reviewer");
  await page
    .getByLabel("Review note")
    .fill("Reviewed exceptions; no lending decision recorded.");
  await page
    .getByRole("button", { name: "Mark packet reviewed", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reviewed by UI Reviewer" }),
  ).toBeVisible();
  await expect(page.locator(".audit-row")).toHaveCount(4);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON" }).click();
  expect((await download).suggestedFilename()).toBe(
    "UI-E2E-BAKERY-revision-2.json",
  );
  await page.reload();
  await page.getByRole("button", { name: /UI-E2E-BAKERY/ }).click();
  await expect(
    page.getByRole("heading", { name: "Reviewed by UI Reviewer" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../work/ui-review-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "UI-E2E-BAKERY", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../work/ui-review-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("connection error retains form and does not silently resubmit", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Load bakery sample" }).click();
  await page.route("**/api/reviews", (route) => route.abort());
  await page.getByRole("button", { name: "Build review packet" }).click();
  await expect(page.getByRole("alert")).toContainText("Cannot reach the API");
  await expect(page.getByLabel("Proposal text", { exact: true })).toHaveValue(
    sample.proposal_text,
  );
});

test("failed human action reuses its action ID on explicit retry", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Load bakery sample" }).click();
  await page.getByLabel("Document ID", { exact: true }).fill("UI-RETRY");
  await page.getByRole("button", { name: "Build review packet" }).click();
  await expect(
    page.getByRole("heading", { name: "UI-RETRY", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Your name").fill("Reviewer");
  await page.getByLabel("Review note").fill("Reviewed the packet.");
  const payloads: string[] = [];
  await page.route("**/api/reviews/*/actions", async (route) => {
    payloads.push(route.request().postData()!);
    if (payloads.length === 1) await route.abort();
    else await route.continue();
  });
  await page
    .getByRole("button", { name: "Mark packet reviewed", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry same action" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry same action" }).click();
  await expect(
    page.getByRole("heading", { name: "Reviewed by Reviewer" }),
  ).toBeVisible();
  expect(payloads).toHaveLength(2);
  expect(payloads[0]).toEqual(payloads[1]);
});

test("new review fits a narrow screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".sidebar-footer")).toContainText(
    "Offline sample parser",
  );
  await page.screenshot({ path: "../work/ui-new-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "A clearer first review." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "../work/ui-new-mobile.png", fullPage: true });
});
