async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data && data.error ? data.error : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(c);
  return node;
}

function renderInputs() {
  const grid = document.getElementById("inputsGrid");
  if (!grid || !Array.isArray(FEATURE_COLUMNS) || FEATURE_COLUMNS.length === 0) return;

  grid.innerHTML = "";
  for (const name of FEATURE_COLUMNS) {
    const input = el("input", {
      type: "number",
      step: "any",
      inputmode: "decimal",
      placeholder: "0.0",
      "data-feature": name,
      autocomplete: "off",
    });
    const field = el("div", { class: "field" }, [
      el("label", { text: name }),
      input,
    ]);
    grid.appendChild(field);
  }
}

function collectValues() {
  const values = {};
  const inputs = document.querySelectorAll('input[data-feature]');
  for (const input of inputs) {
    const k = input.getAttribute("data-feature");
    const v = input.value;
    values[k] = v === "" ? null : Number(v);
  }
  return values;
}

function applyValues(values) {
  const inputs = document.querySelectorAll('input[data-feature]');
  for (const input of inputs) {
    const k = input.getAttribute("data-feature");
    if (Object.prototype.hasOwnProperty.call(values, k)) {
      const v = values[k];
      input.value = (v === null || typeof v === "undefined") ? "" : String(v);
      input.closest(".field")?.animate(
        [{ transform: "translateY(0px)" }, { transform: "translateY(-2px)" }, { transform: "translateY(0px)" }],
        { duration: 280, easing: "cubic-bezier(.2,.9,.2,1)" }
      );
    }
  }
}

function setPrediction(text, tone = "default") {
  const box = document.getElementById("predText");
  if (!box) return;
  box.textContent = text;

  const map = {
    default: "linear-gradient(90deg, rgba(255,255,255,.92), rgba(255,255,255,.92))",
    ok: "linear-gradient(90deg, rgba(34,197,94,.95), rgba(0,229,255,.9))",
    warn: "linear-gradient(90deg, rgba(245,158,11,.95), rgba(255,77,141,.9))",
    err: "linear-gradient(90deg, rgba(239,68,68,.95), rgba(255,77,141,.92))",
  };
  box.style.backgroundImage = map[tone] || map.default;
  box.style.webkitBackgroundClip = "text";
  box.style.backgroundClip = "text";
  box.style.color = "transparent";
  box.animate([{ opacity: 0.3, transform: "translateY(2px)" }, { opacity: 1, transform: "translateY(0px)" }], {
    duration: 260,
    easing: "cubic-bezier(.2,.9,.2,1)",
  });
}

function setSuggestions(level, suggestions) {
  const badge = document.getElementById("levelBadge");
  const list = document.getElementById("suggestionsList");
  const wrap = document.getElementById("suggestionsWrap");
  if (!badge || !list || !wrap) return;

  const levelMap = {
    low: { text: "Low stress", cls: "badge badge--level b--good" },
    medium: { text: "Medium level stress", cls: "badge badge--level b--mid" },
    high: { text: "High stress", cls: "badge badge--level b--high" },
    unknown: { text: "Unknown", cls: "badge badge--level" },
  };

  const m = levelMap[level] || levelMap.unknown;
  badge.className = m.cls;
  badge.textContent = m.text;

  list.innerHTML = "";
  const items = Array.isArray(suggestions) ? suggestions : [];
  for (const s of items) {
    const li = document.createElement("li");
    li.textContent = s;
    list.appendChild(li);
  }

  wrap.classList.remove("is-hidden");
  wrap.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "translateY(0px)" }], {
    duration: 260,
    easing: "cubic-bezier(.2,.9,.2,1)",
  });
}

async function refreshStatus() {
  const box = document.getElementById("statusBox");
  if (!box) return;
  try {
    const st = await fetchJSON("/api/status");
    box.textContent = JSON.stringify(st, null, 2);
  } catch (e) {
    box.textContent = String(e?.message || e);
  }
}

async function onRandom() {
  try {
    const data = await fetchJSON("/api/random");
    applyValues(data.values || {});
  } catch (e) {
    setPrediction(e.message || "Random failed", "err");
  }
}

async function onPredict() {
  try {
    const values = collectValues();
    const data = await fetchJSON("/api/predict", {
      method: "POST",
      body: JSON.stringify({ values }),
    });
    const label = data.prediction || "—";
    const tone = (data.stress_level === "low") ? "ok" : ((data.stress_level === "high") ? "err" : "warn");
    setPrediction(label, tone);
    setSuggestions(data.stress_level || "unknown", data.suggestions || []);
  } catch (e) {
    setPrediction(e.message || "Prediction failed", "err");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  renderInputs();
  await refreshStatus();

  document.getElementById("btnRandom")?.addEventListener("click", onRandom);
  document.getElementById("btnPredict")?.addEventListener("click", onPredict);
});

