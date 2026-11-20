// Показатели RPG: батарея, здоровье, сон.

const STATS = { batt: 100, hp: 100, sleep: 100, xp: 0 };
try {
  const saved = JSON.parse(localStorage.getItem("tim-stats") || "null");
  if (saved) for (const k in STATS) if (typeof saved[k] === "number") STATS[k] = saved[k];
} catch (e) {}

const warned = { batt: false, hp: false, sleep: false };

function bump(key, delta) {
  STATS[key] = Math.max(0, Math.min(100, STATS[key] + delta));
}

function paintStats() {
  const num = (id, v) => {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = String(Math.round(v));
      el.setAttribute("fill", v < 20 ? "#B4442E" : v < 40 ? "#8A6A1E" : "#4A4436");
    }
  };
  num("n-batt", STATS.batt);
  num("n-hp", STATS.hp);
  num("n-sleep", STATS.sleep);
  document.body.classList.toggle("low-batt", STATS.batt < 20);
  document.body.classList.toggle("low-hp", STATS.hp < 30);
  document.body.classList.toggle("low-sleep", STATS.sleep < 15);
}

function saveStats() {
  try { localStorage.setItem("tim-stats", JSON.stringify(STATS)); } catch (e) {}
}

function statReport() {
  if (STATS.batt < 20 && !warned.batt) {
    warned.batt = true;
    showAnswer("Батарея садится. Дай заряд.", false);
    gesture("g-squint", 900); chirp("bad");
  } else if (STATS.batt > 40) warned.batt = false;

  if (STATS.hp < 30 && !warned.hp) {
    warned.hp = true;
    showAnswer("Мне нездоровится. Покормишь?", false);
    gesture("g-squint", 1200); chirp("bad");
  } else if (STATS.hp > 55) warned.hp = false;

  if (STATS.sleep < 15 && !warned.sleep) {
    warned.sleep = true;
    showAnswer("Глаза слипаются... дай поспать.", false);
    gesture("g-sleep", 1500); chirp("ok");
  } else if (STATS.sleep > 45) warned.sleep = false;
}

function startStats() {
return setInterval(() => {
  bump("batt", -TIM.setting("stats.drain_battery", 0.12));
  bump("sleep", (window.TIM && window.TIM.asleep)
    ? TIM.setting("stats.regen_sleep", 2.2)
    : -TIM.setting("stats.drain_sleep", 0.2));
  bump("hp", (STATS.batt < 20 || STATS.sleep < 15)
    ? -TIM.setting("stats.damage_low", 0.12)
    : TIM.setting("stats.heal_ok", 0.05));
  gainXp();
  statReport();
  paintStats();
  saveStats();
  saveToDisk();
}, TIM.setting("stats.tick_ms", 15000));
}

function loadFromDisk() {
  const api = API();
  if (!api || !api.load_stats) return;
  api.load_stats().then((data) => {
    if (!data) return;
    Object.keys(STATS).forEach((k) => {
      if (typeof data[k] === "number") STATS[k] = data[k];
    });
    paintStats();
  }).catch(() => {});
}

function saveToDisk() {
  const api = API();
  if (!api || !api.save_stats) return;
  api.save_stats({
    batt: STATS.batt, hp: STATS.hp, sleep: STATS.sleep, xp: STATS.xp,
  }).catch(() => {});
}

setTimeout(loadFromDisk, 1200);

TIM.startStats = startStats;
paintStats();

function level() { return 1 + Math.floor(STATS.xp / 100); }
function xpLeft() { return 100 - (STATS.xp % 100); }

function gainXp() {
  if (STATS.hp > 50 && STATS.batt > 30 && STATS.sleep > 40) {
    STATS.xp += 1;
    if (STATS.xp % 100 === 0) {
      showAnswer("Уровень " + level() + "! Спасибо, что не забываешь.", false);
      gesture("g-happy", 1400);
      chirp("ok");
    }
  }
}

function word(v) {
  if (v > 70) return "отлично";
  if (v > 40) return "в норме";
  if (v > 20) return "низко";
  return "критично";
}

const sleepBtn = document.getElementById("sleepbtn");
if (sleepBtn) {
  sleepBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const off = document.body.classList.toggle("screen-off");
    if (off) {
      blip(220, 0.14, "sine", 90, 0.09);
    } else {
      chirp("ok");
      gesture("g-blink", 300);
    }
  });
}

window.info = function () {
  showAnswer(
    "Батарея: " + Math.round(STATS.batt) + "% — " + word(STATS.batt) + "\n" +
    "Здоровье: " + Math.round(STATS.hp) + "% — " + word(STATS.hp) + "\n" +
    "Сон: " + Math.round(STATS.sleep) + "% — " + word(STATS.sleep) + "\n" +
    "Уровень " + level() + " · опыт " + (STATS.xp % 100) + "/100 (ещё " + xpLeft() + ")",
    false
  );
  gesture("g-blink", 400);
};

window.charge = function () {
  showAnswer("Подключаюсь к розетке...", false);
  gesture("g-think", 1200);
  chirp("ok");
  setTimeout(() => {
    bump("batt", 100);
    bump("hp", 8);
    paintStats(); saveStats();
    showAnswer("Заряжен на сто процентов.", false);
    gesture("g-happy", 1200);
  }, 2600);
};

paintStats();
