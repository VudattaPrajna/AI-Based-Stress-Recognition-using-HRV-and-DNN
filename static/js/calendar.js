async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const today = new Date();
let viewYear = today.getFullYear();
let viewMonth = today.getMonth() + 1; // 1-12

function levelClass(level) {
  if (level === "low") return "cal-cell--low";
  if (level === "medium") return "cal-cell--medium";
  if (level === "high") return "cal-cell--high";
  return "";
}

async function loadCalendar() {
  const grid = document.getElementById("calGrid");
  const title = document.getElementById("calTitle");
  if (!grid) return;

  title.textContent = `${MONTH_NAMES[viewMonth - 1]} ${viewYear}`;

  try {
    const data = await fetchJSON(`/api/calendar?year=${viewYear}&month=${viewMonth}`);
    const days = data.days || {};
    const dateKeys = Object.keys(days).sort();

    grid.innerHTML = "";
    if (!dateKeys.length) return;

    const firstDate = new Date(dateKeys[0] + "T00:00:00");
    let leadingBlanks = firstDate.getDay() - 1; // Monday = 0
    if (leadingBlanks < 0) leadingBlanks = 6; // Sunday

    for (let i = 0; i < leadingBlanks; i++) {
      const blank = document.createElement("div");
      blank.className = "cal-cell cal-cell--empty";
      grid.appendChild(blank);
    }

    for (const key of dateKeys) {
      const level = days[key];
      const dayNum = Number(key.split("-")[2]);
      const cell = document.createElement("div");
      cell.className = `cal-cell ${levelClass(level)}`;
      cell.title = level ? `${key}: mostly ${level}` : `${key}: no data`;
      cell.innerHTML = `<div class="cal-cell__num">${dayNum}</div><div class="cal-cell__dot"></div>`;
      grid.appendChild(cell);
    }
  } catch (e) {
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadCalendar();

  document.getElementById("btnPrevMonth")?.addEventListener("click", () => {
    viewMonth -= 1;
    if (viewMonth < 1) {
      viewMonth = 12;
      viewYear -= 1;
    }
    loadCalendar();
  });

  document.getElementById("btnNextMonth")?.addEventListener("click", () => {
    viewMonth += 1;
    if (viewMonth > 12) {
      viewMonth = 1;
      viewYear += 1;
    }
    loadCalendar();
  });
});
