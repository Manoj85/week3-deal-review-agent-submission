import { useState } from "react";
import type { Packet } from "../types";
export const humanize = (value: string) =>
  value.toLowerCase().replaceAll("_", " ");
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value.toLowerCase()}`}>
      {humanize(value)}
    </span>
  );
}
export default function PacketView({ packet }: { packet: Packet }) {
  const [tab, setTab] = useState("Policy review");
  const tabs = ["Policy review", "Evidence & source", "Agent activity"];
  return (
    <>
      <section className="summary-card">
        <div className="eyebrow">REVIEW BRIEF</div>
        <h2>{humanize(packet.workflow_status)}</h2>
        <p className="preserve">{packet.summary}</p>
        <div className="metrics">
          <span>
            <strong>
              {packet.rules.filter((r) => r.status === "FLAG").length}
            </strong>{" "}
            exceptions
          </span>
          <span>
            <strong>
              {packet.rules.filter((r) => r.status === "UNKNOWN").length}
            </strong>{" "}
            unknown
          </span>
          <span>
            <strong>{packet.model_calls}</strong> model calls
          </span>
          <span>
            <strong>{(packet.elapsed_ms / 1000).toFixed(1)}s</strong> elapsed
          </span>
        </div>
      </section>
      <div className="tabs" role="tablist" aria-label="Review packet">
        {tabs.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={tab}>
        {tab === "Policy review" && (
          <div className="rule-grid">
            {packet.rules.map((rule) => (
              <article className="rule-card" key={rule.rule_id}>
                <div className="row">
                  <span className="rule-id">{rule.rule_id}</span>
                  <Badge value={rule.status} />
                </div>
                <h3>{rule.explanation}</h3>
                {rule.calculation && (
                  <p className="calculation">{rule.calculation}</p>
                )}
                {rule.clarification && (
                  <p className="question">{rule.clarification}</p>
                )}
                <details>
                  <summary>View supporting evidence</summary>
                  {rule.field_refs.map((ref) => (
                    <div className="fact" key={ref}>
                      <strong>{humanize(ref)}</strong>
                      <p>{packet.terms[ref]?.value ?? "Not established"}</p>
                      {packet.terms[ref]?.evidence.map((e, i) => (
                        <blockquote key={i}>
                          {e.quote}
                          <cite>
                            {e.document_id} · {e.section} · characters {e.start}
                            –{e.end}
                          </cite>
                        </blockquote>
                      ))}
                    </div>
                  ))}
                </details>
              </article>
            ))}
          </div>
        )}
        {tab === "Evidence & source" && (
          <section className="panel">
            <h2>Extracted facts</h2>
            {Object.entries(packet.terms).map(([key, fact]) => (
              <details key={key} className="fact">
                <summary>
                  {humanize(key)}{" "}
                  <span className="fact-value">
                    {fact.value ?? humanize(fact.state)}
                  </span>
                </summary>
                {fact.evidence.length ? (
                  fact.evidence.map((e, i) => (
                    <blockquote key={i}>
                      {e.quote}
                      <cite>
                        {e.section} · characters {e.start}–{e.end}
                      </cite>
                    </blockquote>
                  ))
                ) : (
                  <p>No supporting source span was established.</p>
                )}
              </details>
            ))}
            <h2>Proposal source</h2>
            <pre className="source">{packet.normalized_source}</pre>
          </section>
        )}
        {tab === "Agent activity" && (
          <section className="panel">
            <h2>How the packet was produced</h2>
            {packet.agent_runs.map((agent, i) => (
              <details className="agent" key={i}>
                <summary>
                  <span className="step-number">0{i + 1}</span>
                  <strong>{humanize(agent.agent)}</strong>
                  <span>
                    {agent.model_calls} calls · {agent.execution}
                  </span>
                </summary>
                <p>Tokens: {JSON.stringify(agent.usage)}</p>
                <pre className="source">
                  {JSON.stringify(agent.tool_calls, null, 2)}
                </pre>
              </details>
            ))}
            <h3>Practical limits</h3>
            <ul>
              {packet.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  );
}
