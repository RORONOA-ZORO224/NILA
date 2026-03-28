import React from "react";

export default function MemoryPanel({ memory, onRefresh }) {
  const entries = Object.entries(memory);

  return (
    <div className="memory-panel">
      <div className="memory-panel__header">
        <h2>🧠 What ARIA knows about you</h2>
        <p className="memory-panel__subtitle">
          Learned automatically from your commands. Delete anything you don't want remembered.
        </p>
        <button className="btn btn--secondary" onClick={onRefresh}>↻ Refresh</button>
      </div>

      {entries.length === 0 ? (
        <div className="memory-panel__empty">
          No preferences learned yet. Send a few commands and ARIA will start remembering.
        </div>
      ) : (
        <div className="memory-panel__grid">
          {entries.map(([key, value]) => (
            <div key={key} className="memory-card">
              <div className="memory-card__key">{key.replace(/_/g, " ")}</div>
              <div className="memory-card__value">
                {typeof value === "object" ? JSON.stringify(value) : String(value)}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="memory-panel__note">
        These preferences are injected into every ARIA prompt to reduce clarifying questions.
      </p>
    </div>
  );
}