async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function todayISO() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function selectedDate() {
  const input = document.getElementById("reportDate");
  return (input && input.value) || todayISO();
}

async function loadSummary() {
  try {
    const s = await fetchJSON(`/api/daily-summary?date=${selectedDate()}`);
    setText("repTotal", s.total_predictions ?? 0);
    setText("repFrequent", s.most_frequent_state || "—");
    setText("repTrend", s.overall_trend || "—");
    setText("repScore", s.stress_score != null ? `${s.stress_score}/100` : "—/100");
  } catch (e) {
    console.error(e);
  }
}

function onGenerate() {
  const date = selectedDate();
  window.location.href = `/api/report.pdf?date=${encodeURIComponent(date)}`;
}

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("reportDate");
  if (input) input.value = todayISO();

  loadSummary();

  input?.addEventListener("change", loadSummary);
  document.getElementById("btnGenerate")?.addEventListener("click", onGenerate);
});
