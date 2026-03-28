import React, { useEffect, useRef } from "react";

const MODE_COLORS = {
  ACT: { bg: "#22c55e", label: "ACT" },
  ASK: { bg: "#eab308", label: "ASK" },
  PAUSE: { bg: "#ef4444", label: "PAUSE" },
  error: { bg: "#ef4444", label: "ERROR" },
  system: { bg: "#6366f1", label: "SYSTEM" },
};

export default function ChatBubbles({ messages, loading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="bubbles-container">
      {messages.map((msg, i) => (
        <div key={i} className={`bubble-row ${msg.role === "user" ? "bubble-row--user" : ""}`}>
          <div className={`bubble-avatar ${msg.role === "user" ? "bubble-avatar--user" : ""}`}>
            {msg.role === "user" ? "U" : "A"}
          </div>
          <div className={`bubble ${msg.role === "user" ? "bubble--user" : "bubble--aria"}`}>
            {msg.mode && MODE_COLORS[msg.mode] && (
              <span
                className="mode-badge"
                style={{ background: MODE_COLORS[msg.mode].bg }}
              >
                {MODE_COLORS[msg.mode].label}
              </span>
            )}
            <div className="bubble-text">{msg.text}</div>
            {msg.intent?.reasoning && (
              <div className="bubble-reasoning">💭 {msg.intent.reasoning}</div>
            )}
          </div>
        </div>
      ))}

      {loading && (
        <div className="bubble-row">
          <div className="bubble-avatar">A</div>
          <div className="bubble bubble--aria">
            <div className="typing-indicator">
              <span /><span /><span />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}