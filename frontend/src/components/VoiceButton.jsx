import React, { useState, useRef } from "react";

export default function VoiceButton({ onTranscript }) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  const supported = "webkitSpeechRecognition" in window || "SpeechRecognition" in window;

  const toggle = () => {
    if (!supported) return;

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      onTranscript(transcript);
    };

    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);

    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  };

  if (!supported) {
    return <div className="voice-unsupported" title="Voice not supported in this browser">🎤</div>;
  }

  return (
    <button
      className={`voice-btn ${listening ? "voice-btn--active" : ""}`}
      onClick={toggle}
      title={listening ? "Stop listening" : "Start voice input"}
    >
      {listening ? "🔴" : "🎤"}
    </button>
  );
}