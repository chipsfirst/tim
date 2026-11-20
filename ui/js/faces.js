// Мимика: жесты и случайные рожицы.

let gestureTimer = null;

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

const FACES = [
  ["face-open", 650],
  ["face-wide", 900],
  ["face-flat", 700],
  ["face-o", 600],
  ["face-tongue", 800],
];

function clearFace() {
  FACES.forEach(([cls]) => document.body.classList.remove(cls));
}

function scheduleFace() {
  const wait = TIM.setting("humor.face_min_ms", 5000)
    + Math.random() * TIM.setting("humor.face_max_ms", 9000);
  setTimeout(() => {
    if (!document.body.classList.contains("screen-off")
        && !document.body.classList.contains("g-sleep")) {
      const [cls, ms] = FACES[Math.floor(Math.random() * FACES.length)];
      clearFace();
      document.body.classList.add(cls);
      if (Math.random() < 0.55) chirp(Math.random() < 0.5 ? "ok" : "think");
      setTimeout(clearFace, ms);
    }
    scheduleFace();
  }, wait);
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

