// Меню: один реестр действий вместо перебора имён в разметке.
//
// app.js отдаёт список {id, label, run}, меню строит кнопки само.
// Никаких data-act в HTML и никаких window[act] — опечатка в имени
// больше не превращается в молчащую кнопку.

(function () {
  var el = null;
  var btn = null;
  var handlers = {};

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
    report();
  }

  function run(id) {
    var fn = handlers[id];
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
      return typeof handlers[id] !== "function";
    });
  }

  function mount(list) {
    if (!ensure()) { pending = list; return; }
    handlers = {};
    el.innerHTML = "";
    (list || []).forEach(function (item) {
      handlers[item.id] = item.run;
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
      if (e.key === "Escape") close();
    });

    el.addEventListener("click", function (e) {
      var item = e.target.closest("[data-act]");
      if (!item) return;
      e.stopPropagation();
      run(item.dataset.act);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    ensure();
    if (pending) { var list = pending; pending = null; mount(list); }
  });

  window.TIM = window.TIM || {};
  window.TIM.menu = { mount: mount, close: close, toggle: toggle, audit: audit };
})();
