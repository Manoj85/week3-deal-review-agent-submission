import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import type {
  ActionBody,
  Proposal,
  Revision,
  SavedReview,
  Summary,
} from "./types";
import PacketView, { Badge, humanize } from "./components/PacketView";
import HumanReview from "./components/HumanReview";
import sample from "./sample.json";

function download(record: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(record, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
export default function App() {
  const [reviews, setReviews] = useState<Summary[]>([]);
  const [review, setReview] = useState<SavedReview | null>(null);
  const [history, setHistory] = useState<Revision[]>([]);
  const [version, setVersion] = useState<number | null>(null);
  const [screen, setScreen] = useState<"new" | "review">("new");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState("Connecting");
  const [reloadEpoch, setReloadEpoch] = useState(0);
  const [draft, setDraft] = useState<Proposal>({
    document_id: "",
    submitted_on: new Date().toLocaleDateString("en-CA"),
    proposal_text: "",
  });
  const [recoverId, setRecoverId] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api.health(), api.list()])
      .then(([health, list]) => {
        if (active) {
          setMode(health.mode);
          setReviews(list);
        }
      })
      .catch((e) => {
        if (active) {
          setError(String(e.message));
          setMode("Unavailable");
        }
      });
    return () => {
      active = false;
    };
  }, []);
  async function load(id: string) {
    const record = await api.get(id);
    setReview(record);
    setReloadEpoch((value) => value + 1);
    setScreen("review");
    setVersion(null);
    setHistory([]);
    try {
      setHistory(await api.history(id));
    } catch {
      setNotice(
        "Current record loaded; revision history could not be fetched. Reload to try again.",
      );
    }
    return record;
  }
  async function failure(e: unknown) {
    if (e instanceof ApiError && e.reviewId) {
      setRecoverId(e.reviewId);
      try {
        await load(e.reviewId);
        setReviews(await api.list());
      } catch {
        /* retain the saved ID for manual recovery */
      }
    }
    setError(
      e instanceof Error
        ? e.message
        : "The operation failed. Reload saved reviews before retrying.",
    );
  }
  async function open(id: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await load(id);
    } catch (e) {
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const [health, list] = await Promise.all([api.health(), api.list()]);
      setMode(health.mode);
      setReviews(list);
      if (screen === "review" && review) await load(review.review_id);
    } catch (e) {
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    setRecoverId("");
    try {
      const record = await api.create(draft);
      setReview(record);
      setVersion(null);
      setHistory([]);
      setScreen("review");
      setNotice(
        "Analysis saved. The workflow is now waiting for a human action.",
      );
      try {
        setReviews(await api.list());
        setHistory(await api.history(record.review_id));
      } catch {
        setNotice("Review saved. Refresh to update the sidebar and history.");
      }
    } catch (e) {
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function action(body: ActionBody, retry: boolean) {
    if (!review) return false;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const record = await api.action(review.review_id, body, retry);
      setReview(record);
      setVersion(null);
      setNotice("Human action saved.");
      try {
        setReviews(await api.list());
        setHistory(await api.history(record.review_id));
      } catch {
        setNotice("Action saved. Refresh to update the sidebar and history.");
      }
      return true;
    } catch (e) {
      await failure(e);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const snapshot =
    version === null ? null : history.find((h) => h.revision === version);
  const packet = snapshot?.packet ?? review?.packet;
  const historical = !!snapshot && snapshot.revision !== review?.revision;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="brand-mark">L</span>ledger
          <span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">LOAN OPERATIONS WORKSPACE</div>
        <button
          className="new-button"
          disabled={busy}
          onClick={() => {
            setScreen("new");
            setError("");
            setNotice("");
          }}
        >
          ＋ New review
        </button>
        <div className="sidebar-heading">
          <span>SAVED REVIEWS</span>
          <button
            className="icon-button"
            aria-label="Refresh saved reviews"
            onClick={refresh}
            disabled={busy}
          >
            ↻
          </button>
        </div>
        <nav aria-label="Saved reviews">
          {reviews.length ? (
            reviews.map((item) => (
              <button
                disabled={busy}
                className={`review-link ${screen === "review" && review?.review_id === item.review_id ? "selected" : ""}`}
                key={item.review_id}
                onClick={() => open(item.review_id)}
              >
                <strong>{item.document_id}</strong>
                <span>{humanize(item.lifecycle_status)}</span>
                <small>
                  Revision {item.revision} <span>↗</span>
                </small>
              </button>
            ))
          ) : (
            <p className="sidebar-empty">
              Your saved reviews will appear here.
            </p>
          )}
        </nav>
        <div className="sidebar-footer">
          <span
            className={`connection-dot ${mode === "Connecting" ? "waiting" : ""}`}
          />
          <span>
            {mode === "nebius"
              ? "Nebius mode"
              : mode === "Connecting"
                ? "Checking API"
                : mode === "Unavailable"
                  ? "API unavailable"
                  : "Offline sample parser"}
            <small>Local workspace · Policy v0.1</small>
          </span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            WORKSPACE <span className="separator">/</span> Small-business
            lending
          </span>
          <span className="demo-pill">FICTIONAL POLICY · CLASSROOM DEMO</span>
        </header>
        <div className="content">
          <div role="status" aria-live="polite">
            {busy && (
              <div className="progress">
                <span className="spinner" /> Working on your request. Analysis
                can take a minute; keep this page open.
              </div>
            )}
            {notice && <div className="notice">{notice}</div>}
          </div>
          {error && (
            <div className="error" role="alert">
              <strong>Request needs attention</strong>
              <p>{error}</p>
              {recoverId && (
                <button disabled={busy} onClick={() => open(recoverId)}>
                  Open saved review {recoverId}
                </button>
              )}
              {error.includes("Revision changed") && (
                <p>Reload the record before submitting another action.</p>
              )}
            </div>
          )}
          {screen === "new" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PROPOSAL IN. CLARITY OUT.</div>
                  <h1>A clearer first review.</h1>
                  <p>
                    Turn a small-business proposal into a traceable review
                    packet.
                    <br />
                    Three specialists check the facts. You make the next move.
                  </p>
                </div>
                <div className="heading-stamp">
                  01<span>INITIAL REVIEW</span>
                </div>
              </div>
              <div className="new-layout">
                <section className="panel proposal-panel">
                  <div className="section-heading">
                    <div>
                      <h2>Start with the proposal</h2>
                      <p>Paste the complete source text below.</p>
                    </div>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => setDraft({ ...sample })}
                    >
                      Load bakery sample
                    </button>
                  </div>
                  <form onSubmit={create}>
                    <fieldset disabled={busy}>
                      <div className="form-row">
                        <label>
                          Document ID
                          <input
                            required
                            maxLength={100}
                            pattern="[A-Za-z0-9_-]+"
                            placeholder="e.g. LOAN-2026-001"
                            value={draft.document_id}
                            onChange={(e) =>
                              setDraft({
                                ...draft,
                                document_id: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Submission date
                          <input
                            type="date"
                            required
                            value={draft.submitted_on}
                            onChange={(e) =>
                              setDraft({
                                ...draft,
                                submitted_on: e.target.value,
                              })
                            }
                          />
                        </label>
                      </div>
                      <label>
                        Proposal text
                        <textarea
                          aria-label="Proposal text"
                          required
                          minLength={100}
                          maxLength={100000}
                          rows={16}
                          placeholder="Include the business, requested financing, annual financial figures, people and supporting documents…"
                          value={draft.proposal_text}
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              proposal_text: e.target.value,
                            })
                          }
                        />
                      </label>
                      <div className="input-footer">
                        <span>
                          {draft.proposal_text.length.toLocaleString()} /
                          100,000 characters
                        </span>
                        <span>At least 100 characters</span>
                      </div>
                    </fieldset>
                    <div className="submit-row">
                      <p>
                        In Nebius mode, analysis uses credits.
                        <br />
                        The result is saved locally for human review.
                      </p>
                      <button
                        className="primary"
                        disabled={
                          busy || draft.proposal_text.trim().length < 100
                        }
                      >
                        {busy ? "Analyzing…" : "Build review packet →"}
                      </button>
                    </div>
                  </form>
                </section>
                <aside className="intro-rail">
                  <div className="eyebrow">ONE PACKET. THREE PERSPECTIVES.</div>
                  {[
                    [
                      "01",
                      "Extract the facts",
                      "Identify financial terms, people and exact source quotes.",
                    ],
                    [
                      "02",
                      "Check six policy rules",
                      "Calculate the ratios and flag missing or conflicting information.",
                    ],
                    [
                      "03",
                      "Prepare the handoff",
                      "Explain exceptions and ask focused clarification questions.",
                    ],
                  ].map(([n, title, copy]) => (
                    <div className="intro-step" key={n}>
                      <span>{n}</span>
                      <div>
                        <h3>{title}</h3>
                        <p>{copy}</p>
                      </div>
                    </div>
                  ))}
                  <div className="human-note">
                    <span>↳</span>
                    <h3>A human stays in the loop.</h3>
                    <p>
                      This assistant prepares the initial review. It never
                      approves or denies a loan.
                    </p>
                  </div>
                </aside>
              </div>
            </>
          ) : (
            review && (
              <>
                <div className="page-heading compact">
                  <div>
                    <div className="eyebrow">
                      SAVED REVIEW · REVISION {review.revision}
                    </div>
                    <h1>{review.current_request.document_id}</h1>
                    <p className="review-identifier">{review.review_id}</p>
                  </div>
                  <Badge value={review.lifecycle_status} />
                </div>
                <div className="review-toolbar">
                  <label>
                    Packet version
                    <select
                      aria-label="Packet version"
                      disabled={busy}
                      value={version ?? "current"}
                      onChange={(e) =>
                        setVersion(
                          e.target.value === "current"
                            ? null
                            : Number(e.target.value),
                        )
                      }
                    >
                      <option value="current">
                        Current revision {review.revision}
                      </option>
                      {history
                        .filter((h) => h.revision !== review.revision)
                        .map((h) => (
                          <option key={h.revision} value={h.revision}>
                            Revision {h.revision} · archived
                          </option>
                        ))}
                    </select>
                  </label>
                  <div>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => open(review.review_id)}
                    >
                      Reload record
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        download(
                          historical ? snapshot : review,
                          `${review.current_request.document_id}-revision-${historical ? version : review.revision}.json`,
                        )
                      }
                    >
                      Download JSON ↓
                    </button>
                  </div>
                </div>
                {historical && (
                  <div className="notice">
                    Viewing archived revision {version}. Return to the current
                    revision to take action.
                  </div>
                )}
                {packet ? (
                  <PacketView key={packet.run_id} packet={packet} />
                ) : (
                  <section className="panel">
                    <h2>No accepted packet for this revision</h2>
                    <p>
                      The saved workflow may still be processing or require a
                      failed-stage retry. Earlier accepted versions remain
                      available above.
                    </p>
                  </section>
                )}
                {!historical && (
                  <HumanReview
                    key={`${review.review_id}:${review.revision}:${review.lifecycle_status}:${reloadEpoch}`}
                    review={review}
                    busy={busy}
                    onAction={action}
                  />
                )}
                <section className="panel audit">
                  <h2>Review activity</h2>
                  {review.actions.length ? (
                    review.actions.map((a) => (
                      <div className="audit-row" key={a.action_id}>
                        <div>
                          <strong>{humanize(a.action)}</strong>
                          <small>
                            {a.actor} ·{" "}
                            {new Date(a.submitted_at).toLocaleString()} ·
                            revision {a.resulting_revision}
                          </small>
                        </div>
                        <p>{a.note}</p>
                      </div>
                    ))
                  ) : (
                    <p>No human actions recorded yet.</p>
                  )}
                </section>
              </>
            )
          )}
          <footer className="page-footer">
            Ledger / Initial loan review{" "}
            <span>Evidence first. Human judgment always.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
