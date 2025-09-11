// static/app.js
document.addEventListener("DOMContentLoaded", () => {
    // Küçük UX iyileştirmeleri
    const thresholds = document.querySelectorAll('input[name="threshold"]');
    thresholds.forEach(inp => {
      inp.addEventListener("change", () => {
        const v = parseFloat(inp.value);
        if (isNaN(v) || v <= 0 || v >= 1) {
          alert("Eşik 0.40 ile 0.85 arasında olmalı (öneri: 0.55–0.65).");
        }
      });
    });
  });
  