(function () {
  "use strict";

  const storageKey = "alexroan-theme";
  let savedTheme = null;
  let currentTheme;
  let toggle;

  try {
    const stored = window.localStorage.getItem(storageKey);
    if (stored === "light" || stored === "dark") savedTheme = stored;
  } catch (_) {
    // The light default and toggle still work when storage is unavailable.
  }

  function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.dataset.theme = theme;
    if (toggle) toggle.setAttribute("aria-pressed", String(theme === "dark"));
  }

  // Run before the stylesheet loads so a saved choice is applied before paint.
  applyTheme(savedTheme || "light");

  function enableToggle() {
    toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    toggle.setAttribute("aria-pressed", String(currentTheme === "dark"));
    toggle.addEventListener("click", function () {
      savedTheme = currentTheme === "dark" ? "light" : "dark";
      applyTheme(savedTheme);
      try {
        window.localStorage.setItem(storageKey, savedTheme);
      } catch (_) {
        // Keep the explicit choice for this page even if it cannot be persisted.
      }
    });
    toggle.hidden = false;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enableToggle, { once: true });
  } else {
    enableToggle();
  }
})();
