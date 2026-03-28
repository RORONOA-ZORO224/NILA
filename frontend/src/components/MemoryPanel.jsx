import React from "react";

export default function MemoryPanel({ memory, onRefresh, onDelete }) {
  const entries = Object.entries(memory);

  return (
    <div className="memory-panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">🧠 What ARIA knows about you</div>
          <div className="panel-sub">Learned from your commands. Delete anything you don't want remembered.</div>
        </div>
        <button className="btn btn--ghost" style={{ fontSize: 12, padding: "5px 12px" }} onClick={onRefresh}>
          ↻ Refresh
        </button>
      </div>

      {entries.length === 0 ? (
        <div className="memory-empty">
          No preferences learned yet.<br />
          Send a few commands and ARIA will start remembering patterns.
        </div>
      ) : (
        <div className="memory-grid">
          {entries.map(([key, value]) => (
            <div key={key} className="memory-card">
              <div className="memory-key">{key.replace(/_/g, " ")}</div>
              <div className="memory-value">
                {typeof value === "object" ? JSON.stringify(value) : String(value)}
              </div>
              <button
                className="memory-del"
                onClick={() => onDelete(key)}
              >
                × forget this
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="panel-sub" style={{ marginTop: 8 }}>
        These preferences are injected into every ARIA prompt to reduce clarifying questions.
      </div>
    </div>
  );
}