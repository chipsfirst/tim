// Меню: один реестр действий вместо перебора имён в разметке.
//
// app.js отдаёт список {id, label, run}, меню строит кнопки само.
// Никаких data-act в HTML и никаких window[act] — опечатка в имени
// больше не превращается в молчащую кнопку.

(function () {
  var el = null;
  var btn = null;
  var handlers = {};
  var stack = [];

  function report() {
    if (typeof window.reportRegions === "function") window.reportRegions();
  }

  function close() {
    if (!el) return;
    el.classList.remove("on");
    report();
  }

  function toggle() {
    if (!el) return;
    el.classList.toggle("on");
    if (el.classList.contains("on")) {
      var first = el.querySelector("button");
      if (first) first.focus();
    }
    report();
  }

  function back() {
    if (stack.length) mount(stack.pop());
  }

  function run(id) {
    var fn = handlers[id];
    if (fn && typeof fn === "object" && fn.items) {
      stack.push(current);
      mount(fn.items, true);
      return;
    }
    close();
    if (typeof fn !== "function") {
      if (window.showAnswer) window.showAnswer("Команда «" + id + "» недоступна.", false);
      return;
    }
    fn();
  }

  var pending = null;

  function ensure() {
    if (el) return true;
    el = document.getElementById("menu");
    btn = document.getElementById("mbtn");
    if (!el || !btn) return false;
    bind();
    return true;
  }

  function audit() {
    return Object.keys(handlers).filter(function (id) {
      var h = handlers[id];
      return !(typeof h === "function" || (h && typeof h === "object" && h.items));
    });
  }

  var current = [];

  function mount(list, keepStack) {
    if (keepStack !== true) stack = [];
    if (!ensure()) { pending = list; return; }
    current = list;
    handlers = {};
    el.innerHTML = "";
    var items = list || [];
    if (stack.length) items = [{ id: "back", label: "← Назад", run: back }].concat(items);
    items.forEach(function (item) {
      handlers[item.id] = item.items ? { items: item.items } : item.run;
      var b = document.createElement("button");
      b.textContent = item.label;
      b.dataset.act = item.id;
      b.setAttribute("role", "menuitem");
      el.appendChild(b);
    });
  }

  function bind() {
    el.setAttribute("role", "menu");
    btn.setAttribute("role", "button");
    btn.setAttribute("aria-label", "Меню");

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("click", function (e) {
      if (!el.classList.contains("on")) return;
      if (!el.contains(e.target) && e.target !== btn) close();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { close(); return; }
      if (!el.classList.contains("on")) return;
      var items = Array.prototype.slice.call(el.querySelectorAll("button"));
      if (!items.length) return;
      var at = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        var step = e.key === "ArrowDown" ? 1 : -1;
        var next = (at + step + items.length) % items.length;
        items[next].focus();
      } else if (e.key === "Enter" && at >= 0) {
        e.preventDefault();
        run(items[at].dataset.act);
      }
    });

    el.addEventListener("click", function (e) {
      var item = e.target.closest("[data-act]");
      if (!item) return;
      e.stopPropagation();
      run(item.dataset.act);
    });
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    var key = e.target.closest("#widebtn") || e.target.closest("#collapse");
    if (!key) return;
    e.stopPropagation();
    var api = window.pywebview && window.pywebview.api;
    if (api && api.log_js) api.log_js("wide click (delegated)");
    if (typeof window.toggleWide === "function") window.toggleWide();
  });

  document.addEventListener("DOMContentLoaded", function () {
    ensure();
    if (pending) { var list = pending; pending = null; mount(list); }
  });

  window.TIM = window.TIM || {};
  window.TIM.menu = { mount: mount, close: close, toggle: toggle, audit: audit };
})();
