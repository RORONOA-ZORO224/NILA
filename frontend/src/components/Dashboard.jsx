import React, { useState } from "react";

const MODE_COLORS = { ACT: "#22c55e", ASK: "#eab308", PAUSE: "#ef4444" };

function timeAgo(iso) {
  const diff = Math.floor((Date.now() - new Date(iso + "Z").getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function Dashboard({ actions, onUndo }) {
  const [expanded, setExpanded] = useState(null);

  if (!actions.length) {
    return (
      <div className="dashboard">
        <div className="dashboard__header">
          <h2>Action Dashboard</h2>
          <p className="dashboard__subtitle">Every decision ARIA makes — logged here in real time.</p>
        </div>
        <div className="dashboard__empty">No actions yet. Send ARIA a command.</div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="dashboard__header">
        <h2>Action Dashboard</h2>
        <p className="dashboard__subtitle">{actions.length} actions logged</p>
      </div>
      <div className="dashboard__log">
        {actions.map((a) => (
          <div key={a.id} className={`log-entry ${a.status === "undone" ? "log-entry--undone" : ""}`}>
            <div className="log-entry__row" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
              <span
                className="log-entry__badge"
                style={{ background: MODE_COLORS[a.mode] || "#6366f1", color: "#000" }}
              >
                {a.mode}
              </span>
              <span className="log-entry__action">{a.action}</span>
              <span className="log-entry__summary">{a.summary}</span>
              <span className="log-entry__time">{timeAgo(a.executed_at)}</span>
              {a.status === "undone" && <span className="log-entry__undone-tag">undone</span>}
              <span className="log-entry__expand">{expanded === a.id ? "▲" : "▼"}</span>
            </div>
            {expanded === a.id && (
              <div className="log-entry__detail">
                <div><strong>Reasoning:</strong> {a.reasoning || "—"}</div>
                {a.payload && (
                  <pre className="log-entry__payload">
                    {JSON.stringify(JSON.parse(a.payload || "{}"), null, 2)}
                  </pre>
                )}
                {a.status !== "undone" && onUndo && (
                  <button className="btn btn--undo-small" onClick={() => onUndo(a.id)}>
                    ↩ Undo this action
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}