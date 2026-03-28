import React, { useState, useRef } from "react";

export default function VoiceButton({ onTranscript }) {
  const [listening, setListening] = useState(false);
  const [error,     setError]     = useState("");
  const recognitionRef = useRef(null);

  const supported =
    "webkitSpeechRecognition" in window || "SpeechRecognition" in window;

  const toggle = () => {
    if (!supported) return;
    setError("");

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      onTranscript(transcript);
      setListening(false);
    };

    rec.onend = () => setListening(false);

    // FIX: Provide meaningful error feedback instead of silent failure
    rec.onerror = (e) => {
      setListening(false);
      const messages = {
        "not-allowed":    "Microphone access denied. Check browser permissions.",
        "no-speech":      "No speech detected. Try again.",
        "network":        "Network error during recognition.",
        "audio-capture":  "No microphone found.",
      };
      setError(messages[e.error] || `Voice error: ${e.error}`);
      setTimeout(() => setError(""), 4000);
    };

    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  };

  if (!supported) {
    return (
      <button className="btn--icon" title="Voice not supported in this browser" disabled>
        🎤
      </button>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        className={`btn--icon ${listening ? "btn--icon--active" : ""}`}
        onClick={toggle}
        title={listening ? "Stop listening" : "Voice input"}
      >
        {listening ? "🔴" : "🎤"}
      </button>
      {error && (
        <div style={{
          position: "absolute",
          bottom: "calc(100% + 8px)",
          right: 0,
          background: "var(--bg-card)",
          border: "1px solid rgba(239,68,68,0.4)",
          borderRadius: "var(--radius)",
          padding: "6px 10px",
          fontSize: 11,
          color: "var(--red)",
          whiteSpace: "nowrap",
          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
          zIndex: 100,
        }}>
          {error}
        </div>
      )}
    </div>
  );
}