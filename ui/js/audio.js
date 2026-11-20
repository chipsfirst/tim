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
