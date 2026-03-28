import React from "react";

export default function UndoToast({ entry, windowSeconds = 30, onUndo }) {
  // FIX: Use windowSeconds from API response, not hardcoded 30
  const pct     = Math.round((entry.seconds_remaining / windowSeconds) * 100);
  const urgent  = entry.seconds_remaining <= 8;

  return (
    <div className={`undo-toast ${urgent ? "undo-toast--urgent" : ""}`}>
      <div className="undo-toast__body">
        <span className="undo-toast__icon">↩️</span>
        <div className="undo-toast__text">
          <span className="undo-toast__summary">{entry.summary}</span>
          <span className="undo-toast__timer">{entry.seconds_remaining}s to undo</span>
        </div>
        <button
          className="btn btn--ghost"
          style={{ fontSize: 12, padding: "4px 10px" }}
          onClick={onUndo}
        >
          Undo
        </button>
      </div>
      <div className="undo-toast__bar">
        <div
          className="undo-toast__progress"
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
      </div>
    </div>
  );
}