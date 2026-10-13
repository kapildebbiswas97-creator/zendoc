/* Exercise shared browser handlers using an isolated DOM/event unit harness.
 * This is not a browser or staging test; no external services are contacted.
 */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tagName, attrs = {}) {
    this.tagName = tagName.toUpperCase();
    this.attrs = { ...attrs };
    this.dataset = {};
    this.listeners = {};
    this.disabled = false;
    this.hidden = false;
    this.name = "";
    this.value = "";
    this.textContent = "";
    this.children = [];
    this.classes = new Set();
    this.classList = {
      toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name),
    };
  }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  appendChild(child) { child.parent = this; this.children.push(child); }
  remove() { this.parent.children = this.parent.children.filter((child) => child !== this); }
  focus() { this.focused = true; }
  dispatch(type, extra = {}) {
    const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
    for (const handler of this.listeners[type] || []) handler(event);
    return event;
  }
  querySelectorAll(selector) {
    if (selector === "[data-zendoc-submitter-proxy]") return this.children.filter((item) => item.dataset.zendocSubmitterProxy);
    if (selector === "[data-zendoc-submitting-control]") return this.children.filter((item) => item.dataset.zendocSubmittingControl);
    if (selector === "button[type='submit'], input[type='submit']") return this.children.filter((item) => item.type === "submit");
    return [];
  }
}

function loadApp({ forms = [], tabs = [], panels = [] } = {}) {
  const listeners = {};
  const document = {
    documentElement: { dataset: {}, lang: "en" },
    querySelector: () => null,
    querySelectorAll(selector) {
      if (selector === "form") return forms;
      if (selector === "form[data-zendoc-submitting='true']") return forms.filter((form) => form.dataset.zendocSubmitting === "true");
      if (selector === ".scenario-tab") return tabs;
      if (selector === ".scenario-panel") return panels;
      return [];
    },
    getElementById: (id) => panels.find((panel) => panel.attrs.id === id) || null,
    createElement: (tag) => new Element(tag),
  };
  const window = {
    localStorage: { getItem: () => null },
    matchMedia: () => ({ matches: false }),
    addEventListener: (type, handler) => (listeners[type] ||= []).push(handler),
  };
  vm.runInNewContext(readFileSync(join(__dirname, "../../static/app.js"), "utf8"), {
    window, document, queueMicrotask,
  });
  return { pageshow: () => (listeners.pageshow || []).forEach((handler) => handler()) };
}

function reviewForm() {
  const form = new Element("form");
  const buttons = ["active", "rejected", "disabled"].map((value) => {
    const button = new Element("button");
    button.type = "submit";
    button.name = "status";
    button.value = value;
    button.textContent = value;
    form.appendChild(button);
    return button;
  });
  buttons[2].disabled = true;
  return { form, approve: buttons[0], reject: buttons[1], preDisabled: buttons[2] };
}

test("clicked rejection survives disabling without an approval or duplicate decision", () => {
  const { form, reject } = reviewForm();
  loadApp({ forms: [form] });
  form.dispatch("submit", { submitter: reject });
  const decisions = form.children.filter((item) => item.name === "status" && !item.disabled);
  assert.equal(decisions.length, 1);
  assert.equal(decisions[0].value, "rejected");
  assert.equal(decisions[0].type, "hidden");
  assert.equal(form.attrs["aria-busy"], "true");
});

test("missing or disabled submitters never synthesize approval", () => {
  for (const disabled of [false, true]) {
    const { form, preDisabled } = reviewForm();
    loadApp({ forms: [form] });
    form.dispatch("submit", { submitter: disabled ? preDisabled : null });
    assert.equal(form.children.filter((item) => item.type === "hidden").length, 0);
  }
});

test("cancelled submissions restore exact decisions and previously disabled controls", async () => {
  const { form, reject, preDisabled } = reviewForm();
  loadApp({ forms: [form] });
  form.addEventListener("submit", (event) => event.preventDefault());
  form.dispatch("submit", { submitter: reject });
  await new Promise(queueMicrotask);
  assert.equal(reject.disabled, false);
  assert.equal(reject.textContent, "rejected");
  assert.equal(preDisabled.disabled, true);
  assert.equal(form.children.length, 3);
  assert.equal(form.attrs["aria-busy"], undefined);
});

test("back-forward cache recovery permits retry while retaining pre-disabled controls", () => {
  const { form, reject, preDisabled } = reviewForm();
  const app = loadApp({ forms: [form] });
  form.dispatch("submit", { submitter: reject });
  assert.equal(form.dispatch("submit", { submitter: reject }).defaultPrevented, true);
  app.pageshow();
  assert.equal(reject.disabled, false);
  assert.equal(preDisabled.disabled, true);
  assert.equal(form.children.length, 3);
  assert.equal(form.dispatch("submit", { submitter: reject }).defaultPrevented, false);
});

function scenarioElements() {
  const panels = ["symptoms", "specialist", "report", "family"].map((name) => new Element("div", { id: `scenario-${name}` }));
  const tabs = panels.map((panel) => new Element("button", { "aria-controls": panel.attrs.id }));
  loadApp({ tabs, panels });
  return { tabs, panels };
}

function assertSelected(tabs, panels, index) {
  tabs.forEach((tab, position) => {
    assert.equal(tab.attrs["aria-selected"], String(position === index));
    assert.equal(tab.tabIndex, position === index ? 0 : -1);
    assert.equal(panels[position].hidden, position !== index);
    assert.equal(panels[position].classes.has("active"), position === index);
  });
}

test("scenario clicks expose one panel and one keyboard tab stop", () => {
  const { tabs, panels } = scenarioElements();
  tabs[2].dispatch("click");
  assertSelected(tabs, panels, 2);
});

test("scenario arrow keys wrap; Home and End move focus and selection together", () => {
  const { tabs, panels } = scenarioElements();
  for (const [from, key, to] of [[0, "ArrowLeft", 3], [3, "ArrowRight", 0], [1, "End", 3], [3, "Home", 0]]) {
    assert.equal(tabs[from].dispatch("keydown", { key }).defaultPrevented, true);
    assertSelected(tabs, panels, to);
    assert.equal(tabs[to].focused, true);
  }
  assert.equal(tabs[0].dispatch("keydown", { key: "Tab" }).defaultPrevented, false);
});
