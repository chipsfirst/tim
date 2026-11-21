// Мини-игры: крестики-нолики, понг и «бегунок» в духе Марио.
// Все рисуются на одном полотне #tw поверх экрана.

(function () {
  var c = document.getElementById("tw");
  if (!c) return;
  var x = c.getContext("2d");
  var W = c.width, H = c.height;
  var mode = null, timer = null, onKey = null;

  function clear() { x.fillStyle = "#071108"; x.fillRect(0, 0, W, H); }
  function stop() {
    clearInterval(timer); timer = null; mode = null;
    if (onKey) { document.removeEventListener("keydown", onKey); onKey = null; }
    c.classList.remove("on");
    var b = document.getElementById("tx"); if (b) b.style.display = "none";
  }
  function open() { if (window.TIM && TIM.tetris) TIM.tetris.close(); c.classList.add("on");
    if (window.addCoins) window.addCoins(1);
    var b = document.getElementById("tx"); if (b) b.style.display = "block"; }

  /* ------------------------------ крестики-нолики */
  function tic() {
    var cells = Array(9).fill(""), over = false, turn = "X";
    open();
    function lines(b) {
      var L = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
      for (var i = 0; i < L.length; i++) {
        var a = L[i][0], d = L[i][1], f = L[i][2];
        if (b[a] && b[a] === b[d] && b[a] === b[f]) return b[a];
      }
      return b.indexOf("") < 0 ? "=" : "";
    }
    function bot() {
      var b = cells.slice();
      for (var i = 0; i < 9; i++) if (!b[i]) { b[i] = "O"; if (lines(b) === "O") return i; b[i] = ""; }
      for (var j = 0; j < 9; j++) if (!b[j]) { b[j] = "X"; if (lines(b) === "X") return j; b[j] = ""; }
      var free = [];
      for (var k = 0; k < 9; k++) if (!cells[k]) free.push(k);
      return free[Math.floor(Math.random() * free.length)];
    }
    function draw() {
      clear();
      var s = Math.min(W, H) / 3;
      var ox = (W - s * 3) / 2, oy = (H - s * 3) / 2;
      x.strokeStyle = "#2A5A3A"; x.lineWidth = 2;
      for (var i = 1; i < 3; i++) {
        x.beginPath(); x.moveTo(ox + i * s, oy); x.lineTo(ox + i * s, oy + 3 * s); x.stroke();
        x.beginPath(); x.moveTo(ox, oy + i * s); x.lineTo(ox + 3 * s, oy + i * s); x.stroke();
      }
      x.font = "bold 30px monospace"; x.textAlign = "center";
      cells.forEach(function (v, i) {
        if (!v) return;
        x.fillStyle = v === "X" ? "#66FF9E" : "#FF8A7A";
        x.fillText(v, ox + (i % 3) * s + s / 2, oy + Math.floor(i / 3) * s + s / 2 + 10);
      });
      var r = lines(cells);
      if (r) {
        x.font = "bold 14px monospace"; x.fillStyle = "#FFFFFF";
        x.fillText(r === "=" ? "НИЧЬЯ" : "ПОБЕДА " + r, W / 2, H - 8);
      }
    }
    c.onclick = function (e) {
      if (over) return;
      var rect = c.getBoundingClientRect();
      var px = (e.clientX - rect.left) * (W / rect.width);
      var py = (e.clientY - rect.top) * (H / rect.height);
      var s = Math.min(W, H) / 3;
      var ox = (W - s * 3) / 2, oy = (H - s * 3) / 2;
      var col = Math.floor((px - ox) / s), row = Math.floor((py - oy) / s);
      if (col < 0 || col > 2 || row < 0 || row > 2) return;
      var i = row * 3 + col;
      if (cells[i]) return;
      cells[i] = "X";
      var r = lines(cells);
      if (!r) { cells[bot()] = "O"; r = lines(cells); }
      if (r) over = true;
      draw();
    };
    draw();
  }

  /* ------------------------------ понг */
  function pong() {
    open();
    var ph = 34, py = (H - ph) / 2, ay = (H - ph) / 2;
    var bx = W / 2, by = H / 2, vx = 3, vy = 2, score = 0;
    onKey = function (e) {
      var step = 18;
      if (e.key === "ArrowUp") py = Math.max(0, py - step);
      else if (e.key === "ArrowDown") py = Math.min(H - ph, py + step);
      else if (e.key === "Escape") stop();
      e.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    timer = setInterval(function () {
      by += vy; bx += vx;
      if (by < 4 || by > H - 4) vy = -vy;
      ay += (by - (ay + ph / 2)) * 0.12;
      ay = Math.max(0, Math.min(H - ph, ay));
      if (bx < 8 && by > py && by < py + ph) { vx = Math.abs(vx); score++; }
      if (bx < 0) { bx = W / 2; by = H / 2; vx = 3; score = 0; }
      if (bx > W - 8 && by > ay && by < ay + ph) vx = -Math.abs(vx);
      if (bx > W) vx = -Math.abs(vx);
      clear();
      x.fillStyle = "#66FF9E";
      x.fillRect(2, py, 4, ph);
      x.fillRect(W - 6, ay, 4, ph);
      x.fillRect(bx, by, 4, 4);
      x.font = "10px monospace"; x.fillStyle = "#3CFF86";
      x.fillText(String(score), 6, 12);
      x.fillStyle = "#2A5A3A";
      x.fillText("Esc — выйти", W - 74, 12);
    }, 16);
  }

  /* ------------------------------ «бегунок» */
  function runner() {
    open();
    var gy = H - 24, pyy = gy, vy = 0, obs = [], t = 0, score = 0, dead = false;
    onKey = function (e) {
      if (e.key === "Escape") { stop(); return; }
      if (dead && (e.key === "r" || e.key === "R" || e.key === "Enter")) {
        document.removeEventListener("keydown", onKey);
        clearInterval(timer);
        runner();
        return;
      }
      if ((e.key === " " || e.key === "ArrowUp") && pyy >= gy) vy = -9;
      e.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    timer = setInterval(function () {
      if (dead) return;
      t++; vy += 0.6; pyy = Math.min(gy, pyy + vy);
      if (t % 70 === 0 || (t > 200 && t % 37 === 0)) {
        var kind = Math.random();
        if (kind < 0.4) obs.push({ x: W, h: 8 + Math.random() * 6, y: gy });          // низкий пень
        else if (kind < 0.75) obs.push({ x: W, h: 26 + Math.random() * 10, y: gy });  // высокая стена
        else obs.push({ x: W, h: 10, y: gy - 42 });                                   // летящий блок
      }
      obs.forEach(function (o) { o.x -= 4; });
      obs = obs.filter(function (o) { return o.x > -10; });
      var hit = obs.some(function (o) {
        return o.x < 20 && o.x + 8 > 8 && pyy + 16 > o.y - o.h && pyy < o.y;
      });
      if (hit) dead = true;
      score++;
      clear();
      x.fillStyle = "#3CFF86";
      x.fillRect(8, pyy, 12, 10);
      x.fillStyle = "#071108";
      x.fillRect(10, pyy + 3, 2, 2);
      x.fillRect(15, pyy + 3, 2, 2);
      x.fillStyle = "#3CFF86";
      x.fillRect(6, pyy + 10, 16, 3);
      x.fillRect(9, pyy + 13, 3, 3);
      x.fillRect(16, pyy + 13, 3, 3);
      x.fillStyle = "#FF8A7A";
      obs.forEach(function (o) {
        x.fillStyle = o.y < gy ? "#FFD166" : "#FF8A7A";
        x.fillRect(o.x, o.y - o.h, 8, o.h);
      });
      x.fillStyle = "#1E4429";
      x.fillRect(0, gy + 16, W, H - gy - 16);
      x.fillStyle = "#3CFF86";
      x.fillRect(0, gy + 15, W, 2);
      for (var gx = (t * 4) % 24; gx < W; gx += 24) {
        x.fillRect(gx, gy + 20, 8, 2);
      }
      x.fillStyle = "#FFFFFF"; x.font = "10px monospace";
      x.fillText(dead ? "GAME OVER — R: заново, Esc: выйти" : "SCORE " + score, 6, 12);
    }, 33);
  }

  window.TIM = window.TIM || {};
  window.TIM.games = {
    tic: function () { if (mode) stop(); mode = "tic"; tic(); },
    pong: function () { if (mode) stop(); mode = "pong"; pong(); },
    runner: function () { if (mode) stop(); mode = "runner"; runner(); },
    close: stop,
  };
  var tx = document.getElementById("tx");
  if (tx) tx.onclick = function (e) { e.stopPropagation(); stop(); };
})();
