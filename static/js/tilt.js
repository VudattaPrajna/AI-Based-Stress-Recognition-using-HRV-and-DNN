(() => {
  const els = document.querySelectorAll("[data-tilt]");
  if (!els.length) return;

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  for (const el of els) {
    el.addEventListener("mousemove", (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const y = (e.clientY - r.top) / r.height;
      const rx = clamp((0.5 - y) * 10, -8, 8);
      const ry = clamp((x - 0.5) * 12, -10, 10);
      el.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-2px)`;
    }, { passive: true });
    el.addEventListener("mouseleave", () => {
      el.style.transform = "perspective(900px) rotateX(0deg) rotateY(0deg) translateY(0px)";
    }, { passive: true });
  }
})();

