import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const ACTION_COLORS = {
  send_email:      "#6366f1",
  create_event:    "#22c55e",
  search_linkedin: "#3b82f6",
  slack_message:   "#f59e0b",
  notion_create:   "#ec4899",
  chain:           "#8b5cf6",
  schedule_email:  "#06b6d4",
  other:           "#6b7280",
};

function StatCard({ label, value, sub }) {
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius)",
      padding: "12px 16px",
    }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.7px", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 600, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// Load Chart.js from CDN once
function loadChartJS() {
  return new Promise((resolve) => {
    if (window.Chart) return resolve(window.Chart);
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => resolve(window.Chart);
    document.head.appendChild(s);
  });
}

export default function AnalyticsPanel() {
  const [data,      setData]      = useState(null);
  const [scheduled, setScheduled] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const lineRef = useRef(null);
  const barRef  = useRef(null);
  const lineChartInst = useRef(null);
  const barChartInst  = useRef(null);

  const fetchData = async () => {
    try {
      const [a, s] = await Promise.all([
        axios.get(`${API}/analytics`),
        axios.get(`${API}/scheduled`),
      ]);
      setData(a.data);
      setScheduled(s.data.jobs || []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  useEffect(() => {
    if (!data) return;
    let alive = true;

    loadChartJS().then((Chart) => {
      if (!alive) return;

      const gridColor = "rgba(255,255,255,0.05)";
      const tickColor = "#6b6b85";

      // Hourly line chart
      lineChartInst.current?.destroy();
      if (lineRef.current) {
        lineChartInst.current = new Chart(lineRef.current, {
          type: "line",
          data: {
            labels:   data.hourly.map((h) => h.hour),
            datasets: [{
              data:            data.hourly.map((h) => h.count),
              borderColor:     "#6366f1",
              backgroundColor: "rgba(99,102,241,0.08)",
              borderWidth:     2,
              pointRadius:     2,
              pointBackgroundColor: "#6366f1",
              fill:     true,
              tension:  0.4,
            }],
          },
          options: {
            responsive:          true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: {
                ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } },
                grid:  { color: gridColor },
              },
              y: {
                ticks: { color: tickColor, font: { size: 10 }, stepSize: 1 },
                grid:  { color: gridColor },
                beginAtZero: true,
              },
            },
          },
        });
      }

      // By-type horizontal bar chart
      barChartInst.current?.destroy();
      if (barRef.current && data.by_type.length > 0) {
        barChartInst.current = new Chart(barRef.current, {
          type: "bar",
          data: {
            labels:   data.by_type.map((d) => d.action.replace(/_/g, " ")),
            datasets: [{
              data:            data.by_type.map((d) => d.count),
              backgroundColor: data.by_type.map((d) => ACTION_COLORS[d.action] || "#6b7280"),
              borderRadius:    4,
              borderSkipped:   false,
            }],
          },
          options: {
            indexAxis:           "y",
            responsive:          true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: {
                ticks: { color: tickColor, font: { size: 10 }, stepSize: 1 },
                grid:  { color: gridColor },
                beginAtZero: true,
              },
              y: {
                ticks: { color: tickColor, font: { size: 10 }, autoSkip: false },
                grid:  { display: false },
              },
            },
          },
        });
      }
    });

    return () => {
      alive = false;
      lineChartInst.current?.destroy();
      barChartInst.current?.destroy();
    };
  }, [data]);

  const cancelJob = async (jobId) => {
    try {
      await axios.delete(`${API}/scheduled/${jobId}`);
      fetchData();
    } catch (e) {
      alert(e.response?.data?.detail || "Could not cancel.");
    }
  };

  if (loading) {
    return <div style={{ color: "var(--text-muted)", padding: "60px 0", textAlign: "center" }}>Loading analytics…</div>;
  }

  const { totals, by_mode } = data || {};
  const byMode   = Object.fromEntries((by_mode || []).map((m) => [m.mode, m.count]));
  const barH     = Math.max((data?.by_type?.length || 0) * 38 + 20, 80);

  return (
    <div style={{ overflowY: "auto", height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 10 }}>
        <StatCard label="Total actions" value={totals?.total ?? 0} />
        <StatCard label="ACT rate"      value={`${totals?.act_rate ?? 0}%`} sub="immediately executed" />
        <StatCard label="Undone"        value={totals?.undone ?? 0} sub="via 30s window" />
        <StatCard label="Scheduled"     value={scheduled.filter((j) => j.status === "pending").length} sub="pending jobs" />
      </div>

      {/* Mode pills */}
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { mode: "ACT",   color: "#22c55e" },
          { mode: "ASK",   color: "#f59e0b" },
          { mode: "PAUSE", color: "#ef4444" },
        ].map(({ mode, color }) => (
          <div key={mode} style={{
            display: "flex", alignItems: "center", gap: 6,
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 20, padding: "4px 12px", fontSize: 12,
          }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
            <span style={{ color: "var(--text-muted)" }}>{mode}</span>
            <span style={{ fontWeight: 600 }}>{byMode[mode] || 0}</span>
          </div>
        ))}
        <button
          onClick={fetchData}
          style={{
            marginLeft: "auto", background: "none", border: "1px solid var(--border)",
            borderRadius: 20, padding: "4px 12px", fontSize: 12,
            color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Hourly line chart */}
      <div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Actions — last 24 hours</div>
        <div style={{ position: "relative", height: 160 }}>
          <canvas ref={lineRef} />
        </div>
      </div>

      {/* By-type bar chart */}
      {(data?.by_type?.length || 0) > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>By action type</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px", marginBottom: 10 }}>
            {data.by_type.map((d) => (
              <span key={d.action} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)" }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: ACTION_COLORS[d.action] || "#6b7280", display: "inline-block" }} />
                {d.action.replace(/_/g, " ")} ({d.count})
              </span>
            ))}
          </div>
          <div style={{ position: "relative", height: barH }}>
            <canvas ref={barRef} />
          </div>
        </div>
      )}

      {/* Scheduled jobs */}
      {scheduled.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Scheduled jobs</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {scheduled.map((job) => (
              <div key={job.id} style={{
                display: "flex", alignItems: "center", gap: 10,
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: "var(--radius)", padding: "10px 14px",
              }}>
                <div style={{
                  fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, flexShrink: 0,
                  background: job.status === "pending" ? "rgba(6,182,212,0.12)" : "rgba(107,114,128,0.12)",
                  color:      job.status === "pending" ? "#06b6d4"             : "var(--text-muted)",
                }}>
                  {job.status.toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {job.description}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                    {new Date(job.run_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
                  </div>
                </div>
                {job.status === "pending" && (
                  <button
                    onClick={() => cancelJob(job.id)}
                    style={{
                      background: "none", border: "1px solid rgba(239,68,68,0.3)",
                      borderRadius: 6, color: "var(--red)", fontSize: 11,
                      padding: "3px 10px", cursor: "pointer", flexShrink: 0,
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {scheduled.length === 0 && (data?.by_type?.length || 0) === 0 && (
        <div style={{ color: "var(--text-muted)", textAlign: "center", padding: "20px 0", fontSize: 13 }}>
          No data yet — send ARIA some commands to see analytics here.
        </div>
      )}
    </div>
  );
}