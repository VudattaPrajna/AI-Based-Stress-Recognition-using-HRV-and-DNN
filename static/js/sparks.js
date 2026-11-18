(() => {
  const canvas = document.getElementById("sparkCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  let w = 0, h = 0;
  let t = 0;

  const sparks = Array.from({ length: 90 }).map(() => ({
    x: Math.random(),
    y: Math.random(),
    r: 0.6 + Math.random() * 1.6,
    s: 0.25 + Math.random() * 0.9,
    o: 0.10 + Math.random() * 0.25,
    hue: 190 + Math.random() * 120,
  }));

  function resize() {
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw() {
    t += 0.0065;
    ctx.clearRect(0, 0, w, h);

    for (const p of sparks) {
      const px = (p.x + Math.sin(t * p.s + p.y * 10) * 0.0025) * w;
      const py = (p.y + Math.cos(t * p.s + p.x * 10) * 0.0025) * h;
      const a = p.o + 0.08 * Math.sin(t * 2 + p.x * 6);

      const g = ctx.createRadialGradient(px, py, 0, px, py, p.r * 10);
      g.addColorStop(0, `hsla(${p.hue}, 95%, 70%, ${a})`);
      g.addColorStop(1, `hsla(${p.hue}, 95%, 70%, 0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(px, py, p.r * 10, 0, Math.PI * 2);
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener("resize", resize, { passive: true });
  resize();
  draw();
})();

