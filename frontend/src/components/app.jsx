import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import ChatBubbles from "./components/ChatBubbles";
import VoiceButton from "./components/VoiceButton";
import ActionCard from "./components/ActionCard";
import Dashboard from "./components/Dashboard";
import MemoryPanel from "./components/MemoryPanel";
import UndoToast from "./components/UndoToast";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function App() {
  const [messages, setMessages] = useState([
    { role: "aria", text: "Hi! I'm ARIA. Tell me what to do — I'll handle it.", mode: null },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);  // For PAUSE mode
  const [undoStack, setUndoStack] = useState([]);            // Active undo entries
  const [actionLog, setActionLog] = useState([]);            // Dashboard log
  const [memory, setMemory] = useState({});                  // Persona panel
  const [activePanel, setActivePanel] = useState("chat");    // chat | dashboard | memory
  const wsRef = useRef(null);

  // ── WebSocket: subscribe to live action events ──────────────────────────
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/dashboard`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "action_executed") {
        fetchActionLog();
        fetchMemory();
      }
      if (msg.type === "action_undone") {
        setUndoStack((prev) => prev.filter((u) => u.action_id !== msg.action_id));
        fetchActionLog();
      }
    };

    return () => ws.close();
  }, []);

  // ── Poll undo timers every second ───────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/undo/active`);
        setUndoStack(data.active || []);
      } catch {
        // Silently ignore if backend not ready
      }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // ── Initial data load ────────────────────────────────────────────────────
  useEffect(() => {
    fetchActionLog();
    fetchMemory();
  }, []);

  const fetchActionLog = async () => {
    try {
      const { data } = await axios.get(`${API}/actions`);
      setActionLog(data.actions || []);
    } catch {}
  };

  const fetchMemory = async () => {
    try {
      const { data } = await axios.get(`${API}/memory`);
      setMemory(data.preferences || {});
    } catch {}
  };

  // ── Send message to ARIA ─────────────────────────────────────────────────
  const sendMessage = async (text, confirm = false) => {
    if (!text.trim() || loading) return;

    const userMsg = { role: "user", text, mode: null };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const { data } = await axios.post(`${API}/chat`, {
        message: text,
        confirm,
      });

      const ariaMsg = {
        role: "aria",
        text: data.response,
        mode: data.mode,
        result: data.result,
        intent: data.intent,
        action_id: data.action_id,
      };
      setMessages((prev) => [...prev, ariaMsg]);

      if (data.mode === "PAUSE") {
        setPendingAction({ intent: data.intent, preview: data.response, original: text });
      } else {
        setPendingAction(null);
      }

      if (data.undo_available) {
        const { data: undoData } = await axios.get(`${API}/undo/active`);
        setUndoStack(undoData.active || []);
      }

      fetchActionLog();
      fetchMemory();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "aria", text: "⚠️ Something went wrong. Is the backend running?", mode: "error" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    if (pendingAction) {
      sendMessage(pendingAction.original, true);
      setPendingAction(null);
    }
  };

  const handleUndo = async (action_id) => {
    try {
      await axios.post(`${API}/undo`, { action_id });
      setUndoStack((prev) => prev.filter((u) => u.action_id !== action_id));
      setMessages((prev) => [
        ...prev,
        { role: "aria", text: "↩️ Action undone successfully.", mode: "system" },
      ]);
      fetchActionLog();
    } catch (err) {
      alert(err.response?.data?.detail || "Undo failed — window may have expired.");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-brand">
          <span className="aria-logo">ARIA</span>
          <span className="aria-tagline">Autonomous Real-world Intent Agent</span>
        </div>
        <nav className="header-nav">
          {["chat", "dashboard", "memory"].map((panel) => (
            <button
              key={panel}
              className={`nav-btn ${activePanel === panel ? "nav-btn--active" : ""}`}
              onClick={() => setActivePanel(panel)}
            >
              {{ chat: "💬 Chat", dashboard: "📊 Dashboard", memory: "🧠 Memory" }[panel]}
            </button>
          ))}
        </nav>
      </header>

      <main className="main">
        {/* ── Chat Panel ── */}
        {activePanel === "chat" && (
          <div className="chat-panel">
            <ChatBubbles messages={messages} loading={loading} />

            {/* PAUSE confirmation card */}
            {pendingAction && (
              <ActionCard
                preview={pendingAction.preview}
                intent={pendingAction.intent}
                onConfirm={handleConfirm}
                onCancel={() => setPendingAction(null)}
              />
            )}

            {/* Input row */}
            <div className="input-row">
              <VoiceButton onTranscript={(text) => sendMessage(text)} />
              <textarea
                className="input-box"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder='Try: "Email Ravi I\'ll be 15 mins late" or "Schedule a meeting tomorrow at 3PM"'
                rows={2}
                disabled={loading}
              />
              <button
                className="send-btn"
                onClick={() => sendMessage(input)}
                disabled={loading || !input.trim()}
              >
                {loading ? "⏳" : "Send"}
              </button>
            </div>
          </div>
        )}

        {activePanel === "dashboard" && (
          <Dashboard actions={actionLog} onUndo={handleUndo} />
        )}

        {activePanel === "memory" && (
          <MemoryPanel memory={memory} onRefresh={fetchMemory} />
        )}
      </main>

      {/* ── Undo Toast Stack ── */}
      <div className="undo-stack">
        {undoStack.map((entry) => (
          <UndoToast
            key={entry.action_id}
            entry={entry}
            onUndo={() => handleUndo(entry.action_id)}
          />
        ))}
      </div>
    </div>
  );
}