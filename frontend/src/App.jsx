import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import ChatBubbles    from "./components/ChatBubbles";
import VoiceButton    from "./components/VoiceButton";
import ActionCard     from "./components/ActionCard";
import Dashboard      from "./components/Dashboard";
import MemoryPanel    from "./components/MemoryPanel";
import AnalyticsPanel from "./components/AnalyticsPanel";
import UndoToast      from "./components/UndoToast";
import CommandChips   from "./components/CommandChips";
import CommandPalette from "./components/CommandPalette";
import "./App.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const WS_URL = API.replace("http://", "ws://").replace("https://", "wss://");

const PANELS = {
  chat:      { icon: "💬", label: "Chat" },
  dashboard: { icon: "📊", label: "Dashboard" },
  analytics: { icon: "📈", label: "Analytics" },
  memory:    { icon: "🧠", label: "Memory" },
};

export default function App() {
  const [messages,      setMessages]      = useState([
    { role: "aria", text: "Hi! I'm ARIA. Tell me what to do — or press ⌘K to browse commands.", mode: null },
  ]);
  const [input,         setInput]         = useState("");
  const [loading,       setLoading]       = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [undoStack,     setUndoStack]     = useState([]);
  const [undoWindow,    setUndoWindow]    = useState(30);
  const [actionLog,     setActionLog]     = useState([]);
  const [memory,        setMemory]        = useState({});
  const [activePanel,   setActivePanel]   = useState("chat");
  const [connected,     setConnected]     = useState(false);
  const [paletteOpen,   setPaletteOpen]   = useState(false);

  const wsRef      = useRef(null);
  const historyRef = useRef([]);
  const historyIdx = useRef(-1);
  const inputRef   = useRef(null);

  // ── WebSocket with auto-reconnect ────────────────────────────────────────
  useEffect(() => {
    let ws, reconnectTimer;
    const connect = () => {
      ws = new WebSocket(`${WS_URL}/ws/dashboard`);
      wsRef.current = ws;
      ws.onopen  = () => setConnected(true);
      ws.onclose = () => { setConnected(false); reconnectTimer = setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
      ws.onmessage = ({ data }) => {
        const msg = JSON.parse(data);
        if (msg.type === "action_executed") { fetchActionLog(); fetchMemory(); }
        if (msg.type === "action_undone")   { setUndoStack((p) => p.filter((u) => u.action_id !== msg.action_id)); fetchActionLog(); }
      };
    };
    connect();
    return () => { clearTimeout(reconnectTimer); ws?.close(); };
  }, []);

  // ── Poll undo timers ─────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/undo/active`);
        setUndoStack(data.active || []);
        if (data.window_seconds) setUndoWindow(data.window_seconds);
      } catch {}
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Global keyboard shortcuts ────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      // ⌘K or Ctrl+K — open command palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
      // Escape — close palette
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => { fetchActionLog(); fetchMemory(); }, []);

  const fetchActionLog = async () => {
    try { const { data } = await axios.get(`${API}/actions`); setActionLog(data.actions || []); } catch {}
  };
  const fetchMemory = async () => {
    try { const { data } = await axios.get(`${API}/memory`); setMemory(data.preferences || {}); } catch {}
  };

  // ── Send message ─────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (text, confirm = false, sessionId = null) => {
    if (!text.trim() || loading) return;

    if (!confirm) {
      historyRef.current = [text, ...historyRef.current.slice(0, 49)];
      historyIdx.current = -1;
      setMessages((p) => [...p, { role: "user", text, mode: null }]);
    }

    setInput("");
    setLoading(true);

    try {
      const body = { message: text, confirm };
      if (confirm && sessionId) body.session_id = sessionId;

      const { data } = await axios.post(`${API}/chat`, body);

      setMessages((p) => [...p, {
        role:      "aria",
        text:      data.response,
        mode:      data.mode,
        result:    data.result,
        intent:    data.intent,
        action_id: data.action_id,
      }]);

      if (data.mode === "PAUSE") {
        setPendingAction({ intent: data.intent, preview: data.response, original: text, session_id: data.session_id });
      } else {
        setPendingAction(null);
      }

      if (data.undo_available) {
        const { data: ud } = await axios.get(`${API}/undo/active`);
        setUndoStack(ud.active || []);
      }

      fetchActionLog(); fetchMemory();
    } catch {
      setMessages((p) => [...p, { role: "aria", text: "⚠️ Something went wrong. Is the backend running?", mode: "error" }]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  const handleConfirm = () => {
    if (pendingAction) { sendMessage(pendingAction.original, true, pendingAction.session_id); setPendingAction(null); }
  };

  const handleUndo = async (action_id) => {
    try {
      await axios.post(`${API}/undo`, { action_id });
      setUndoStack((p) => p.filter((u) => u.action_id !== action_id));
      setMessages((p) => [...p, { role: "aria", text: "↩️ Action undone successfully.", mode: "system" }]);
      fetchActionLog();
    } catch (err) {
      alert(err.response?.data?.detail || "Undo failed — window may have expired.");
    }
  };

  const handleDeleteMemory = async (key) => {
    try { await axios.delete(`${API}/memory/${key}`); fetchMemory(); } catch {}
  };

  // ── Input keyboard handling ──────────────────────────────────────────────
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); return; }
    if (e.key === "ArrowUp" && !input) {
      e.preventDefault();
      const next = Math.min(historyIdx.current + 1, historyRef.current.length - 1);
      historyIdx.current = next;
      if (historyRef.current[next] !== undefined) setInput(historyRef.current[next]);
      return;
    }
    if (e.key === "ArrowDown" && !input) {
      e.preventDefault();
      const next = Math.max(historyIdx.current - 1, -1);
      historyIdx.current = next;
      setInput(next === -1 ? "" : historyRef.current[next]);
    }
  };

  const panelCounts = {
    dashboard: actionLog.length,
    memory:    Object.keys(memory).length,
    analytics: "",
  };

  return (
    <div className="app">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">A</div>
        <nav className="sidebar-nav">
          {Object.entries(PANELS).map(([key, { icon, label }]) => (
            <button
              key={key}
              className={`sidebar-btn ${activePanel === key ? "sidebar-btn--active" : ""}`}
              onClick={() => setActivePanel(key)}
            >
              {icon}
              <span className="tooltip">
                {label}{panelCounts[key] ? ` · ${panelCounts[key]}` : ""}
              </span>
            </button>
          ))}
        </nav>

        {/* ⌘K button at bottom of sidebar */}
        <div style={{ marginTop: "auto", paddingBottom: 8 }}>
          <button
            className="sidebar-btn"
            onClick={() => setPaletteOpen(true)}
            title="Command palette (⌘K)"
          >
            ⌘
            <span className="tooltip">Command palette  ⌘K</span>
          </button>
        </div>
      </aside>

      <div className="main-content">
        {/* ── Top bar ── */}
        <div className="topbar">
          <div>
            <div className="topbar-title">ARIA — {PANELS[activePanel].label}</div>
            <div className="topbar-sub">Autonomous Real-world Intent Agent</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* ⌘K hint */}
            <button
              onClick={() => setPaletteOpen(true)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "var(--bg-card)", border: "1px solid var(--border-mid)",
                borderRadius: 6, padding: "4px 10px",
                fontSize: 12, color: "var(--text-muted)", cursor: "pointer",
              }}
            >
              <span>⌘K</span>
              <span>Commands</span>
            </button>
            <div className="topbar-status">
              <div className="status-dot" style={{ background: connected ? "var(--green)" : "var(--red)" }} />
              {connected ? "Live" : "Reconnecting…"}
            </div>
          </div>
        </div>

        <div className="panel">
          {/* ── Chat ── */}
          {activePanel === "chat" && (
            <div className="chat-panel">
              <ChatBubbles messages={messages} loading={loading} />

              {pendingAction && (
                <ActionCard
                  preview={pendingAction.preview}
                  intent={pendingAction.intent}
                  onConfirm={handleConfirm}
                  onCancel={() => setPendingAction(null)}
                />
              )}

              <CommandChips onSelect={(cmd) => sendMessage(cmd)} disabled={loading} />

              <div className="input-area">
                <textarea
                  ref={inputRef}
                  className="input-box"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder='Try "Email Ravi at 3pm tomorrow" or press ⌘K for commands'
                  rows={2}
                  disabled={loading}
                />
                <div className="input-actions">
                  <VoiceButton onTranscript={(t) => sendMessage(t)} />
                  <button
                    className="btn--icon btn--icon--send"
                    onClick={() => sendMessage(input)}
                    disabled={loading || !input.trim()}
                    title="Send (Enter)"
                  >
                    {loading ? "⏳" : "↑"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activePanel === "dashboard" && (
            <Dashboard actions={actionLog} onUndo={handleUndo} onRefresh={fetchActionLog} />
          )}

          {activePanel === "analytics" && <AnalyticsPanel />}

          {activePanel === "memory" && (
            <MemoryPanel memory={memory} onRefresh={fetchMemory} onDelete={handleDeleteMemory} />
          )}
        </div>
      </div>

      {/* ── Undo toast stack ── */}
      <div className="undo-stack">
        {undoStack.map((entry) => (
          <UndoToast
            key={entry.action_id}
            entry={entry}
            windowSeconds={undoWindow}
            onUndo={() => handleUndo(entry.action_id)}
          />
        ))}
      </div>

      {/* ── Command palette (portal-style overlay) ── */}
      {paletteOpen && (
        <CommandPalette
          onSelect={(template) => {
            setInput(template);
            setActivePanel("chat");
            setTimeout(() => inputRef.current?.focus(), 50);
          }}
          onClose={() => setPaletteOpen(false)}
        />
      )}
    </div>
  );
}