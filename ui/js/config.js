// Настройки: значения по умолчанию и подгрузка config.json.
//
// Файл лежит рядом с index.html и попадает в бандл вместе с папкой ui.
// Всё, что тикает по времени, читает числа отсюда (TIM.config.*).

(function () {
  var defaults = {
    window: { width: 340, height: 500, margin_right: 12, margin_bottom: 2 },
    loop: { tick_ms: 100, push_every: 3, quit_check_every: 10, heartbeat_every: 100, sleep_after_s: 180 },
    stats: { tick_ms: 15000, drain_battery: 0.12, drain_sleep: 0.2, regen_sleep: 2.2, damage_low: 0.12, heal_ok: 0.05 },
    humor: { face_min_ms: 5000, face_max_ms: 9000, idle_min_ms: 150000, idle_max_ms: 240000, modem_min_ms: 210000, modem_max_ms: 300000 },
    hunger: { bite_ms: 600000 },
  };

  window.TIM = window.TIM || {};
  TIM.config = defaults;

  function merge(target, source) {
    Object.keys(source || {}).forEach(function (key) {
      var value = source[key];
      if (value && typeof value === "object" && !Array.isArray(value)) {
        merge(target[key] = target[key] || {}, value);
      } else if (value !== undefined) {
        target[key] = value;
      }
    });
    return target;
  }

  function value(path, fallback) {
    var parts = String(path).split(".");
    var node = TIM.config;
    for (var i = 0; i < parts.length; i += 1) {
      if (!node || typeof node !== "object") return fallback;
      node = node[parts[i]];
    }
    return node === undefined ? fallback : node;
  }

  TIM.setting = value;

  TIM.configReady = fetch("config.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) { return data ? merge(TIM.config, data) : TIM.config; })
    .catch(function () { return TIM.config; });
})();
