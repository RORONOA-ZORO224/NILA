import React from "react";

export default function UndoToast({ entry, onUndo }) {
  const pct = Math.round((entry.seconds_remaining / 30) * 100);
  const urgent = entry.seconds_remaining <= 8;

  return (
    <div className={`undo-toast ${urgent ? "undo-toast--urgent" : ""}`}>
      <div className="undo-toast__content">
        <span className="undo-toast__icon">↩️</span>
        <div className="undo-toast__text">
          <span className="undo-toast__summary">{entry.summary}</span>
          <span className="undo-toast__timer">{entry.seconds_remaining}s to undo</span>
        </div>
        <button className="btn btn--undo" onClick={onUndo}>Undo</button>
      </div>
      <div className="undo-toast__bar">
        <div
          className={`undo-toast__progress ${urgent ? "undo-toast__progress--urgent" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}