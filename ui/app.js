// Ошибки из окна — в общий лог, а не в пустоту консоли.
window.addEventListener("error", function (e) {
  try {
    var api = window.pywebview && window.pywebview.api;
    if (api && api.log_js) api.log_js(e.message || "error", e.filename || "", e.lineno || 0);
  } catch (err) { /* лог недоступен — молчим */ }
});

window.addEventListener("unhandledrejection", function (e) {
  try {
    var api = window.pywebview && window.pywebview.api;
    if (api && api.log_js) api.log_js("promise: " + (e.reason && e.reason.message || e.reason), "", 0);
  } catch (err) { /* лог недоступен — молчим */ }
});

const $ = (id) => document.getElementById(id);
const API = () => (window.pywebview && window.pywebview.api) || null;

let hover = false;
let panelOpen = false;
let busy = false;
let hideTimer = null;


function setPanel(open) {
  panelOpen = open;
  $("panel").classList.toggle("show", open);
  // Поле ввода живёт в облачке — наведению нужно и его тоже показать.
  $("bubble").classList.toggle("show", open || !!$("bubble-text").textContent.trim());
  const a = API();
  if (a && a.set_panel) a.set_panel(open);
  reportRegions();
  if (open) setTimeout(() => $("q").focus(), 140);
}

function onHover(value) {
  if (value === hover) return;
  hover = value;
  if (value) {
    clearTimeout(hideTimer);
    setPanel(true);
  } else {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (!hover && document.activeElement !== $("q") && !$("q").value) setPanel(false);
    }, 900);
  }
}

/* ---------------------------------------------- ответ */

let voiceOn = false;

window.toggleVoice = function () {
  voiceOn = !voiceOn;
  showAnswer(voiceOn ? "Буду читать ответы вслух." : "Читать вслух больше не буду.", false);
};

const bubbleBox = $("bubble");
if (bubbleBox) {
  bubbleBox.tabIndex = 0;
  bubbleBox.addEventListener("wheel", function (e) { e.stopPropagation(); }, { passive: false });
  bubbleBox.addEventListener("keydown", function (e) {
    const step = 40;
    if (e.key === "PageDown" || e.key === "ArrowDown") { bubbleBox.scrollTop += step; e.preventDefault(); }
    else if (e.key === "PageUp" || e.key === "ArrowUp") { bubbleBox.scrollTop -= step; e.preventDefault(); }
  });
}

function showAnswer(text, thinking) {
  $("bubble-text").textContent = text;
  $("bubble").classList.add("show");
  $("bubble").classList.toggle("thinking", !!thinking);
  try { localStorage.setItem("tim-last-answer", String(text || "").slice(0, 12000)); } catch (e) {}
  try {
    const api = API();
    if (api && api.save_last) api.save_last(String(text || "").slice(0, 12000));
    if (api && api.log_js) api.log_js("save_last: " + String(text || "").length + " chars");
  } catch (e) {}
  if (!thinking && voiceOn) {
    const api = API();
    if (api && api.speak) api.speak(String(text).slice(0, 400)).catch(() => {});
  }
  if (thinking) {
    text = "Алиса думает";
    window.__restored = false;
  }
  const box = $("bubble");
  box.scrollTop = box.scrollHeight;
}

/* ---------------------------------------------- реплики в простое */


function quoteTick() {
  setTimeout(function () {
    if (!busy && !document.body.classList.contains("g-sleep")
        && !document.body.classList.contains("screen-off")) {
      const pool = Math.random() < 0.4 ? MOTIVATE : QUOTES;
      showAnswer(pool[Math.floor(Math.random() * pool.length)], false);
      gesture("g-blink", 400);
    }
    quoteTick();
  }, 240000 + Math.random() * 300000);
}

function tuneTick() {
  setTimeout(function () {
    if (!muted && !busy && !document.body.classList.contains("g-sleep")) {
      playTune();
      gesture("g-happy", 1200);
    }
    tuneTick();
  }, 420000 + Math.random() * 480000);
}

function idleTalk() {
  const delay = TIM.setting("humor.idle_min_ms", 150000)
    + Math.random() * TIM.setting("humor.idle_max_ms", 240000);
  setTimeout(() => {
    if (!busy && !panelOpen) {
      showAnswer(IDLE[Math.floor(Math.random() * IDLE.length)], false);
      gesture("g-happy", 900);
      chirp();
      setTimeout(() => {
        if (!busy) $("bubble").classList.remove("show");
      }, 9000);
    }
    idleTalk();
  }, delay);
}

/* ---------------------------------------------- быстрые ответы */




function weatherDesc(code) {
  if (code === 0) return "ясно";
  if (code <= 3) return "переменная облачность";
  if (code <= 48) return "туман";
  if (code <= 67) return "дождь";
  if (code <= 77) return "снег";
  if (code <= 82) return "ливень";
  return "гроза";
}

async function quickWeather() {
  busy = true;
  gesture("g-think", 8000);
  showAnswer("Смотрю погоду…", true);
  let text = "Не смог узнать погоду — нет сети.";
  try {
    const url = "https://api.open-meteo.com/v1/forecast?latitude=55.75&longitude=37.62"
      + "&current=temperature_2m,weather_code&timezone=Europe/Moscow";
    const res = await fetch(url);
    const data = await res.json();
    const t = Math.round(data.current.temperature_2m);
    text = "Сейчас " + t + "°, " + weatherDesc(data.current.weather_code) + ".";
  } catch (err) {
    /* оставляем текст ошибки */
  }
  document.body.classList.remove("g-think");
  showAnswer(text, false);
  gesture("g-happy", 900);
  chirp("ok");
  busy = false;
}

function quickTime() {
  const now = new Date();
  const t = now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  showAnswer("Сейчас " + t + ".", false);
  gesture("g-happy", 900);
  chirp("ok");
}

function quickJoke() {
  showAnswer(JOKES[Math.floor(Math.random() * JOKES.length)], false);
  gesture("g-happy", 900);
  chirp("ok");
}

function runQuick(kind) {
  if (busy) return;
  if (kind === "weather") quickWeather();
  else if (kind === "time") quickTime();
  else if (kind === "joke") quickJoke();
}

/* ---------------------------------------------- запрос */


/* ---------------------------------------------- зоны кликов */

function rectOf(el, shown) {
  if (!el || (shown && !el.classList.contains(shown))) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return null;
  return { x: r.left, y: r.top, w: r.width, h: r.height };
}

function reportRegions() {
  const a = API();
  if (!a || !a.set_regions) return;
  const shell = $("robot").offsetParent ? $("robot").getBoundingClientRect() : document.querySelector(".device").getBoundingClientRect();
  const r = shell;
  const p = $("panel").getBoundingClientRect();
  const extra = [
    rectOf($("menu"), "on"),
    rectOf($("bubble"), "show"),
  ].filter(Boolean);
  a.set_regions(
    { x: r.left, y: r.top, w: r.width, h: r.height },
    { x: p.left, y: p.top, w: p.width, h: p.height },
    extra
  );
}

/* ---------------------------------------------- железо и игра */

function floppySound() {
  [0, 70, 140, 215, 300].forEach((t, i) => setTimeout(
    () => blip(330 - i * 28, 0.05, "square", 190, 0.09), t));
  setTimeout(() => blip(150, 0.14, "sawtooth", 85, 0.07), 430);
}

function dance() {
  const seq = [520, 660, 780, 660, 880, 780, 990];
  seq.forEach((f, i) => setTimeout(() => blip(f, 0.14, "square", f * 1.2, 0.12), i * 140));
  showAnswer("Танцую!" + (window.stateLine ? window.stateLine() : ""), false);
  gesture("g-scan", 900);
  setTimeout(() => gesture("g-happy", 900), 950);
  setTimeout(() => gesture("g-left", 700), 1900);
}

let hunger = 0;

function feed() {
  hunger = 0;
  if (typeof bump === "function") { bump("hp", 12); bump("batt", 3); }
  if (typeof feedToday === "function") feedToday();
  if (typeof window.addCoins === "function") window.addCoins(1);
  showAnswer("Ням! Спасибо, вкусно." + (window.stateLine ? window.stateLine() : ""), false);
  gesture("g-happy", 1200);
  [0, 160, 320].forEach((t) => setTimeout(() => blip(300, 0.07, "square", 180, 0.1), t));
}

function hungerLoop() {
  setInterval(() => {
    hunger += 1;
    if (hunger === 2 && !busy) {
      showAnswer("Я проголодался — покормишь?", false);
      gesture("g-squint", 900);
      chirp();
    }
  }, TIM.setting("hunger.bite_ms", 600000));
}

[["Покормить", feed], ["Танец", dance]].forEach(([label, fn]) => {
  const btn = document.createElement("button");
  btn.textContent = label;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!busy) fn();
  });
  $("chips").appendChild(btn);
});


window.dance = dance;
window.time = quickTime;

let game = null;

function startGame() {
  if (busy) return;
  game = { phase: "wait" };
  showAnswer("Игра: нажми на меня, как только пискну.", false);
  setTimeout(() => {
    if (!game) return;
    game = { phase: "go", t: Date.now() };
    chirp("ok");
    showAnswer("Жми!", false);
  }, 1200 + Math.random() * 2500);
}

function gameClick() {
  if (!game) return false;
  if (game.phase === "wait") {
    showAnswer("Рано! Подожди писка.", false);
    chirp("think");
  } else {
    const ms = Date.now() - game.t;
    showAnswer("Поймал! Твоя реакция: " + ms + " мс.", false);
    chirp("ok");
    gesture("g-happy", 900);
  }
  game = null;
  return true;
}

const floppyEl = $("floppy");
if (floppyEl) {
  floppyEl.addEventListener("click", (e) => {
    e.stopPropagation();
    floppySound();
    gesture("g-scan", 900);
  });
}

$("robot").addEventListener("click", (e) => {
  if (gameClick()) e.stopPropagation();
}, true);

const gameChip = document.querySelector('[data-q="game"]');
if (gameChip) gameChip.addEventListener("click", (e) => {
  e.stopPropagation();
  startGame();
});

modemLoop();

/* ---------------------------------------------- события */

$("send").addEventListener("click", ask);

$("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); ask(); return; }
  if (e.key === "ArrowUp" && history.length) {
    e.preventDefault();
    histPos = Math.max(0, histPos - 1);
    $("q").value = history[histPos] || "";
  }
  if (e.key === "ArrowDown" && history.length) {
    e.preventDefault();
    histPos = Math.min(history.length, histPos + 1);
    $("q").value = history[histPos] || "";
  }
});

$("login").addEventListener("click", async () => {
  const a = API();
  if (!a || !a.login) return;
  chirp("think");
  const res = await a.login();
  if (res === "failed") showAnswer("Не смог открыть окно Алисы. Нажмите ещё раз.", false);
});

$("sound").addEventListener("click", (e) => {
  e.stopPropagation();
  muted = !muted;
  document.body.classList.toggle("muted", muted);
  if (!muted) chirp("ok");
});

$("power").addEventListener("click", (e) => {
  e.stopPropagation();
  if (window.TIM) window.TIM.quit = true;
  const a = API();
  if (a && a.quit) {
    try { a.quit(); } catch (err) { /* сработает опрос из Python */ }
  }
});

document.querySelectorAll("#chips button").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    runQuick(btn.dataset.q);
  });
});

$("robot").addEventListener("click", () => {
  const g = GESTURES[Math.floor(Math.random() * GESTURES.length)];
  gesture(g[0], g[1]);
  chirp();
});

window.addEventListener("blur", () => {
  if (!hover && !$("q").value) setPanel(false);
});

window.TIM = window.TIM || {};
window.TIM.state = function (s) {
  if (!s) return;
  if ("hover" in s) onHover(!!s.hover);
  if ("sleep" in s) {
    window.TIM.asleep = !!s.sleep;
    document.body.classList.toggle("g-sleep", !!s.sleep);
  }
};

/* ---------------------------------------------- показатели (RPG) */


window.addEventListener("pywebviewready", () => {
  const a = API();
  if (a && a.ready) a.ready();
  reportRegions();
});

if (window.TIM && TIM.menu) {
  TIM.menu.mount([
    { id: "feed", label: "Покормить", run: feed },
    { id: "dance", label: "Танец", run: dance },
    { id: "weather", label: "Погода", run: quickWeather },
    { id: "joke", label: "Шутка", run: quickJoke },

    { id: "games", label: "Игры ▸", items: [
      { id: "tetris", label: "Тетрис", run: function () { TIM.tetris.start(); } },
      { id: "tic", label: "Крестики-нолики", run: function () { TIM.games.tic(); } },
      { id: "pong", label: "Понг", run: function () { TIM.games.pong(); } },
      { id: "runner", label: "Бегунок", run: function () { TIM.games.runner(); } },
    ] },
    { id: "adult", label: "Позвать взрослого", run: function () { window.callAdult(); } },
    { id: "guess", label: "Угадай число", run: function () { window.startGuess(); } },
    { id: "shop", label: "Магазин ▸", items: [
      { id: "buy-green", label: "Зелёная (0)", run: function () { window.buyTheme("green"); } },
      { id: "buy-blue", label: "Синяя (10)", run: function () { window.buyTheme("blue"); } },
      { id: "buy-red", label: "Красная (15)", run: function () { window.buyTheme("red"); } },
      { id: "buy-gold", label: "Золотая (25)", run: function () { window.buyTheme("gold"); } },
    ] },
    { id: "more", label: "Сервис ▸", items: [
      { id: "charge", label: "Заряд", run: function () { window.charge(); } },
      { id: "time", label: "Время", run: function () { quickTime(); } },
      { id: "info", label: "Состояние", run: function () { window.info(); } },
      { id: "setup", label: "Настройки ▸", items: [
        { id: "voice", label: "Голос вкл/выкл", run: function () { window.toggleVoice(); } },
      { id: "reminder", label: "Напоминания", run: function () { window.toggleReminder(); } },
        { id: "autostart", label: "Автозапуск", run: function () { window.toggleAutostart(); } },
        { id: "update", label: "Обновления", run: function () { window.checkUpdate(); } },
        { id: "diag", label: "Диагностика", run: function () { window.diag(); } },
        { id: "reset", label: "Начать сначала", run: function () { window.resetProgress(); } },
      ] },
    ] },
  ]);
}

window.diag = function () {
  const api = API();
  const lines = [
    "Платформа: " + (navigator.platform || "?"),
    "Экран: " + screen.width + "×" + screen.height,
    "Окно: " + window.innerWidth + "×" + window.innerHeight,
    "Масштаб: " + Math.round((window.devicePixelRatio || 1) * 100) + "%",
    "Мост: " + (api ? "есть" : "нет"),
    "Модули: " + Object.keys(window.TIM || {}).join(", "),
    "Тик: " + TIM.setting("stats.tick_ms", "?") + " мс",
    "Звук: " + (muted ? "выкл" : "вкл"),
    "Батарея " + Math.round(STATS.batt) + "% · Здоровье "
      + Math.round(STATS.hp) + "% · Сон " + Math.round(STATS.sleep) + "%",
  ];
  showAnswer(lines.join("\n"), false);
};

let reminderTimer = null;

window.toggleReminder = function () {
  if (reminderTimer) {
    clearInterval(reminderTimer);
    reminderTimer = null;
    showAnswer("Напоминания выключены.", false);
    return;
  }
  const ms = TIM.setting("reminders.every_ms", 2700000);
  reminderTimer = setInterval(() => {
    if (document.body.classList.contains("g-sleep")) return;
    showAnswer("Ты давно за экраном. Встань, разомнись, попей воды.", false);
    gesture("g-squint", 1200);
    chirp("think");
  }, ms);
  showAnswer("Буду напоминать раз в " + Math.round(ms / 60000) + " мин.", false);
};

window.toggleWide = function () {
  const api = API();
  const next = !document.body.classList.contains("wide");
  document.body.classList.toggle("wide", next);
  // На Windows окно не растягиваем: после смены размера прозрачность теряется
  // и по краям остаётся белая подложка. Место для ответа даёт сама вёрстка.
  if (/Win/i.test(navigator.platform || "")) {
    reportRegions();
    return;
  }
  if (!api || !api.toggle_expand) return;
  api.toggle_expand().then((r) => {
    if (!r || !r.ok) return;
    reportRegions();
  }).catch((e) => showAnswer("Ошибка режима: " + e, false));
};

window.settingsCard = function () {
  const api = API();
  showAnswer(
    "Звук: " + (muted ? "выключен" : "включён") + "\n" +
    "Напоминания: " + (reminderTimer ? "включены" : "выключены") + "\n" +
    "Автозапуск: переключается пунктом меню\n" +
    "Звук: кнопка-динамик на корпусе", false);
};

window.toggleAutostart = function () {
  const api = API();
  if (!api || !api.autostart_toggle) {
    showAnswer("Автозапуск недоступен.", false);
    return;
  }
  api.autostart_toggle().then((state) => {
    if (state === null) showAnswer("Не удалось изменить автозапуск.", false);
    else showAnswer(state ? "Буду стартовать вместе с системой." : "Автозапуск выключен.", false);
  }).catch(() => showAnswer("Не удалось изменить автозапуск.", false));
};

let guessGame = null;

window.callAdult = function () {
  showAnswer("Зову взрослых! Эй, тут нужен человек.", false);
  for (let i = 0; i < 6; i += 1) {
    setTimeout(() => blip(1200, 0.18, "square", 1600, 0.16), i * 260);
  }
  gesture("g-happy", 1800);
};

window.startGuess = function () {
  guessGame = { secret: 1 + Math.floor(Math.random() * 100), tries: 0 };
  showAnswer("Загадал число от 1 до 100. Пиши догадку — отвечу «больше» или «меньше»." +
             " Угадаешь — получишь 2 монеты.", false);
  gesture("g-blink", 400);
  chirp("ok");
};

function handleGuess(text) {
  if (!guessGame) return false;
  const n = parseInt(text.replace(/[^0-9]/g, ""), 10);
  if (!n || n < 1 || n > 100) {
    showAnswer("Нужно число от 1 до 100.", false);
    return true;
  }
  guessGame.tries += 1;
  if (n === guessGame.secret) {
    const tries = guessGame.tries;
    guessGame = null;
    if (window.addCoins) window.addCoins(2);
    showAnswer("Угадал! Это " + n + ". Попыток: " + tries + ". Держи 2 монеты.", false);
    gesture("g-happy", 1400);
    chirp("ok");
  } else {
    showAnswer("Попытка " + guessGame.tries + ": " + (n < guessGame.secret ? "больше." : "меньше.")
      + " Загадано от 1 до 100.", false);
    gesture("g-squint", 600);
  }
  return true;
}

window.guessHook = function (text) {
  try {
    const api = API();
    if (api && api.log_js) api.log_js("guess: active=" + !!guessGame + " text=" + text.slice(0, 8));
  } catch (e) {}
  if (/угадай\s*число/i.test(text)) { window.startGuess(); return true; }
  return handleGuess(text);
};

const SECRETS = {
  "тим, покажи фокус": "Фокус-покус! Смотри: я моргаю сразу обоими глазами... почти.",
  "фокус": "Секрет: если покормить меня три раза подряд, я станцую.",
  "секрет": "Ты нашёл секрет. Я запомню, что ты любопытный.",
  "позови взрослого": "Эй, взрослые! Тут ребёнок хочет внимания!",
};

window.resetProgress = function () {
  if (!confirm("Начать сначала? Шкалы и уровень обнулятся.")) return;
  Object.keys(STATS).forEach((k) => { STATS[k] = k === "xp" ? 0 : 100; });
  paintStats();
  saveStats();
  if (API() && API().save_stats) API().save_stats({ batt: 100, hp: 100, sleep: 100, xp: 0 });
  showAnswer("Начинаем сначала. Уровень 1.", false);
  gesture("g-blink", 400);
  chirp("ok");
};

window.checkUpdate = function () {
  const api = API();
  if (!api || !api.check_update) {
    showAnswer("Проверка обновлений недоступна.", false);
    return;
  }
  showAnswer("Смотрю, нет ли новой версии…", true);
  api.check_update().then((tag) => {
    if (tag) showAnswer("Последняя версия: " + tag + ". Если у вас старее — скачайте с сайта.", false);
    else showAnswer("Не удалось узнать версию — проверьте интернет.", false);
  }).catch(() => showAnswer("Не удалось проверить обновления.", false));
};

function restoreLast(tries) {
  tries = tries || 0;
  const api = API();
  if (!api || !api.last) {
    if (tries < 40) setTimeout(function () { restoreLast(tries + 1); }, 250);
    return;
  }
  api.last().then((text) => {
    if (api.log_js) api.log_js("restore: " + (text ? text.length : 0) + " chars");
    if (!text) return;
    window.__restored = true;
    $("bubble-text").textContent = text;
    const box = $("bubble");
    box.classList.add("show");
    box.scrollTop = box.scrollHeight;
  }).catch(() => {});
}
window.addEventListener("pywebviewready", function () { restoreLast(0); });
setTimeout(function () { restoreLast(0); }, 400);

try {
  const saved = localStorage.getItem("tim-last-answer");
  if (saved) {
    if (!thinking && voiceOn) {
    const api = API();
    if (api && api.speak) api.speak(String(text).slice(0, 400)).catch(() => {});
  }
  if (thinking) {
    text = "Алиса думает";
    window.__restored = false;
  }
  const box = $("bubble");
    $("bubble-text").textContent = saved;
    box.classList.add("show");
    box.scrollTop = box.scrollHeight;
  }
} catch (e) {}

reportRegions();
setTimeout(reportRegions, 800);
setTimeout(reportRegions, 2500);

function nightTick() {
  const h = new Date().getHours();
  const night = h >= 23 || h < 7;
  document.body.classList.toggle("night", night);
  setTimeout(nightTick, 60000);
}

function boot() {
  nightTick();
  quoteTick();
  tuneTick();
  modemLoop();
  hungerLoop();
  if (window.TIM && TIM.startStats) TIM.startStats();
  scheduleGesture();
  scheduleFace();
  idleTalk();
  setTimeout(() => {
    if (window.__restored) return;
    showAnswer("Привет, друг! Я на связи.", false);
    gesture("g-happy", 1200);
    chirp("think");
    setTimeout(() => {
      if (!busy) $("bubble").classList.remove("show");
    }, 7000);
  }, 1500);
}

// Таймеры стартуют после чтения config.json, иначе числа не успеют примениться.
(window.TIM && TIM.configReady ? TIM.configReady : Promise.resolve()).then(boot, boot);
