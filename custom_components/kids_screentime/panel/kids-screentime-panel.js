/* Kids Screentime sidebar panel: Log, Shows, Needs review. Plain DOM, no build step.
   Titles come from apps and TMDB, so they are only ever inserted as text. */
const WS = "kids_screentime/";

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
  .badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--warning-color, #ffa600); color: #000; }
  button.act { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); cursor: pointer; }
  button.danger { color: var(--error-color, #db4437); }
  .empty { padding: 32px 0; color: var(--secondary-text-color); text-align: center; }
  header button { background: none; border: 1px solid currentColor; color: inherit; border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; }
`;

class KidsScreentimePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "log";
    this._showBlocked = false;
    this._data = { log: [], shows: [], review: [] };
    this._error = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }
  set narrow(_) {}
  set panel(_) {}

  async _ws(type, extra = {}) {
    return this._hass.callWS({ type: WS + type, ...extra });
  }

  async _load() {
    try {
      const [log, shows, review] = await Promise.all([
        this._ws("sessions", { limit: 200 }), this._ws("shows"), this._ws("review"),
      ]);
      this._data = { log, shows, review };
      this._error = null;
    } catch (err) {
      this._error = err.message || "Could not load Kids Screentime data";
    }
    this._render();
  }

  async _do(type, extra) {
    try {
      await this._ws(type, extra);
    } catch (err) {
      this._error = err.message || "That change failed";
    }
    await this._load();
  }

  _when(iso) {
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  _logRows() {
    if (!this._data.log.length) return h("div", { class: "empty" }, "Nothing recorded yet.");
    return this._data.log.map((s) =>
      h("div", { class: "row" },
        h("div", { class: "grow" },
          h("div", { class: "title" }, s.show_title, s.pending ? h("span", { class: "badge" }, "needs review") : null),
          h("div", { class: "sub" }, `${this._when(s.start)} · ${s.minutes} min · ${s.app || "Unknown app"} · ${s.device}`)),
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

  _render() {
    const tabs = [["log", "Log"], ["shows", "Shows"], ["review", `Needs review${this._data.review.length ? ` (${this._data.review.length})` : ""}`]];
    const body = { log: () => this._logRows(), shows: () => this._showRows(), review: () => this._reviewRows() }[this._tab]();
    this.shadowRoot.replaceChildren(
      h("style", {}, STYLE),
      h("header", {}, h("h1", {}, "Kids Screentime"), h("button", { onclick: () => this._load() }, "Refresh")),
      h("nav", { role: "tablist" }, tabs.map(([id, label]) =>
        h("button", { role: "tab", "aria-selected": String(this._tab === id), onclick: () => { this._tab = id; this._render(); } }, label))),
      h("main", {}, this._error ? h("div", { class: "empty" }, this._error) : null, body));
  }
}

customElements.define("kids-screentime-panel", KidsScreentimePanel);
