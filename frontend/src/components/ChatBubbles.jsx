import React, { useEffect, useRef } from "react";

const MODE_META = {
  ACT:    { label: "ACT",    cls: "mode-tag--ACT" },
  ASK:    { label: "ASK",    cls: "mode-tag--ASK" },
  PAUSE:  { label: "PAUSE",  cls: "mode-tag--PAUSE" },
  system: { label: "SYSTEM", cls: "mode-tag--system" },
  error:  { label: "ERROR",  cls: "mode-tag--error" },
};

export default function ChatBubbles({ messages, loading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="messages">
      {messages.map((msg, i) => (
        <div key={i} className={`msg-row ${msg.role === "user" ? "msg-row--user" : ""}`}>
          <div className={`avatar ${msg.role === "user" ? "avatar--user" : "avatar--aria"}`}>
            {msg.role === "user" ? "U" : "A"}
          </div>

          <div className={`bubble ${msg.role === "user" ? "bubble--user" : "bubble--aria"}`}>
            {msg.mode && MODE_META[msg.mode] && (
              <div className={`mode-tag ${MODE_META[msg.mode].cls}`}>
                <div className="mode-tag-dot" />
                {MODE_META[msg.mode].label}
              </div>
            )}
            <div className="bubble-text">{msg.text}</div>

            {msg.intent?.reasoning && (
              <div className="bubble-reasoning">
                💭 {msg.intent.reasoning}
              </div>
            )}
          </div>
        </div>
      ))}

      {loading && (
        <div className="msg-row">
          <div className="avatar avatar--aria">A</div>
          <div className="bubble bubble--aria">
            <div className="typing">
              <span /><span /><span />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}