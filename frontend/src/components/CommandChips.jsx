import React from "react";

const QUICK_COMMANDS = [
  "Email Ravi I'll be 15 minutes late",
  "Schedule a meeting tomorrow at 3PM",
  "Find HR contacts at TCS",
  "Post a standup update in #general",
  "Create a Notion note about today's goals",
];

export default function CommandChips({ onSelect, disabled }) {
  return (
    <div className="chips">
      {QUICK_COMMANDS.map((cmd) => (
        <button
          key={cmd}
          className="chip"
          onClick={() => !disabled && onSelect(cmd)}
          disabled={disabled}
        >
          {cmd}
        </button>
      ))}
    </div>
  );
}