async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

const BADGE_CLASS = { low: "b--good", medium: "b--mid", high: "b--high" };
let activeLevel = "";

function fmt(v) {
  return v === null || v === undefined ? "—" : Number(v).toFixed(3);
}

async function loadHistory() {
  const body = document.getElementById("historyBody");
  const empty = document.getElementById("historyEmpty");
  if (!body) return;

  try {
    const qs = activeLevel ? `?level=${encodeURIComponent(activeLevel)}` : "";
    const data = await fetchJSON(`/api/history${qs}`);
    const records = data.records || [];

    body.innerHTML = "";
    if (!records.length) {
      empty?.classList.remove("is-hidden");
      return;
    }
    empty?.classList.add("is-hidden");

    for (const r of records) {
      const tr = document.createElement("tr");
      const badgeCls = BADGE_CLASS[r.stress_level] || "";
      tr.innerHTML = `
        <td>${r.date}</td>
        <td>${r.time}</td>
        <td><span class="badge badge--sm ${badgeCls}">${r.stress_level_label}</span></td>
        <td>${fmt(r.MEAN_RR)}</td>
        <td>${fmt(r.RMSSD)}</td>
        <td>${fmt(r.SDRR)}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadHistory();

  document.getElementById("btnRefresh")?.addEventListener("click", loadHistory);

  const filters = document.getElementById("levelFilters");
  filters?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".filter-btn");
    if (!btn) return;
    filters.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    activeLevel = btn.getAttribute("data-level") || "";
    loadHistory();
  });
});
