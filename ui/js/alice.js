// Мост к окну Алисы: вопрос, ожидание ответа, история.

let history = [];
let histPos = -1;

async function ask() {
  let text = $("q").value.trim();
  if (/^(погода|weather)\s*$/i.test(text)) { text = ""; $("q").value = ""; runQuick("weather"); return; }
  if (!text) return;
  try {
    const dbg = API();
    if (dbg && dbg.log_js) dbg.log_js("ask: busy=" + busy + " hook=" + (typeof window.guessHook));
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
  busy = true;
  clearTimeout(window.__busyGuard);
  window.__busyGuard = setTimeout(function () {
    if (busy) {
      busy = false;
      const send = $("send");
      if (send) send.disabled = false;
    }
  }, 60000);
  if ($("send")) $("send").disabled = true;
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

  document.body.classList.remove("g-think");
  if (typeof window.rememberExchange === "function") {
    window.rememberExchange(text, answer || "");
  }
  showAnswer(answer || "Алиса промолчала.", false);
  gesture("g-happy", 900);
  chirp("ok");
  $("q").value = "";
  if ($("send")) $("send").disabled = false;
  busy = false;
}
