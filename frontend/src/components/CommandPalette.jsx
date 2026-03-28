import React, { useState, useEffect, useRef } from "react";

const COMMANDS = [
  // Email
  { id: "email_late",    group: "Email",    icon: "✉️", label: "Tell someone I'll be late",              template: "Email {recipient} I'll be 15 minutes late" },
  { id: "email_follow",  group: "Email",    icon: "✉️", label: "Send a follow-up email",                 template: "Send a follow-up email to {recipient} about {topic}" },
  { id: "email_apology", group: "Email",    icon: "✉️", label: "Apologise for something",                template: "Email {recipient} apologising about {topic}" },
  { id: "email_later",   group: "Email",    icon: "📅", label: "Schedule an email for later",            template: "Email {recipient} about {topic} tomorrow at 9am" },

  // Calendar
  { id: "cal_meet",      group: "Calendar", icon: "📅", label: "Schedule a meeting",                     template: "Schedule a meeting with {recipient} tomorrow at 3PM" },
  { id: "cal_standup",   group: "Calendar", icon: "📅", label: "Book daily standup",                     template: "Create a daily standup event tomorrow at 9:30am" },

  // Slack
  { id: "slack_update",  group: "Slack",    icon: "💬", label: "Post team update to Slack",              template: "Post our deployment update to the #general channel" },
  { id: "slack_standby", group: "Slack",    icon: "💬", label: "Tell team I'm AFK",                      template: "Message #general that I'm away from keyboard until 3PM" },

  // LinkedIn
  { id: "li_search",     group: "LinkedIn", icon: "🔍", label: "Find HR contacts at a company",          template: "Find HR contacts at {company} in Chennai" },

  // Notion
  { id: "notion_note",   group: "Notion",   icon: "📝", label: "Create a meeting notes page",            template: "Create a Notion page for today's meeting notes about {topic}" },
  { id: "notion_retro",  group: "Notion",   icon: "📝", label: "Start sprint retrospective",             template: "Create a Notion page for this week's sprint retrospective" },

  // Chain
  { id: "chain_onboard", group: "Chain",    icon: "⛓️", label: "Full onboarding workflow",               template: "Email {recipient} the welcome info, create an onboarding event next Monday, and post in #general that they joined" },
  { id: "chain_outreach", group: "Chain",   icon: "⛓️", label: "LinkedIn → Email outreach chain",        template: "Find HR contacts at {company} then email the top contact introducing myself" },
];

function highlight(text, query) {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: "rgba(99,102,241,0.35)", color: "inherit", borderRadius: 2 }}>
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export default function CommandPalette({ onSelect, onClose }) {
  const [query,    setQuery]    = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef   = useRef(null);
  const listRef    = useRef(null);

  const filtered = query
    ? COMMANDS.filter((c) =>
        c.label.toLowerCase().includes(query.toLowerCase()) ||
        c.group.toLowerCase().includes(query.toLowerCase()) ||
        c.template.toLowerCase().includes(query.toLowerCase())
      )
    : COMMANDS;

  // Group filtered results
  const groups = filtered.reduce((acc, cmd) => {
    if (!acc[cmd.group]) acc[cmd.group] = [];
    acc[cmd.group].push(cmd);
    return acc;
  }, {});

  const flat = filtered; // for keyboard index

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Reset selected when query changes
  useEffect(() => { setSelected(0); }, [query]);

  // Scroll selected into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${selected}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flat[selected]) pick(flat[selected]);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  const pick = (cmd) => {
    onSelect(cmd.template);
    onClose();
  };

  return (
    /* Backdrop */
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 500,
        background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        paddingTop: 80,
      }}
      onClick={onClose}
    >
      {/* Palette box */}
      <div
        style={{
          width: "100%", maxWidth: 560,
          background: "var(--bg-card)",
          border: "1px solid var(--border-mid)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          boxShadow: "0 24px 64px rgba(0,0,0,0.7)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "12px 16px",
          borderBottom: "1px solid var(--border)",
        }}>
          <span style={{ fontSize: 14, color: "var(--text-muted)", flexShrink: 0 }}>⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search commands…"
            style={{
              flex: 1, background: "none", border: "none",
              color: "var(--text)", fontSize: 14, outline: "none",
              fontFamily: "inherit",
            }}
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 12 }}
            >
              ✕
            </button>
          )}
          <kbd style={{
            fontSize: 10, padding: "2px 6px",
            border: "1px solid var(--border-mid)",
            borderRadius: 4, color: "var(--text-muted)",
            fontFamily: "inherit",
          }}>
            esc
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          style={{ maxHeight: 380, overflowY: "auto", padding: "6px 0" }}
        >
          {flat.length === 0 && (
            <div style={{ color: "var(--text-muted)", textAlign: "center", padding: "24px 0", fontSize: 13 }}>
              No commands match "{query}"
            </div>
          )}

          {Object.entries(groups).map(([group, cmds]) => (
            <div key={group}>
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: "0.8px",
                color: "var(--text-muted)", padding: "6px 16px 3px",
                textTransform: "uppercase",
              }}>
                {group}
              </div>
              {cmds.map((cmd) => {
                const idx = flat.indexOf(cmd);
                const isActive = idx === selected;
                return (
                  <div
                    key={cmd.id}
                    data-idx={idx}
                    onClick={() => pick(cmd)}
                    onMouseEnter={() => setSelected(idx)}
                    style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "8px 16px", cursor: "pointer",
                      background: isActive ? "var(--accent-dim)" : "transparent",
                      borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                      transition: "background 0.08s",
                    }}
                  >
                    <span style={{ fontSize: 14, flexShrink: 0, lineHeight: 1 }}>{cmd.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {highlight(cmd.label, query)}
                      </div>
                      <div style={{
                        fontSize: 11, color: "var(--text-muted)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        marginTop: 1,
                      }}>
                        {highlight(cmd.template, query)}
                      </div>
                    </div>
                    {isActive && (
                      <kbd style={{
                        fontSize: 10, padding: "1px 5px",
                        border: "1px solid var(--border-mid)",
                        borderRadius: 3, color: "var(--text-muted)",
                        flexShrink: 0,
                      }}>
                        ↵
                      </kbd>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", gap: 16, padding: "8px 16px",
          borderTop: "1px solid var(--border)",
          fontSize: 11, color: "var(--text-muted)",
        }}>
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span>esc close</span>
          <span style={{ marginLeft: "auto" }}>{flat.length} commands</span>
        </div>
      </div>
    </div>
  );
}