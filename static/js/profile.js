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

async function loadProfile() {
  const empty = document.getElementById("profileEmpty");
  try {
    const p = await fetchJSON("/api/profile");
    setText("profileName", p.name || "Demo User");
    setText("profileTotal", p.total_measurements ?? 0);
    setText("profileFrequent", p.most_frequent_stress || "No data");
    setText("profileHigh", p.high_stress_episodes ?? 0);

    if (p.monitoring_start && p.monitoring_end) {
      setText("profilePeriod", `${p.monitoring_start} – ${p.monitoring_end}`);
    } else {
      setText("profilePeriod", "No data yet");
    }

    if (!p.total_measurements) {
      empty?.classList.remove("is-hidden");
    } else {
      empty?.classList.add("is-hidden");
    }
  } catch (e) {
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", loadProfile);
