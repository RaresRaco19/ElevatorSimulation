// Elevator simulation playback — no build step, no dependencies.
// Reads config.json / positions_log.csv / requests.csv / passenger_log.csv /
// passenger_stats.json from a chosen run directory and renders an SVG line chart
// (time x floor), a scrubbing/playback UI, a request log, a Passenger Times panel
// (waiting time + total time per passenger, once each trip completes), and an
// always-visible run summary (count, min/avg/max wait & total time).
//
// The run dropdown is populated by parsing the directory-listing pages that
// `python -m http.server` serves for `outputs/` and `outputs/examples/` (see
// discoverRuns()) — no manifest file to keep in sync, any run you generate shows up
// automatically. This only works when the static server actually emits a directory
// listing; if it doesn't, DEFAULT_RUN_DIR is used as the sole fallback option.

const DEFAULT_RUN_DIR = "../outputs/examples/round_robin_scan_demo";
const RUN_ROOTS = ["../outputs/", "../outputs/examples/"];
const TICK_MS = 300;
const PALETTE = ["#4fd1c5", "#f6ad55", "#f687b3", "#63b3ed", "#68d391", "#fc8181"];

const svg = document.getElementById("chart");
const legendEl = document.getElementById("legend");
const runInfoEl = document.getElementById("run-info");
const runPicker = document.getElementById("run-picker");
const runPickerBtn = document.getElementById("run-picker-btn");
const runPickerLabel = document.getElementById("run-picker-label");
const runPickerList = document.getElementById("run-picker-list");
const playBtn = document.getElementById("play-btn");
const scrubber = document.getElementById("scrubber");
const timeReadout = document.getElementById("time-readout");
const logBody = document.getElementById("log-body");
const accuracyBody = document.getElementById("accuracy-body");
const summaryCard = document.getElementById("summary-card");
const statCount = document.getElementById("stat-count");
const statWait = document.getElementById("stat-wait");
const statTotal = document.getElementById("stat-total");

const MARGIN = { top: 12, right: 16, bottom: 30, left: 36 };
const VIEW_W = 900;
const VIEW_H = 420;
const plotW = VIEW_W - MARGIN.left - MARGIN.right;
const plotH = VIEW_H - MARGIN.top - MARGIN.bottom;

let state = {
  floors: 0,
  elevatorIds: [],
  times: [],
  series: {}, // elevatorId -> [floor, floor, ...] indexed by time
  requests: [], // {time, id, source, dest}
  passengers: [], // {id, elevator, pickupTime, actualWait}
  elevatorById: new Map(), // passenger id -> elevator id, for the Requests table
  visible: new Set(),
  currentTime: 0,
  maxTime: 0,
  playing: false,
  timer: null,
};

function parseCsv(text) {
  const lines = text.trim().split("\n").map((l) => l.trim()).filter(Boolean);
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    const row = {};
    headers.forEach((h, i) => (row[h] = cells[i]));
    return row;
  });
}

// Parses a directory-listing HTML page (as served by `python -m http.server`) into
// the list of subdirectory names it links to (trailing "/", excludes files and "..").
async function listDir(path) {
  const res = await fetch(path);
  if (!res.ok) return [];
  const html = await res.text();
  const doc = new DOMParser().parseFromString(html, "text/html");
  return Array.from(doc.querySelectorAll("a"))
    .map((a) => a.getAttribute("href"))
    .filter((href) => href && href.endsWith("/") && !href.startsWith(".."));
}

// Finds every run directory under RUN_ROOTS by listing them and keeping only entries
// that actually contain a config.json (which filters out things like a stray
// examples/README.md or an unrelated subfolder with no extra bookkeeping needed).
async function discoverRuns() {
  const candidates = [];
  for (const root of RUN_ROOTS) {
    const entries = await listDir(root).catch(() => []);
    for (const entry of entries) {
      candidates.push((root + entry).replace(/\/$/, ""));
    }
  }
  const checked = await Promise.all(
    candidates.map(async (dir) => {
      try {
        const res = await fetch(`${dir}/config.json`, { method: "HEAD" });
        return res.ok ? dir : null;
      } catch {
        return null;
      }
    })
  );
  return [...new Set(checked.filter(Boolean))].sort();
}

function runLabel(dir) {
  return dir.replace("../outputs/", "");
}

let currentRunDir = null;

function closePicker() {
  runPickerList.hidden = true;
  runPickerBtn.setAttribute("aria-expanded", "false");
}

function openPicker() {
  runPickerList.hidden = false;
  runPickerBtn.setAttribute("aria-expanded", "true");
}

function selectRun(dir) {
  currentRunDir = dir;
  runPickerLabel.textContent = runLabel(dir);
  Array.from(runPickerList.children).forEach((li) => {
    li.classList.toggle("selected", li.dataset.dir === dir);
  });
}

function populateRunPicker(runs, selected) {
  runPickerList.innerHTML = "";
  runs.forEach((dir) => {
    const li = document.createElement("li");
    li.className = "run-picker-option";
    li.setAttribute("role", "option");
    li.dataset.dir = dir;
    li.textContent = runLabel(dir);
    li.addEventListener("click", () => {
      closePicker();
      if (dir === currentRunDir) return;
      stopPlaying();
      selectRun(dir);
      loadRun(dir).catch((err) => {
        runInfoEl.textContent = "Failed to load run data — see console.";
        console.error(err);
      });
    });
    runPickerList.appendChild(li);
  });
  selectRun(selected);
}

runPickerBtn.addEventListener("click", () => {
  if (runPickerList.hidden) {
    openPicker();
  } else {
    closePicker();
  }
});

document.addEventListener("click", (e) => {
  if (!runPicker.contains(e.target)) closePicker();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePicker();
});

async function loadRun(runDir) {
  const [config, positionsText, requestsText, passengerLogText, stats] = await Promise.all([
    fetch(`${runDir}/config.json`).then((r) => r.json()),
    fetch(`${runDir}/positions_log.csv`).then((r) => r.text()),
    fetch(`${runDir}/requests.csv`).then((r) => r.text()),
    fetch(`${runDir}/passenger_log.csv`).then((r) => r.text()),
    fetch(`${runDir}/passenger_stats.json`).then((r) => r.json()),
  ]);

  const positionRows = parseCsv(positionsText);
  // Derived from the log itself (not config.elevators) so a stale/mismatched config
  // can't produce elevators with no position data (and NaN chart lines).
  const elevatorIds = Object.keys(positionRows[0]).filter((k) => k !== "time");
  const times = positionRows.map((r) => Number(r.time));
  const series = {};
  elevatorIds.forEach((id) => {
    series[id] = positionRows.map((r) => Number(r[id]));
  });

  const requests = parseCsv(requestsText)
    .map((r) => ({
      time: Number(r.time),
      id: r.id,
      source: Number(r.source),
      dest: Number(r.dest),
    }))
    .sort((a, b) => a.time - b.time);

  const passengers = parseCsv(passengerLogText)
    .map((r) => ({
      id: r.id,
      elevator: r.elevator,
      pickupTime: Number(r.pickup_time),
      actualWait: Number(r.actual_wait_time),
      dropoffTime: Number(r.dropoff_time),
      totalTime: Number(r.total_time),
    }))
    .sort((a, b) => a.dropoffTime - b.dropoffTime);

  state.floors = config.floors;
  state.elevatorIds = elevatorIds;
  state.times = times;
  state.series = series;
  state.requests = requests;
  state.passengers = passengers;
  state.elevatorById = new Map(passengers.map((p) => [p.id, p.elevator]));
  state.visible = new Set(elevatorIds);
  state.maxTime = times[times.length - 1];
  state.currentTime = 0;

  runInfoEl.textContent =
    `${config.scheduler} · ${config.floors} floors · ` +
    `${elevatorIds.length} elevators · capacity ${config.capacity}`;
  if (config.elevators && config.elevators.length !== elevatorIds.length) {
    console.warn(
      `config.json declares ${config.elevators.length} elevators but positions_log.csv only has data for ${elevatorIds.length}; using the log.`
    );
  }

  scrubber.max = String(state.maxTime);
  scrubber.value = "0";

  renderSummary(stats);
  buildLegend();
  buildStaticChart();
  render();
}

function renderSummary(stats) {
  const fmt = (s) => `${s.min} / ${s.avg.toFixed(1)} / ${s.max}`;
  statCount.textContent = stats.count;
  statWait.textContent = fmt(stats.wait_time);
  statTotal.textContent = fmt(stats.total_time);
  summaryCard.hidden = false;
}

function buildLegend() {
  legendEl.innerHTML = "";
  state.elevatorIds.forEach((id, i) => {
    const color = PALETTE[i % PALETTE.length];
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "legend-chip";
    chip.dataset.id = id;
    chip.innerHTML = `<span class="swatch" style="background:${color}"></span>${id}`;
    chip.addEventListener("click", () => {
      if (state.visible.has(id)) {
        state.visible.delete(id);
        chip.classList.add("off");
      } else {
        state.visible.add(id);
        chip.classList.remove("off");
      }
      updateLines();
    });
    legendEl.appendChild(chip);
  });
}

function xScale(t) {
  return MARGIN.left + (state.maxTime === 0 ? 0 : (t / state.maxTime) * plotW);
}

function yScale(floor) {
  const span = state.floors - 1;
  const frac = span === 0 ? 0 : (floor - 1) / span;
  return MARGIN.top + (1 - frac) * plotH;
}

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

function buildStaticChart() {
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);

  // horizontal gridlines + floor labels (every floor)
  for (let f = 1; f <= state.floors; f++) {
    const y = yScale(f);
    svg.appendChild(
      svgEl("line", { class: "grid-line", x1: MARGIN.left, x2: VIEW_W - MARGIN.right, y1: y, y2: y })
    );
    svg.appendChild(
      svgEl("text", { class: "axis-label", x: MARGIN.left - 8, y: y + 3, "text-anchor": "end" })
    ).textContent = f;
  }

  // vertical gridlines + time labels
  const xStep = Math.max(1, Math.ceil(state.maxTime / 12));
  for (let t = 0; t <= state.maxTime; t += xStep) {
    const x = xScale(t);
    svg.appendChild(
      svgEl("line", { class: "grid-line", x1: x, x2: x, y1: MARGIN.top, y2: VIEW_H - MARGIN.bottom })
    );
    svg.appendChild(
      svgEl("text", { class: "axis-label", x: x, y: VIEW_H - MARGIN.bottom + 16, "text-anchor": "middle" })
    ).textContent = t;
  }

  // one path per elevator
  state.elevatorIds.forEach((id, i) => {
    const path = svgEl("path", {
      class: "elevator-line",
      id: `line-${id}`,
      stroke: PALETTE[i % PALETTE.length],
      d: "",
    });
    svg.appendChild(path);
  });

  svg.appendChild(
    svgEl("line", { class: "playhead", id: "playhead", x1: xScale(0), x2: xScale(0), y1: MARGIN.top, y2: VIEW_H - MARGIN.bottom })
  );
}

function updateLines() {
  state.elevatorIds.forEach((id) => {
    const path = document.getElementById(`line-${id}`);
    const visible = state.visible.has(id);
    path.style.opacity = visible ? "1" : "0";
    if (!visible) return;
    const values = state.series[id];
    let d = "";
    for (let t = 0; t <= state.currentTime; t++) {
      const x = xScale(state.times[t]);
      const y = yScale(values[t]);
      d += (t === 0 ? "M" : "L") + x + "," + y + " ";
    }
    path.setAttribute("d", d.trim());
  });

  const playhead = document.getElementById("playhead");
  const x = xScale(state.currentTime);
  playhead.setAttribute("x1", x);
  playhead.setAttribute("x2", x);
}

function updateLog() {
  const rows = state.requests.filter((r) => r.time <= state.currentTime);
  if (rows.length === 0) {
    logBody.innerHTML = `<tr><td colspan="5" class="log-empty">No requests submitted yet.</td></tr>`;
    return;
  }
  logBody.innerHTML = rows
    .map((r) => {
      const elevator = state.elevatorById.get(r.id) ?? "–";
      return `<tr><td>${r.time}</td><td>${r.id}</td><td>${r.source}</td><td>${r.dest}</td><td>${elevator}</td></tr>`;
    })
    .join("");
}

function updateAccuracyLog() {
  const rows = state.passengers.filter((p) => p.dropoffTime <= state.currentTime);
  if (rows.length === 0) {
    accuracyBody.innerHTML = `<tr><td colspan="4" class="log-empty">No completed trips yet.</td></tr>`;
    return;
  }
  accuracyBody.innerHTML = rows
    .map(
      (p) =>
        `<tr><td>${p.id}</td><td>${p.actualWait}</td><td class="total-time-value">${p.totalTime}</td><td>${p.elevator}</td></tr>`
    )
    .join("");
}

function render() {
  scrubber.value = String(state.currentTime);
  timeReadout.textContent = `Time ${state.currentTime} / ${state.maxTime}`;
  updateLines();
  updateLog();
  updateAccuracyLog();
}

function stopPlaying() {
  state.playing = false;
  playBtn.textContent = "Run";
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

function startPlaying() {
  if (state.currentTime >= state.maxTime) state.currentTime = 0;
  state.playing = true;
  playBtn.textContent = "Pause";
  state.timer = setInterval(() => {
    state.currentTime += 1;
    if (state.currentTime >= state.maxTime) {
      state.currentTime = state.maxTime;
      render();
      stopPlaying();
      return;
    }
    render();
  }, TICK_MS);
}

playBtn.addEventListener("click", () => {
  if (state.playing) {
    stopPlaying();
  } else {
    startPlaying();
  }
});

scrubber.addEventListener("input", (e) => {
  stopPlaying();
  state.currentTime = Number(e.target.value);
  render();
});

async function init() {
  let runs = [];
  try {
    runs = await discoverRuns();
  } catch (err) {
    console.warn("Run discovery failed (server may not support directory listings); falling back to the default run only.", err);
  }
  if (runs.length === 0) runs = [DEFAULT_RUN_DIR];

  const initial = runs.includes(DEFAULT_RUN_DIR) ? DEFAULT_RUN_DIR : runs[0];
  populateRunPicker(runs, initial);
  await loadRun(initial);
}

init().catch((err) => {
  runInfoEl.textContent = "Failed to load run data — see console.";
  console.error(err);
});
