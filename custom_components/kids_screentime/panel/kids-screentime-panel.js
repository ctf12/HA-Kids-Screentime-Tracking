/* Kids Screentime sidebar panel: Log, Shows, Needs review. Plain DOM, no build step.
   Titles come from apps and TMDB, so they are only ever inserted as text. */
const WS = "kids_screentime/";
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const STYLE = `
  :host { display: block; color: var(--primary-text-color); background: var(--primary-background-color); min-height: 100%; font-family: var(--paper-font-body1_-_font-family, inherit); }
  header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
  nav { display: flex; gap: 4px; padding: 8px 16px 0; border-bottom: 1px solid var(--divider-color); }
  nav button { background: none; border: 0; border-bottom: 2px solid transparent; padding: 10px 14px; font: inherit; color: var(--secondary-text-color); cursor: pointer; }
  nav button[aria-selected="true"] { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  main { padding: 8px 16px 32px; max-width: 900px; margin: 0 auto; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
  .grow { flex: 1; min-width: 0; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sub { color: var(--secondary-text-color); font-size: 13px; }
  .badge.quiet { background: var(--secondary-background-color, #e0e0e0); color: var(--secondary-text-color); margin-left: 6px; }
  .badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--warning-color, #ffa600); color: #000; }
  button.act { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); cursor: pointer; }
  button.danger { color: var(--error-color, #db4437); }
  .form { display: grid; gap: 12px; padding: 12px 0; }
  .form label { display: grid; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  .form select, .form input[type="time"], .form input[type="text"] { font: inherit; padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  .days { display: flex; flex-wrap: wrap; gap: 8px; }
  .days label { display: inline-flex; align-items: center; gap: 4px; font-size: 14px; color: var(--primary-text-color); }
  .times { display: flex; gap: 12px; }
  .times label { flex: 1; }
  .empty { padding: 32px 0; color: var(--secondary-text-color); text-align: center; }
  header button { background: none; border: 1px solid currentColor; color: inherit; border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; }
`;

class KidsScreentimePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "log";
    this._showBlocked = false;
    this._data = { log: [], shows: [], review: [], windows: [] };
    this._form = { app: "", days: [], start: "21:00", end: "23:00", label: "" };
    this._error = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }
  set narrow(value) {
    if (this._narrow !== value) {
      this._narrow = value;
      if (this._hass) this._render();
    }
  }
  set panel(_) {}

  async _ws(type, extra = {}) {
    return this._hass.callWS({ type: WS + type, ...extra });
  }

  async _load() {
    try {
      const [log, shows, review, windows] = await Promise.all([
        this._ws("sessions", { limit: 200 }), this._ws("shows"), this._ws("review"), this._ws("quiet_windows"),
      ]);
      this._data = { log, shows, review, windows };
      this._error = null;
    } catch (err) {
      this._error = err.message || "Could not load Kids Screentime data";
    }
    this._render();
  }

  async _do(type, extra) {
    let failed = null;
    try {
      await this._ws(type, extra);
    } catch (err) {
      failed = err.message || "That change failed";
    }
    await this._load();
    if (failed) {
      this._error = failed; // _load() clears errors on success, so show the failure after it
      this._render();
    }
  }

  _when(iso) {
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  _logRows() {
    if (!this._data.log.length) return h("div", { class: "empty" }, "Nothing recorded yet.");
    return this._data.log.map((s) =>
      h("div", { class: "row" },
        h("div", { class: "grow" },
          h("div", { class: "title" }, s.show_title,
            s.pending ? h("span", { class: "badge" }, "needs review") : null,
            s.counted_minutes === 0 && s.minutes > 0 ? h("span", { class: "badge quiet" }, "not counted") : null,
            s.counted_minutes > 0 && s.counted_minutes < s.minutes ? h("span", { class: "badge quiet" }, "partly counted") : null),
          h("div", { class: "sub" }, `${this._when(s.start)} · ${s.counted_minutes < s.minutes ? `${s.counted_minutes} of ${s.minutes} min counted` : `${s.minutes} min`} · ${s.app || "Unknown app"} · ${s.device}`)),
        h("button", { class: "act danger", onclick: () => this._do("delete_session", { session_id: s.id }) }, "Delete")));
  }

  _showRows() {
    const rows = this._data.shows.filter((s) => s.blocked === this._showBlocked);
    const toggle = h("div", { class: "row" },
      h("div", { class: "grow sub" }, this._showBlocked ? "Blocked titles are never recorded." : "Everything gathered so far."),
      h("button", { class: "act", onclick: () => { this._showBlocked = !this._showBlocked; this._render(); } },
        this._showBlocked ? "Show active" : "Show blocked"));
    if (!rows.length) return [toggle, h("div", { class: "empty" }, this._showBlocked ? "No blocked titles." : "No shows yet.")];
    return [toggle, ...rows.map((s) =>
      h("div", { class: "row" },
        h("div", { class: "grow" },
          h("div", { class: "title" }, s.title),
          h("div", { class: "sub" }, [s.rating || "unrated", `${s.minutes} min`, s.percent != null ? `${s.percent}% through` : null, s.source].filter(Boolean).join(" · "))),
        this._showBlocked
          ? h("button", { class: "act", onclick: () => this._do("set_rule", { key: s.key, rule: null }) }, "Unblock")
          : h("button", { class: "act danger", onclick: () => {
              if (window.confirm(`Delete "${s.title}" and all its sessions? It will not be recorded again.`)) this._do("delete_show", { key: s.key });
            } }, "Delete")))];
  }

  _windowText(w) {
    const days = w.days.map((d) => DAY_NAMES[d]).join(", ");
    return `${w.apps.length ? w.apps.join(", ") : "All apps"} · ${days} · ${w.start}\u2013${w.end}`;
  }

  _filterRows() {
    const f = this._form;
    const apps = [...new Set(this._data.log.map((x) => x.app).filter(Boolean))].sort();
    const list = this._data.windows.length
      ? this._data.windows.map((w) =>
          h("div", { class: "row" },
            h("div", { class: "grow" },
              h("div", { class: "title" }, w.label || "Quiet time"),
              h("div", { class: "sub" }, this._windowText(w))),
            h("button", { class: "act danger", onclick: () => this._do("delete_quiet_window", { window_id: w.id }) }, "Delete")))
      : [h("div", { class: "empty" }, "No filters. Everything recorded counts.")];
    const form = h("div", { class: "form" },
      h("div", { class: "sub" }, "Time inside a filter is still logged, but it does not count toward the totals."),
      h("label", {}, "App",
        h("select", { onchange: (e) => { f.app = e.target.value; } },
          h("option", { value: "", ...(f.app === "" ? { selected: "" } : {}) }, "All apps"),
          apps.map((a) => h("option", { value: a, ...(f.app === a ? { selected: "" } : {}) }, a)))),
      h("div", { class: "days", role: "group", "aria-label": "Days" },
        DAY_NAMES.map((name, i) =>
          h("label", {}, h("input", { type: "checkbox", ...(f.days.includes(i) ? { checked: "" } : {}),
            onchange: (e) => { f.days = e.target.checked ? [...f.days, i] : f.days.filter((d) => d !== i); } }), name))),
      h("div", { class: "times" },
        h("label", {}, "From", h("input", { type: "time", value: f.start, onchange: (e) => { f.start = e.target.value; } })),
        h("label", {}, "To", h("input", { type: "time", value: f.end, onchange: (e) => { f.end = e.target.value; } }))),
      h("label", {}, "Name (optional)", h("input", { type: "text", value: f.label, onchange: (e) => { f.label = e.target.value; } })),
      h("button", { class: "act", onclick: () => this._addWindow() }, "Add filter"));
    return [h("div", { class: "sub" }, "Disregard certain hours and days, for one app or all of them. Times are Home Assistant's local time; a window that ends before it starts runs past midnight."), ...list, form];
  }

  async _addWindow() {
    const f = this._form;
    await this._do("add_quiet_window", { apps: f.app ? [f.app] : [], days: f.days, start: f.start, end: f.end, label: f.label });
    if (!this._error) this._form = { app: "", days: [], start: f.start, end: f.end, label: "" };
    this._render();
  }

  _reviewRows() {
    if (!this._data.review.length) return h("div", { class: "empty" }, "Nothing waiting for review.");
    return this._data.review.map((s) =>
      h("div", { class: "row" },
        h("div", { class: "grow" },
          h("div", { class: "title" }, s.title),
          h("div", { class: "sub" }, `${s.minutes} min waiting · ${s.rating || "no rating found"}`)),
        h("button", { class: "act", onclick: () => this._do("resolve_review", { key: s.key, count: true }) }, "Count"),
        h("button", { class: "act danger", onclick: () => this._do("resolve_review", { key: s.key, count: false }) }, "Don't count")));
  }

  _menuButton() {
    // On a narrow screen the sidebar is closed, so the panel must offer the button that opens it.
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    return menu;
  }

  _render() {
    const tabs = [["log", "Log"], ["shows", "Shows"], ["filters", "Filters"], ["review", `Needs review${this._data.review.length ? ` (${this._data.review.length})` : ""}`]];
    const body = { log: () => this._logRows(), shows: () => this._showRows(), filters: () => this._filterRows(), review: () => this._reviewRows() }[this._tab]();
    this.shadowRoot.replaceChildren(
      h("style", {}, STYLE),
      h("header", {}, this._menuButton(), h("h1", {}, "Kids Screentime"), h("button", { onclick: () => this._load() }, "Refresh")),
      h("nav", { role: "tablist" }, tabs.map(([id, label]) =>
        h("button", { role: "tab", "aria-selected": String(this._tab === id), onclick: () => { this._tab = id; this._render(); } }, label))),
      h("main", {}, this._error ? h("div", { class: "empty" }, this._error) : null, body));
  }
}

customElements.define("kids-screentime-panel", KidsScreentimePanel);
