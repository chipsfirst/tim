// Тетрис: отдельный модуль, наружу торчит только start().

(function () {
  var c = document.getElementById("tw");
  if (!c) return;
  var x = c.getContext("2d");
  var W = 10, H = 20, S = c.height / 20;
  var OX = (c.width - W * S) / 2, OY = (c.height - H * S) / 2;
  var P = [[[1,1,1,1]],[[1,1],[1,1]],[[0,1,0],[1,1,1]],[[1,0,0],[1,1,1]],
           [[0,0,1],[1,1,1]],[[1,1,0],[0,1,1]],[[0,1,1],[1,1,0]]];
  var g, cur, px, py, score, over, timer;

  function spawn() {
    cur = P[Math.floor(Math.random() * P.length)].map(function (r) { return r.slice(); });
    px = 3; py = 0;
    if (hit(0, 0)) { over = true; stop(); }
  }

  function hit(dx, dy, sh) {
    sh = sh || cur;
    for (var y = 0; y < sh.length; y++) for (var xx = 0; xx < sh[y].length; xx++) {
      if (!sh[y][xx]) continue;
      var nx = px + xx + dx, ny = py + y + dy;
      if (nx < 0 || nx >= W || ny >= H) return true;
      if (ny >= 0 && g[ny][nx]) return true;
    }
    return false;
  }

  function rot() {
    var r = cur[0].map(function (_, i) {
      return cur.map(function (row) { return row[i]; }).reverse();
    });
    if (!hit(0, 0, r)) cur = r;
  }

  function clearRows() {
    for (var y = H - 1; y >= 0; y--) {
      if (g[y].every(function (v) { return v; })) {
        g.splice(y, 1); g.unshift(Array(W).fill(0)); score += 100; y++;
      }
    }
  }

  function lock() {
    cur.forEach(function (row, y) {
      row.forEach(function (v, xx) {
        if (v && py + y >= 0) g[py + y][px + xx] = 1;
      });
    });
    clearRows(); spawn();
  }

  function draw() {
    x.fillStyle = "#071108"; x.fillRect(0, 0, c.width, c.height);
    x.fillStyle = "#3CFF86";
    g.forEach(function (row, y) {
      row.forEach(function (v, xx) { if (v) x.fillRect(OX + xx * S, OY + y * S, S - 1, S - 1); });
    });
    if (!over) cur.forEach(function (row, y) {
      row.forEach(function (v, xx) {
        if (v && py + y >= 0) x.fillRect(OX + (px + xx) * S, OY + (py + y) * S, S - 1, S - 1);
      });
    });
    x.fillStyle = "#66FF9E"; x.font = "10px monospace";
    x.fillText(over ? "GAME OVER" : "SCORE " + score, 4, 12);
    x.strokeStyle = "#2A5A3A"; x.strokeRect(OX - 1, OY - 1, W * S + 2, H * S + 2);
  }

  function step() { if (over) return; if (hit(0, 1)) lock(); else py++; draw(); }
  function stop() { clearInterval(timer); }

  function start() {
    g = Array.from({ length: H }, function () { return Array(W).fill(0); });
    score = 0; over = false;
    spawn();
    c.classList.add("on");
    stop();
    timer = setInterval(step, 450);
    draw();
  }

  function close() { c.classList.remove("on"); stop(); }

  var tx = document.getElementById("tx");
  if (tx) tx.onclick = function (e) { e.stopPropagation(); close(); };

  document.addEventListener("keydown", function (e) {
    if (!c.classList.contains("on")) return;
    if (e.key === "ArrowLeft" && !hit(-1, 0)) px--;
    else if (e.key === "ArrowRight" && !hit(1, 0)) px++;
    else if (e.key === "ArrowDown" && !hit(0, 1)) py++;
    else if (e.key === "ArrowUp") rot();
    else if (e.key === " ") { while (!hit(0, 1)) py++; }
    else if (e.key === "Escape") { close(); return; }
    e.preventDefault(); draw();
  });

  window.TIM = window.TIM || {};
  window.TIM.tetris = { start: start, close: close };
})();
