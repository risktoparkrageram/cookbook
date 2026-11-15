// Cook mode on the recipe page. The server has already found every number (D30): number
// spans carry data-value, metric quantities data-metric-*, and temperatures and inches in the
// text data-metric. This script only multiplies and formats; it never parses recipe text.
(function () {
  const main = document.querySelector("main[data-recipe]");
  const storageKey = "cook:" + main.dataset.recipe;
  const stored = (key, fallback) => {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch {
      return fallback;
    }
  };
  // Per recipe: ticked ingredients and steps, the current step and the serves factor.
  const state = { ticked: [], current: null, factor: 1, ...stored(storageKey, {}) };
  // Per phone: "written" or "metric".
  let units = localStorage.getItem("units") === "metric" ? "metric" : "written";
  const save = () => localStorage.setItem(storageKey, JSON.stringify(state));

  const tabs = document.querySelectorAll(".toggle [data-tab]");
  const showTab = (name) => {
    tabs.forEach((tab) => tab.setAttribute("aria-selected", tab.dataset.tab === name));
    document.getElementById("ingredients").hidden = name !== "ingredients";
    document.getElementById("method").hidden = name !== "method";
  };
  tabs.forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
  // A link to a step's notes, such as from the notes page, opens the Method tab.
  const target = location.hash && document.getElementById(location.hash.slice(1));
  showTab(target && target.closest("#method") ? "method" : "ingredients");
  if (target) target.scrollIntoView();

  const FRACTIONS = [
    ["", 0], ["⅛", 1 / 8], ["¼", 1 / 4], ["⅓", 1 / 3], ["⅜", 3 / 8], ["½", 1 / 2],
    ["⅝", 5 / 8], ["⅔", 2 / 3], ["¾", 3 / 4], ["⅞", 7 / 8], ["", 1],
  ];
  const decimal = (value, places) => String(+value.toFixed(places));
  // g, kg, ml, l: to 5 above 50, whole from 10, else up to two decimals.
  const metricNumber = (value) =>
    value >= 50 ? String(Math.round(value / 5) * 5) : value >= 10 ? String(Math.round(value)) : decimal(value, 2);
  // Everything else: a fraction within 0.04, else one decimal; tiny amounts as decimals.
  const fractionNumber = (value) => {
    let whole = Math.floor(value);
    const rest = value - whole;
    let [symbol, nearest] = FRACTIONS.reduce((best, fraction) =>
      Math.abs(rest - fraction[1]) < Math.abs(rest - best[1]) ? fraction : best);
    if (Math.abs(rest - nearest) > 0.04) return decimal(value, 1);
    if (nearest === 1) [whole, symbol] = [whole + 1, ""];
    if (whole === 0) return symbol || decimal(value, 2);
    return whole + symbol;
  };
  const metricAmount = (minimum, maximum, unit) => {
    // kg or l only when both ends reach 1000: "910–1815 g", not "0.91–1.81 kg".
    const large = minimum >= 1000;
    const shown = (value) => (large ? decimal(value / 1000, 2) : metricNumber(value));
    const name = large ? (unit === "g" ? "kg" : "l") : unit;
    const range = minimum === maximum ? shown(minimum) : `${shown(minimum)}–${shown(maximum)}`;
    return `≈ ${range} ${name}`;
  };

  // Each quantity and converted text span keeps its server-rendered form, to return to.
  const written = new Map();
  document.querySelectorAll(".q, .conv").forEach((element) => written.set(element, element.innerHTML));

  const servesSelect = document.getElementById("serves");
  const scaledNote = document.querySelector(".serves .scaled");
  const resetButton = document.querySelector(".reset");
  const stepItems = [...document.querySelectorAll("ol.steps > li")];

  const paint = () => {
    const factor = state.factor;
    document.querySelectorAll(".q").forEach((quantity) => {
      const metric = quantity.dataset.metricUnit;
      if (units === "metric" && metric) {
        quantity.textContent = metricAmount(
          +quantity.dataset.metricMin * factor, +quantity.dataset.metricMax * factor, metric);
        return;
      }
      quantity.innerHTML = written.get(quantity);
      if (factor === 1) return;
      quantity.querySelectorAll(".n:not([data-size])").forEach((number) => {
        const value = +number.dataset.value * factor;
        number.textContent = "metric" in number.dataset ? metricNumber(value) : fractionNumber(value);
      });
    });
    document.querySelectorAll(".conv").forEach((span) => {
      span.innerHTML = units === "metric" ? "" : written.get(span);
      if (units === "metric") span.textContent = span.dataset.metric;
    });
    document.querySelectorAll("ul.ing > li").forEach((item) =>
      item.classList.toggle("done", state.ticked.includes(item.dataset.tick)));
    stepItems.forEach((step) => {
      const done = state.ticked.includes(step.dataset.tick);
      step.classList.toggle("done", done);
      step.classList.toggle("current", step.dataset.tick === state.current);
      step.querySelector(".step-tick").setAttribute("aria-pressed", done);
    });
    document.querySelectorAll("[data-units]").forEach((button) =>
      button.setAttribute("aria-pressed", button.dataset.units === units));
    if (servesSelect) servesSelect.value = String(factor);
    if (scaledNote) scaledNote.hidden = factor === 1;
    resetButton.hidden = !(state.ticked.length || state.current || factor !== 1);
  };

  if (servesSelect && ![...servesSelect.options].some((option) => +option.value === state.factor)) {
    state.factor = 1;
  }
  if (!servesSelect) state.factor = 1;

  const toggleTick = (id) => {
    const index = state.ticked.indexOf(id);
    if (index >= 0) state.ticked.splice(index, 1);
    else state.ticked.push(id);
  };
  // Taps on notes, links and form controls are theirs, not a tick or a current step.
  const ownTap = (event) => event.target.closest(".notes, a, button, select, textarea, details");

  document.querySelectorAll("ul.ing > li").forEach((item) =>
    item.addEventListener("click", (event) => {
      if (ownTap(event)) return;
      toggleTick(item.dataset.tick);
      save();
      paint();
    }));
  stepItems.forEach((step) => {
    step.addEventListener("click", (event) => {
      if (ownTap(event)) return;
      state.current = state.current === step.dataset.tick ? null : step.dataset.tick;
      save();
      paint();
    });
    // Ticking the current step moves "current" on to the next unticked step.
    step.querySelector(".step-tick").addEventListener("click", () => {
      const id = step.dataset.tick;
      toggleTick(id);
      if (state.current === id && state.ticked.includes(id)) {
        const later = stepItems.slice(stepItems.indexOf(step) + 1)
          .find((other) => !state.ticked.includes(other.dataset.tick));
        state.current = later ? later.dataset.tick : null;
      }
      save();
      paint();
    });
  });
  if (servesSelect) {
    servesSelect.addEventListener("change", () => {
      state.factor = +servesSelect.value;
      save();
      paint();
    });
  }
  document.querySelectorAll("[data-units]").forEach((button) =>
    button.addEventListener("click", () => {
      units = button.dataset.units;
      localStorage.setItem("units", units);
      paint();
    }));
  resetButton.addEventListener("click", () => {
    Object.assign(state, { ticked: [], current: null, factor: 1 });
    save();
    paint();
  });
  paint();

  // Keep the screen awake while the recipe is open, from the first tap. Over plain HTTP
  // there is no Wake Lock API (it needs a secure context), so a muted, looping, nearly
  // invisible video does the job; browsers pause a hidden one, so it is 1 px, not hidden.
  let wakeLock = null;
  let video = null;
  let awake = false;
  const keepAwake = async () => {
    awake = true;
    if ("wakeLock" in navigator) {
      try {
        if (!wakeLock || wakeLock.released) wakeLock = await navigator.wakeLock.request("screen");
        return;
      } catch {
        // Refused, for example with the battery saver on: fall back to the video.
      }
    }
    if (!video) {
      video = document.createElement("video");
      video.className = "keep-awake";
      video.src = "/static/keep-awake.mp4";
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "");
      video.setAttribute("aria-hidden", "true");
      document.body.append(video);
    }
    video.play().catch(() => {});
  };
  document.addEventListener("click", keepAwake, { once: true });
  document.addEventListener("visibilitychange", () => {
    if (awake && document.visibilityState === "visible") keepAwake();
  });
})();
