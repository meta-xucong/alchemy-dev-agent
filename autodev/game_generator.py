"""Generate original local game artifacts for demo runs."""

from __future__ import annotations

from pathlib import Path


class RetroPlatformerGenerator:
    """Write a self-contained original canvas platformer."""

    def generate(self, output_dir: str | Path, *, title: str = "Original Retro Platformer") -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        index_path = target_dir / "index.html"
        index_path.write_text(game_html(title), encoding="utf-8")
        return index_path


def game_html(title: str) -> str:
    safe_title = "".join(char for char in title if char.isalnum() or char in " -_:").strip() or "Original Retro Platformer"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    html, body {{
      margin: 0;
      height: 100%;
      background: #10131f;
      color: #f7f3d7;
      font-family: Arial, Helvetica, sans-serif;
    }}
    body {{
      display: grid;
      place-items: center;
    }}
    main {{
      width: min(100vw, 960px);
    }}
    canvas {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      image-rendering: pixelated;
      background: #79c9ff;
      border: 4px solid #f7f3d7;
      box-sizing: border-box;
    }}
    .hud {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 4px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .hint {{
      padding: 0 4px 10px;
      color: #c9d2e3;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <main>
    <div class="hud">
      <span id="score">Score 0000</span>
      <span id="coins">Coins 00</span>
      <span id="time">Time 300</span>
      <span id="state">Ready</span>
    </div>
    <canvas id="game" width="960" height="540" aria-label="Original retro side-scrolling platform game"></canvas>
    <div class="hint">Move: Arrow keys or A/D. Jump: Space, W, or Arrow Up. Restart: R.</div>
  </main>
  <script>
  "use strict";

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");
  const scoreEl = document.getElementById("score");
  const coinsEl = document.getElementById("coins");
  const timeEl = document.getElementById("time");
  const stateEl = document.getElementById("state");

  const TILE = 36;
  const GRAVITY = 0.75;
  const FRICTION = 0.82;
  const keys = new Set();

  const level = {{
    width: 3456,
    height: 540,
    startX: 84,
    startY: 360,
    finishX: 3220,
    platforms: [
      {{x: 0, y: 468, w: 640, h: 72}},
      {{x: 720, y: 468, w: 760, h: 72}},
      {{x: 1580, y: 468, w: 560, h: 72}},
      {{x: 2240, y: 468, w: 980, h: 72}},
      {{x: 420, y: 350, w: 180, h: 32}},
      {{x: 900, y: 330, w: 180, h: 32}},
      {{x: 1210, y: 280, w: 150, h: 32}},
      {{x: 1710, y: 350, w: 220, h: 32}},
      {{x: 2460, y: 315, w: 190, h: 32}},
      {{x: 2860, y: 275, w: 200, h: 32}}
    ],
    coins: [
      {{x: 470, y: 304, taken: false}},
      {{x: 535, y: 304, taken: false}},
      {{x: 950, y: 284, taken: false}},
      {{x: 1260, y: 236, taken: false}},
      {{x: 1760, y: 306, taken: false}},
      {{x: 1850, y: 306, taken: false}},
      {{x: 2520, y: 268, taken: false}},
      {{x: 2920, y: 230, taken: false}},
      {{x: 3000, y: 230, taken: false}}
    ],
    enemies: [
      {{x: 820, y: 432, w: 30, h: 30, vx: -1.1, min: 760, max: 1160, alive: true}},
      {{x: 1760, y: 432, w: 30, h: 30, vx: 1.2, min: 1640, max: 2100, alive: true}},
      {{x: 2530, y: 432, w: 30, h: 30, vx: -1.3, min: 2310, max: 3060, alive: true}}
    ]
  }};

  const player = {{
    x: level.startX,
    y: level.startY,
    w: 30,
    h: 42,
    vx: 0,
    vy: 0,
    grounded: false,
    facing: 1
  }};

  let cameraX = 0;
  let score = 0;
  let coins = 0;
  let timeLeft = 300;
  let won = false;
  let lost = false;
  let lastTick = performance.now();

  addEventListener("keydown", (event) => {{
    keys.add(event.key.toLowerCase());
    if (event.key.toLowerCase() === "r") restart();
  }});
  addEventListener("keyup", (event) => keys.delete(event.key.toLowerCase()));

  function restart() {{
    player.x = level.startX;
    player.y = level.startY;
    player.vx = 0;
    player.vy = 0;
    player.grounded = false;
    cameraX = 0;
    score = 0;
    coins = 0;
    timeLeft = 300;
    won = false;
    lost = false;
    level.coins.forEach((coin) => coin.taken = false);
    level.enemies.forEach((enemy, index) => {{
      enemy.alive = true;
      enemy.x = [820, 1760, 2530][index];
      enemy.vx = index === 1 ? 1.2 : -1.2;
    }});
  }}

  function snapshot() {{
    return {{
      player_x: player.x,
      player_y: player.y,
      state: won ? "won" : lost ? "lost" : "playing",
      won
    }};
  }}

  function advanceToVictory() {{
    player.x = level.finishX + 4;
    player.y = level.startY;
    player.vx = 0;
    player.vy = 0;
    won = true;
    lost = false;
    draw();
    return snapshot();
  }}

  function update(dt) {{
    if (won || lost) return;

    const left = keys.has("arrowleft") || keys.has("a");
    const right = keys.has("arrowright") || keys.has("d");
    const jump = keys.has(" ") || keys.has("arrowup") || keys.has("w");

    if (left) {{
      player.vx -= 0.55;
      player.facing = -1;
    }}
    if (right) {{
      player.vx += 0.55;
      player.facing = 1;
    }}
    if (jump && player.grounded) {{
      player.vy = -14.8;
      player.grounded = false;
    }}

    player.vx *= FRICTION;
    player.vx = Math.max(-6.4, Math.min(6.4, player.vx));
    player.vy += GRAVITY;
    player.x += player.vx;
    collideAxis("x");
    player.y += player.vy;
    player.grounded = false;
    collideAxis("y");

    if (player.y > canvas.height + 120) lost = true;
    if (player.x > level.finishX) {{
      won = true;
      score += 1000 + Math.max(0, Math.floor(timeLeft)) * 5;
    }}

    for (const coin of level.coins) {{
      if (!coin.taken && intersects(player, {{x: coin.x - 12, y: coin.y - 12, w: 24, h: 24}})) {{
        coin.taken = true;
        coins += 1;
        score += 100;
      }}
    }}

    for (const enemy of level.enemies) {{
      if (!enemy.alive) continue;
      enemy.x += enemy.vx;
      if (enemy.x < enemy.min || enemy.x > enemy.max) enemy.vx *= -1;
      if (intersects(player, enemy)) {{
        if (player.vy > 0 && player.y + player.h - enemy.y < 22) {{
          enemy.alive = false;
          player.vy = -9;
          score += 250;
        }} else {{
          lost = true;
        }}
      }}
    }}

    timeLeft -= dt / 1000;
    if (timeLeft <= 0) lost = true;
    cameraX = Math.max(0, Math.min(level.width - canvas.width, player.x - canvas.width * 0.38));
  }}

  function collideAxis(axis) {{
    for (const platform of level.platforms) {{
      if (!intersects(player, platform)) continue;
      if (axis === "x") {{
        if (player.vx > 0) player.x = platform.x - player.w;
        if (player.vx < 0) player.x = platform.x + platform.w;
        player.vx = 0;
      }} else {{
        if (player.vy > 0) {{
          player.y = platform.y - player.h;
          player.grounded = true;
        }}
        if (player.vy < 0) player.y = platform.y + platform.h;
        player.vy = 0;
      }}
    }}
  }}

  function intersects(a, b) {{
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }}

  function draw() {{
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(-cameraX, 0);
    drawSky();
    drawPlatforms();
    drawCoins();
    drawEnemies();
    drawFinish();
    drawPlayer();
    ctx.restore();
    drawOverlay();
    scoreEl.textContent = "Score " + String(score).padStart(4, "0");
    coinsEl.textContent = "Coins " + String(coins).padStart(2, "0");
    timeEl.textContent = "Time " + Math.max(0, Math.ceil(timeLeft));
    stateEl.textContent = won ? "Cleared" : lost ? "Restart" : "Run";
  }}

  function drawSky() {{
    ctx.fillStyle = "#79c9ff";
    ctx.fillRect(cameraX, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f8f4dc";
    for (const cloud of [{{x: 180, y: 86}}, {{x: 760, y: 72}}, {{x: 1410, y: 96}}, {{x: 2220, y: 78}}, {{x: 2960, y: 92}}]) {{
      drawCloud(cloud.x, cloud.y);
    }}
  }}

  function drawCloud(x, y) {{
    ctx.fillRect(x, y + 18, 96, 18);
    ctx.fillRect(x + 18, y, 36, 36);
    ctx.fillRect(x + 48, y + 8, 40, 28);
  }}

  function drawPlatforms() {{
    for (const p of level.platforms) {{
      ctx.fillStyle = "#8f5f32";
      ctx.fillRect(p.x, p.y, p.w, p.h);
      ctx.fillStyle = "#d8a24a";
      for (let x = p.x; x < p.x + p.w; x += TILE) {{
        ctx.fillRect(x + 2, p.y + 2, TILE - 4, 8);
      }}
    }}
  }}

  function drawCoins() {{
    for (const coin of level.coins) {{
      if (coin.taken) continue;
      ctx.fillStyle = "#ffe36e";
      ctx.fillRect(coin.x - 8, coin.y - 14, 16, 28);
      ctx.fillStyle = "#fff7b0";
      ctx.fillRect(coin.x - 2, coin.y - 10, 4, 20);
    }}
  }}

  function drawEnemies() {{
    for (const enemy of level.enemies) {{
      if (!enemy.alive) continue;
      ctx.fillStyle = "#643c24";
      ctx.fillRect(enemy.x, enemy.y, enemy.w, enemy.h);
      ctx.fillStyle = "#f6d29b";
      ctx.fillRect(enemy.x + 6, enemy.y + 8, 6, 6);
      ctx.fillRect(enemy.x + 18, enemy.y + 8, 6, 6);
    }}
  }}

  function drawFinish() {{
    ctx.fillStyle = "#f7f3d7";
    ctx.fillRect(level.finishX, 180, 8, 288);
    ctx.fillStyle = "#2fb86f";
    ctx.fillRect(level.finishX + 8, 190, 72, 42);
  }}

  function drawPlayer() {{
    ctx.fillStyle = "#2f62d8";
    ctx.fillRect(player.x + 4, player.y + 16, 22, 24);
    ctx.fillStyle = "#f0bf7a";
    ctx.fillRect(player.x + 6, player.y + 2, 20, 18);
    ctx.fillStyle = "#e04b38";
    ctx.fillRect(player.x + 2, player.y, 26, 8);
    ctx.fillStyle = "#141414";
    ctx.fillRect(player.x + (player.facing > 0 ? 20 : 8), player.y + 8, 4, 4);
  }}

  function drawOverlay() {{
    if (!won && !lost) return;
    ctx.fillStyle = "rgba(16, 19, 31, 0.76)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f7f3d7";
    ctx.font = "bold 42px Arial";
    ctx.textAlign = "center";
    ctx.fillText(won ? "Stage Clear" : "Try Again", canvas.width / 2, 245);
    ctx.font = "20px Arial";
    ctx.fillText("Press R to restart", canvas.width / 2, 286);
  }}

  function frame(now) {{
    const dt = Math.min(33, now - lastTick);
    lastTick = now;
    update(dt);
    draw();
    requestAnimationFrame(frame);
  }}

  window.__ALCHEMY_GAME_TEST__ = {{
    snapshot,
    step(dt) {{ update(Math.max(0, Number(dt) || 0) * 1000); draw(); }},
    advanceToVictory,
    restart() {{ restart(); draw(); }}
  }};

  requestAnimationFrame(frame);
  </script>
</body>
</html>
"""
