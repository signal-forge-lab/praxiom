"use strict";

const $ = (id) => document.getElementById(id);
let frameVersion = null;

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function formatJstSeconds(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return text(value);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type) => parts.find((item) => item.type === type)?.value || "00";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}:${part("second")}`;
}

function countObject(value) {
  return value && typeof value === "object"
    ? Object.values(value).reduce((sum, item) => sum + (Number(item) || 0), 0)
    : 0;
}

function renderMeta(frame) {
  const root = $("frameMeta");
  root.replaceChildren();
  if (!frame.available) return;
  const rows = [
    ["Captured", formatJstSeconds(frame.captured_at)],
    ["Size", `${text(frame.width)} × ${text(frame.height)}`],
    ["Revision", frame.revision],
  ];
  for (const [label, value] of rows) {
    const box = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = text(value);
    box.append(dt, dd);
    root.append(box);
  }
}

function renderTimeline(activity) {
  const root = $("timeline");
  root.replaceChildren();
  if (!Array.isArray(activity) || activity.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "RunJournal eventはまだありません。";
    root.append(empty);
    return;
  }
  for (const event of [...activity].reverse()) {
    const row = document.createElement("div");
    row.className = "event";
    const seq = document.createElement("span");
    seq.className = "seq";
    seq.textContent = `#${text(event.seq, "?")}`;
    const kind = document.createElement("strong");
    kind.className = "kind";
    kind.textContent = text(event.event_type, "event");
    const status = document.createElement("span");
    status.className = "status";
    status.textContent = text(event.status, event.phase || "—");
    const detail = document.createElement("span");
    detail.className = "detail";
    const duration = event.duration_ms === undefined ? "" : `${Number(event.duration_ms).toFixed(1)}ms`;
    detail.textContent = duration || text(event.effect || event.outcome || event.error_code, "");
    row.append(seq, kind, status, detail);
    root.append(row);
  }
}

function render(snapshot) {
  $("runState").textContent = snapshot.run?.available ? (snapshot.run.completed ? "DONE" : "ACTIVE") : "NO RUN";
  $("frameState").textContent = snapshot.frame?.available ? "READY" : "EMPTY";
  $("generatedAt").textContent = formatJstSeconds(snapshot.generated_at);

  const frame = snapshot.frame || { available: false };
  const img = $("currentFrame");
  const empty = $("frameEmpty");
  img.hidden = !frame.available;
  empty.hidden = frame.available;
  if (frame.available && frame.captured_at !== frameVersion) {
    frameVersion = frame.captured_at;
    img.src = `/api/frame?v=${encodeURIComponent(frameVersion)}`;
  }
  renderMeta(frame);

  const runtime = snapshot.runtime || {};
  $("runtimeState").textContent = runtime.available ? text(runtime.status, text(runtime.event_type)) : "NO EVIDENCE";
  $("runtimeDetail").textContent = runtime.available
    ? [text(runtime.event_type), runtime.duration_ms === undefined ? null : `${Number(runtime.duration_ms).toFixed(1)}ms`].filter(Boolean).join(" · ")
    : "既存Telemetryから最後の状態を表示します。";

  const ai = snapshot.ai_state || {};
  $("policyState").textContent = ai.available ? text(ai.actual_policy, "RECORDED") : "NO DECISION";
  $("policyDetail").textContent = ai.policy_recommendation
    ? `Shadow: ${text(ai.policy_recommendation)} · Actual: ${text(ai.actual_policy)}`
    : "Shadow recommendationは実行権限を持ちません。";
  $("learningCount").textContent = text(ai.learning_records_window, "0");
  $("errorCount").textContent = String(countObject(snapshot.diagnostics?.errors));
  const human = snapshot.human_channel || {};
  const counts = human.counts || {};
  $("humanState").textContent = text(human.state, "NOT PROJECTED");
  $("humanDetail").textContent = `Teaching ${text(counts.teachings, "0")} · Learned ${text(counts.learned_teachings, "0")} · Open questions ${text(counts.open_questions, "0")}`;
  renderQuestions(human.questions || []);
  renderTimeline(snapshot.activity);
}

function renderQuestions(questions) {
  const root = $("humanQuestions");
  root.replaceChildren();
  const open = Array.isArray(questions) ? questions.filter((item) => item.state === "open") : [];
  for (const question of open) {
    const row = document.createElement("div");
    row.className = "event";
    const label = document.createElement("strong");
    label.className = "kind";
    label.textContent = "QUESTION";
    const prompt = document.createElement("span");
    prompt.className = "detail";
    prompt.textContent = text(question.prompt);
    const answer = document.createElement("button");
    answer.type = "button";
    answer.className = "compact-button";
    answer.textContent = "Answer";
    answer.addEventListener("click", async () => {
      const value = window.prompt(question.prompt);
      if (!value) return;
      await postJson("/api/human-answer", {
        question_id: question.question_id,
        text: value,
        teaching_kind: "other",
      });
      await refresh();
    });
    row.append(label, prompt, answer);
    root.append(row);
  }
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const value = await response.json();
  if (!response.ok || !value.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}

async function refresh() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    $("runState").textContent = "OFFLINE";
    console.error("monitor refresh failed", error);
  }
}

for (const button of document.querySelectorAll("[data-preview]")) {
  button.addEventListener("click", () => {
    const mode = button.dataset.preview;
    $("preview").className = `preview ${mode}`;
    for (const peer of document.querySelectorAll("[data-preview]")) {
      peer.classList.toggle("is-selected", peer === button);
    }
  });
}

$("submitTeaching").addEventListener("click", async () => {
  const content = $("teachingText").value.trim();
  if (!content) return;
  try {
    const value = await postJson("/api/human-teaching", {
      text: content,
      teaching_kind: $("teachingKind").value,
    });
    $("teachingResult").textContent = `Saved ${value.teaching_id}`;
    $("teachingText").value = "";
    await refresh();
  } catch (error) {
    $("teachingResult").textContent = `Error: ${error.message}`;
  }
});

refresh();
setInterval(refresh, 1000);
