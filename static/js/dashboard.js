async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

const LEVEL_LABELS = { low: "Low Stress", medium: "Medium Stress", high: "High Stress" };

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

let trendChart = null;

async function loadSummary() {
  try {
    const s = await fetchJSON("/api/dashboard-summary");
    setText("statCurrent", s.current_stress_label || "No predictions yet");
    setText("statTotal", s.today_total ?? 0);
    setText(
      "statBreakdown",
      `Low ${s.low_count} · Medium ${s.medium_count} · High ${s.high_count}`
    );
    setText("statAvgHrv", s.average_hrv != null ? s.average_hrv : "—");
    setText("statAvgHrvSub", s.average_hrv != null ? s.average_hrv_metric : "Calculated from today's records");
    setText("statTrend", s.stress_trend || "—");
  } catch (e) {
    console.error(e);
  }
}

async function loadTrend() {
  const empty = document.getElementById("trendEmpty");
  const canvas = document.getElementById("trendChart");
  try {
    const data = await fetchJSON("/api/trend");
    const points = data.points || [];

    if (!points.length) {
      empty?.classList.remove("is-hidden");
      if (canvas) canvas.style.display = "none";
      return;
    }
    empty?.classList.add("is-hidden");
    if (canvas) canvas.style.display = "block";

    const labels = points.map((p) => p.time);
    const values = points.map((p) => p.level_order);
    const colorFor = (v) => (v >= 2.5 ? "#EF4444" : v >= 1.5 ? "#F59E0B" : "#22C55E");

    if (trendChart) trendChart.destroy();
    const ctx = canvas.getContext("2d");
    trendChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Stress level",
            data: values,
            borderColor: "#7C5CFF",
            backgroundColor: "rgba(124,92,255,.15)",
            pointBackgroundColor: values.map(colorFor),
            pointRadius: 5,
            tension: 0.35,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) => {
                const p = points[item.dataIndex];
                return LEVEL_LABELS[p.stress_level] || p.stress_level;
              },
            },
          },
        },
        scales: {
          y: {
            min: 0.5,
            max: 3.5,
            ticks: {
              stepSize: 1,
              color: "rgba(255,255,255,.7)",
              callback: (v) => ({ 1: "Low", 2: "Medium", 3: "High" }[v] || ""),
            },
            grid: { color: "rgba(255,255,255,.08)" },
          },
          x: {
            ticks: { color: "rgba(255,255,255,.7)" },
            grid: { color: "rgba(255,255,255,.05)" },
          },
        },
      },
    });
  } catch (e) {
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadSummary();
  loadTrend();
});
