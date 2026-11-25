// Звук: пищалки R2-D2, флоппи и модем.

var audio = null;
var muted = false;

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
  if (kind === "bad") {
    blip(340, 0.14, "square", 160, 0.12);
    setTimeout(() => blip(210, 0.18, "square", 120, 0.10), 150);
    return;
  }
  if (kind === "coin") {
    blip(1180, 0.05, "square", 1180, 0.10);
    setTimeout(() => blip(1560, 0.10, "square", 1560, 0.10), 70);
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
  }, TIM.setting("humor.modem_min_ms", 210000)
     + Math.random() * TIM.setting("humor.modem_max_ms", 300000));
}


function toggleMute() {
  muted = !muted;
  document.body.classList.toggle('muted', muted);
  return muted;
}

// Пиксельные мелодии: народные и позапрошловековые мотивы.
var TUNES = [
  [660,660,660,520,660,780,780],
  [520,590,660,590,520,440,520],
  [440,520,590,660,590,520,440],
  [780,780,780,520,660,780,880],
  [392,523,659,784,659,523,392],
  [523,659,784,1047,784,659,523],
  [440,554,659,880,659,554,440],
  [659,587,523,587,659,659,659],
  [1047,988,880,784,880,988,1047]
];

function playTune() {
  // Мягкая версия: синус, длинные ноты, тихая громкость и плавное затухание.
  var tune = TUNES[Math.floor(Math.random() * TUNES.length)];
  tune.forEach(function (f, i) {
    setTimeout(function () {
      blip(f, 0.34, "sine", f * 1.002, 0.045);
      setTimeout(function () { blip(f * 0.5, 0.3, "triangle", f * 0.5, 0.02); }, 40);
    }, i * 320);
  });
}
