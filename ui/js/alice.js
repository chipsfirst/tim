// Мост к окну Алисы: вопрос, ожидание ответа, история.

let history = [];
let histPos = -1;

function setAskBusy(on) {
  busy = on;
  const send = $("send");
  if (send) send.textContent = on ? "■" : "→";
  if (!on) document.body.classList.remove("g-think");
}

/* Пока ждём ответ, кнопка отправки превращается в «стоп»: 45 секунд
   молчания — слишком долго, чтобы их нельзя было прервать. */
function cancelAsk() {
  if (!busy) return false;
  const a = API();
  if (a && a.cancel) {
    try { a.cancel(); } catch (e) { /* ответ всё равно уже не нужен */ }
  }
  clearTimeout(window.__busyGuard);
  setAskBusy(false);
  showAnswer("Хорошо, отменил.", false);
  return true;
}

async function ask() {
  let text = $("q").value.trim();
  if (/^(погода|weather)\s*$/i.test(text)) { text = ""; $("q").value = ""; runQuick("weather"); return; }
  if (!text) return;
  try {
    const dbg = API();
    if (dbg && dbg.log_js) dbg.log_js("ask: busy=" + busy + " hook=" + (typeof window.guessHook), "", 0, "info");
  } catch (e) {}
  try {
    if (typeof window.guessHook === "function" && window.guessHook(text)) {
      $("q").value = "";
      return;
    }
  } catch (err) { /* игра не должна ломать вопросы */ }
  if (busy) return;
  history.push(text);
  histPos = history.length;
  setAskBusy(true);
  clearTimeout(window.__busyGuard);
  window.__busyGuard = setTimeout(function () { if (busy) setAskBusy(false); }, 60000);
  gesture("g-think", 60000);
  chirp("think");
  showAnswer("…", true);

  const a = API();
  let answer = "Нет связи с приложением.";
  if (a && a.ask) {
    try {
      const TIMEOUT = 45000;
      answer = await Promise.race([
        a.ask(text),
        new Promise((res) => setTimeout(
          () => res("Алиса не ответила за 45 секунд. Окно Алисы: пункт ⌗ — проверьте вход."),
          TIMEOUT)),
      ]);
    } catch (err) {
      answer = "Не получилось спросить Алису.";
    }
  }

  if (!busy) return; // отменили, пока ждали — ответ уже не показываем
  if (typeof window.rememberExchange === "function") {
    window.rememberExchange(text, answer || "");
  }
  showAnswer(answer || "Алиса промолчала.", false);
  gesture("g-happy", 900);
  chirp("ok");
  $("q").value = "";
  setAskBusy(false);
}

document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  const menu = document.getElementById("menu");
  if (menu && menu.classList.contains("on")) return; // меню закрывается само
  if (cancelAsk()) { e.preventDefault(); return; }
  if ($("q").value) { $("q").value = ""; return; }
  if (panelOpen) setPanel(false);
});
