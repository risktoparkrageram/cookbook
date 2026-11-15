// Theme button: cycles light → dark → auto, remembered per phone. The saved theme is
// applied before the first paint by the inline script in base.html.
(function () {
  const icons = {
    auto: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/></svg>',
    light: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1"/></svg>',
    dark: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>',
  };
  const order = ["light", "dark", "auto"];
  const button = document.querySelector(".theme");
  const themeColour = document.querySelector('meta[name="theme-color"]');
  const saved = () => localStorage.getItem("theme") || "light";
  const apply = (theme) => {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
    button.innerHTML = icons[theme];
    button.title = "Theme: " + theme;
    themeColour.content = getComputedStyle(document.documentElement).getPropertyValue("--paper").trim();
  };
  apply(saved());
  button.addEventListener("click", () => apply(order[(order.indexOf(saved()) + 1) % order.length]));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => apply(saved()));
})();

// Dialogs such as the filter sheet: a button with data-opens="id" opens one, a button with
// data-closes inside one closes it. Delegated, so it survives htmx swapping the buttons.
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-opens]");
  if (opener) document.getElementById(opener.dataset.opens).showModal();
  const closer = event.target.closest("[data-closes]");
  if (closer) closer.closest("dialog").close();
});

// Leave empty fields out of htmx searches, so the address bar holds only the filters set.
document.addEventListener("htmx:configRequest", (event) => {
  const data = event.detail.formData;
  for (const key of [...new Set(data.keys())]) {
    if (data.getAll(key).every((value) => value === "")) data.delete(key);
  }
});
