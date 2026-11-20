const $ = (id) => document.getElementById(id);
const API = () => (window.pywebview && window.pywebview.api) || null;

let hover = false;
let panelOpen = false;
let busy = false;
let muted = false;
let audio = null;
let gestureTimer = null;
let hideTimer = null;
let history = [];
let histPos = -1;

/* ---------------------------------------------- звук (R2-D2) */

function ctx() {
  if (!audio) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    audio = new AC();
  }
  if (audio.state === "suspended") audio.resume();
  return audio;
}

function blip(freq, dur, type, glide, vol) {
  if (muted) return;
  const ac = ctx();
  if (!ac) return;
  const now = ac.currentTime;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = type || "sine";
  osc.frequency.setValueAtTime(freq, now);
  if (glide) osc.frequency.exponentialRampToValueAtTime(Math.max(80, glide), now + dur);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(vol || 0.16, now + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  osc.connect(gain);
  gain.connect(ac.destination);
  osc.start(now);
  osc.stop(now + dur + 0.03);
}

function chirp(kind) {
  if (kind === "think") {
    blip(620, 0.09, "square", 900, 0.10);
    setTimeout(() => blip(760, 0.08, "square", 520, 0.10), 110);
    return;
  }
  if (kind === "ok") {
    blip(880, 0.10, "sine", 1320, 0.14);
    setTimeout(() => blip(1320, 0.12, "sine", 990, 0.12), 110);
    setTimeout(() => blip(1180, 0.16, "sine", 1560, 0.11), 240);
    return;
  }
  const n = 2 + Math.floor(Math.random() * 3);
  for (let i = 0; i < n; i += 1) {
    const base = 520 + Math.random() * 900;
    setTimeout(() => blip(base, 0.05 + Math.random() * 0.08, Math.random() < 0.5 ? "square" : "sine",
                         base * (0.6 + Math.random() * 0.9), 0.09), i * 95);
  }
}

/* ---------------------------------------------- жесты */

const GESTURES = [
  ["g-blink", 170],
  ["g-left", 700],
  ["g-right", 700],
  ["g-happy", 900],
  ["g-squint", 800],
  ["g-scan", 1600],
];

function gesture(name, ms) {
  document.body.classList.add(name);
  clearTimeout(gestureTimer);
  gestureTimer = setTimeout(() => document.body.classList.remove(name), ms);
}

function scheduleGesture() {
  const delay = 3200 + Math.random() * 5200;
  setTimeout(() => {
    if (!busy) {
      const g = GESTURES[Math.floor(Math.random() * GESTURES.length)];
      gesture(g[0], g[1]);
      if (Math.random() < 0.55) chirp();
    }
    scheduleGesture();
  }, delay);
}

/* ---------------------------------------------- окошко */

function setPanel(open) {
  panelOpen = open;
  $("panel").classList.toggle("show", open);
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

function showAnswer(text, thinking) {
  $("bubble-text").textContent = text;
  $("bubble").classList.add("show");
  $("bubble").classList.toggle("thinking", !!thinking);
  $("bubble").scrollTop = 0;
}

/* ---------------------------------------------- реплики в простое */

const IDLE = [
  "Как дела?",
  "Я на месте — спроси что-нибудь.",
  "Может, узнаем погоду?",
  "Разомнись немного, я подожду.",
];

function idleTalk() {
  const delay = 150000 + Math.random() * 240000;
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

const JOKES = [
  "Почему программисты путают Хэллоуин и Рождество? Потому что oct 31 == dec 25.",
  "У меня нет нервов — только провода. Зато стальные.",
  "Спрашиваю у Алисы совета. Она говорит: «Спроси Т.И.М.». Прогресс!",
  "Мой любимый цикл — while(true) { пить_кофе(); }",
];

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
      answer = await a.ask(text);
    } catch (err) {
      answer = "Не получилось спросить Алису.";
    }
  }

  document.body.classList.remove("g-think");
  showAnswer(answer || "Алиса промолчала.", false);
  gesture("g-happy", 900);
  chirp("ok");
  $("q").value = "";
  $("send").disabled = false;
  busy = false;
}

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
  const r = $("robot").getBoundingClientRect();
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

function modemSound() {
  [0, 240, 480, 720].forEach((t, i) => setTimeout(() => {
    blip(1150 - i * 170, 0.18, "sawtooth", 320, 0.07);
    blip(720 + i * 90, 0.16, "square", 1450, 0.05);
  }, t));
  setTimeout(() => blip(1750, 0.34, "sine", 380, 0.06), 980);
}

function modemLoop() {
  setTimeout(() => {
    if (!muted && !busy) modemSound();
    modemLoop();
  }, 210000 + Math.random() * 300000);
}

function dance() {
  const seq = [520, 660, 780, 660, 880, 780, 990];
  seq.forEach((f, i) => setTimeout(() => blip(f, 0.14, "square", f * 1.2, 0.12), i * 140));
  showAnswer("Танцую!", false);
  gesture("g-scan", 900);
  setTimeout(() => gesture("g-happy", 900), 950);
  setTimeout(() => gesture("g-left", 700), 1900);
}

let hunger = 0;

function feed() {
  hunger = 0;
  showAnswer("Ням! Спасибо, вкусно.", false);
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
  }, 600000);
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

modemLoop();
hungerLoop();

window.feed = feed;
window.dance = dance;
window.weather = quickWeather;
window.time = quickTime;
window.joke = quickJoke;

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

$("floppy").addEventListener("click", (e) => {
  e.stopPropagation();
  floppySound();
  gesture("g-scan", 900);
});

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

window.TIM = {
  state(s) {
    if (!s) return;
    if ("hover" in s) onHover(!!s.hover);
    if ("sleep" in s) document.body.classList.toggle("g-sleep", !!s.sleep);
  },
};

window.addEventListener("pywebviewready", () => {
  const a = API();
  if (a && a.ready) a.ready();
  reportRegions();
});

reportRegions();
setTimeout(reportRegions, 800);
setTimeout(reportRegions, 2500);
scheduleGesture();
idleTalk();

setTimeout(() => {
  showAnswer("Привет, друг! Я на связи.", false);
  gesture("g-happy", 1200);
  chirp("ok");
  setTimeout(() => {
    if (!busy) $("bubble").classList.remove("show");
  }, 7000);
}, 1500);
