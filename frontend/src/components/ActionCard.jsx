import React from "react";

export default function ActionCard({ preview, intent, onConfirm, onCancel }) {
  return (
    <div className="action-card">
      <div className="action-card__header">
        <span className="action-card__badge">⚠ PAUSE — Confirm Required</span>
        <span className="action-card__risk">Risk: {intent?.risk_level?.toUpperCase()}</span>
      </div>
      <div className="action-card__preview">{preview}</div>
      {intent?.reasoning && (
        <div className="action-card__reason">Why paused: {intent.reasoning}</div>
      )}
      <div className="action-card__buttons">
        <button className="btn btn--confirm" onClick={onConfirm}>
          ✓ Confirm
        </button>
        <button className="btn btn--cancel" onClick={onCancel}>
          ✗ Cancel
        </button>
      </div>
    </div>
  );
}