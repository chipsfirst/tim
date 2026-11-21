// Мост к окну Алисы: вопрос, ожидание ответа, история.

let history = [];
let histPos = -1;

async function ask() {
  let text = $("q").value.trim();
  if (/^(погода|weather)\s*$/i.test(text)) { text = ""; $("q").value = ""; runQuick("weather"); return; }
  if (!text || busy) return;
  history.push(text);
  histPos = history.length;
  busy = true;
  $("send").disabled = true;
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
  $("send").disabled = false;
  busy = false;
}
