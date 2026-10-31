import { useState } from "react";
import type { FormEvent } from "react";
import type { ActionBody, ActionKind, SavedReview } from "../types";
interface Props {
  review: SavedReview;
  busy: boolean;
  onAction: (body: ActionBody, retry: boolean) => Promise<boolean>;
}
export default function HumanReview({ review, busy, onAction }: Props) {
  const [actor, setActor] = useState("");
  const [note, setNote] = useState("");
  const [source, setSource] = useState(review.current_request.proposal_text);
  const [kind, setKind] = useState<ActionKind>(
    review.lifecycle_status === "AWAITING_CLARIFICATION"
      ? "clarify"
      : review.lifecycle_status === "ERROR_NEEDS_REVIEW"
        ? "retry"
        : "mark_reviewed",
  );
  const [pending, setPending] = useState<{
    body: ActionBody;
    retry: boolean;
  } | null>(null);
  if (review.lifecycle_status === "REVIEWED")
    return (
      <section className="panel completed">
        <span className="eyebrow">HUMAN REVIEW RECORDED</span>
        <h2>Reviewed by {review.reviewed_by}</h2>
        <p>
          The packet and policy exceptions remain preserved. This records review
          of the packet; it is not a credit decision.
        </p>
      </section>
    );
  if (review.lifecycle_status === "PROCESSING")
    return (
      <section className="panel">
        <h2>Processing</h2>
        <p>Refresh this record after the active request finishes.</p>
      </section>
    );
  const options: ActionKind[] =
    review.lifecycle_status === "AWAITING_CLARIFICATION"
      ? ["clarify"]
      : review.lifecycle_status === "ERROR_NEEDS_REVIEW"
        ? ["retry"]
        : ["mark_reviewed", "request_revision"];
  const labels = {
    clarify: "Submit corrected proposal",
    mark_reviewed: "Mark packet reviewed",
    request_revision: "Request changes",
    retry: "Retry failed stage",
  };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const operation = pending ?? {
      body: {
        action_id: crypto.randomUUID(),
        expected_revision: review.revision,
        actor: actor.trim(),
        note: note.trim(),
        ...(kind === "retry" ? {} : { action: kind }),
        ...(kind === "clarify" ? { replacement_proposal_text: source } : {}),
      } as ActionBody,
      retry: kind === "retry",
    };
    setPending(operation);
    if (await onAction(operation.body, operation.retry)) setPending(null);
  }
  return (
    <section className="panel human-panel">
      <span className="eyebrow">YOUR NEXT STEP</span>
      <h2>
        {review.lifecycle_status === "AWAITING_CLARIFICATION"
          ? "Resolve the missing information"
          : review.lifecycle_status === "ERROR_NEEDS_REVIEW"
            ? "Resume the saved analysis"
            : "Complete the human review"}
      </h2>
      {review.pending_interrupt?.reviewer_request && (
        <p className="question">
          Reviewer request: {review.pending_interrupt.reviewer_request}
        </p>
      )}
      {!!review.packet?.clarification_questions.length && (
        <ul>
          {review.packet.clarification_questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      )}
      {review.last_error && (
        <p className="question">
          {review.last_error.stage}: {review.last_error.message}
        </p>
      )}
      <form onSubmit={submit}>
        <fieldset disabled={busy || !!pending}>
          {options.length > 1 && (
            <label>
              Action
              <select
                aria-label="Action"
                value={kind}
                onChange={(e) => setKind(e.target.value as ActionKind)}
              >
                {options.map((o) => (
                  <option key={o} value={o}>
                    {labels[o]}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="form-row">
            <label>
              Your name
              <input
                required
                minLength={2}
                maxLength={100}
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </label>
            <label>
              Review note
              <input
                required
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
          </div>
          {kind === "clarify" && (
            <label>
              Complete corrected proposal
              <textarea
                aria-label="Complete corrected proposal"
                required
                minLength={100}
                maxLength={100000}
                rows={12}
                value={source}
                onChange={(e) => setSource(e.target.value)}
              />
              <small>
                Edit the full proposal above. Submitting creates revision{" "}
                {review.revision + 1} and runs the agents again.
              </small>
            </label>
          )}
        </fieldset>
        <p className="muted">
          {kind === "clarify" || kind === "retry"
            ? "This action can use Nebius credits."
            : "This action does not call the model."}{" "}
          Reviewer names are self-reported in this local demo.
        </p>
        {pending && !busy && (
          <p className="question">
            The result was not confirmed. Retry sends the exact same action ID
            safely. Reload the record if its revision or state changed.
          </p>
        )}
        <button
          className="primary"
          disabled={
            busy || (!pending && (actor.trim().length < 2 || !note.trim()))
          }
        >
          {busy ? "Saving…" : pending ? "Retry same action" : labels[kind]}
        </button>
      </form>
    </section>
  );
}
