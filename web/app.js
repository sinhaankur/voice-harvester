// Voice Harvester web UI — drives the local server (analyze → pick → clone → speak),
// with an Ollama assistant. Vanilla JS, no deps.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const api = (path, body) =>
    fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined)
      .then((r) => r.json());

  let state = { path: "", analysis: null, selectedSpeaker: null, exportedRef: "" };

  // --- env / badges ---
  api("/api/env").then((env) => {
    const b = (label, on) =>
      `<span class="badge"><span class="dot" style="background:${on ? "var(--good)" : "var(--dim)"}"></span>${label}</span>`;
    $("badges").innerHTML =
      b("ffmpeg", env.ffmpeg) + b("Demucs", env.demucs) +
      b("voice engine", env.voice_engine) + b("Ollama", (env.ollama || []).length);
    // languages dropdown
    const sel = $("lang");
    Object.entries(env.languages || {}).forEach(([code, name]) => {
      const o = document.createElement("option"); o.value = code; o.textContent = name; sel.appendChild(o);
    });
    // ollama models
    if ((env.ollama || []).length) {
      $("aiCard").classList.remove("hidden");
      $("aiModel").textContent = "· " + env.ollama[0];
      $("aiCard").dataset.model = env.ollama[0];
    }
    if (!env.voice_engine) $("refLine") && ($("refLine").dataset.warn = "1");
  });

  // --- import ---
  const drop = $("drop");
  drop.addEventListener("click", () => $("file").click());
  $("file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f) { state.path = f.path || f.name; $("path").value = state.path; analyze(); }
  });
  ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f && f.path) { state.path = f.path; $("path").value = f.path; analyze(); }
  });
  $("analyzeBtn").addEventListener("click", () => { state.path = $("path").value.trim(); analyze(); });

  function analyze() {
    if (!state.path) return;
    $("analyzeBtn").innerHTML = '<span class="spin"></span>';
    $("analyzeBtn").disabled = true;
    api("/api/analyze", { path: state.path }).then((res) => {
      $("analyzeBtn").textContent = "Analyze"; $("analyzeBtn").disabled = false;
      if (!res.ok) { alert(res.error || "Analyze failed"); return; }
      state.analysis = res; renderSpeakers(res);
    });
  }

  function renderSpeakers(res) {
    $("speakersCard").classList.remove("hidden");
    $("anaInfo").textContent = `· ${res.duration}s${res.transcribed ? " · transcribed" : ""}`;
    const wrap = $("speakers"); wrap.innerHTML = "";
    (res.speakers || []).forEach((s) => {
      const el = document.createElement("div");
      el.className = "spk";
      el.innerHTML = `<b>Speaker ${s.speaker}</b> <span class="muted">${s.seconds}s · ~${s.avg_pitch}Hz · ${s.likely}</span>`;
      el.onclick = () => { state.selectedSpeaker = s.speaker; document.querySelectorAll(".spk").forEach(x => x.classList.remove("sel")); el.classList.add("sel"); renderSegments(res, s.speaker); };
      wrap.appendChild(el);
    });
    if (res.speakers && res.speakers[0]) wrap.firstChild.click();
  }

  function renderSegments(res, speaker) {
    const c = $("segments"); c.innerHTML = "";
    res.segments.filter(s => s.speaker === speaker).forEach((s) => {
      const el = document.createElement("div"); el.className = "seg";
      el.innerHTML = `<span class="tag">${s.speaker}</span>
        <span class="meta">${s.start}–${s.end}s · ${s.duration}s · ~${s.pitch_hz}Hz</span>
        <span style="flex:1">${s.text || ""}</span>`;
      c.appendChild(el);
    });
  }

  $("exportBtn").addEventListener("click", () => {
    if (!state.selectedSpeaker) return;
    $("exportBtn").innerHTML = '<span class="spin"></span> Extracting…'; $("exportBtn").disabled = true;
    $("exportMsg").textContent = "";
    api("/api/export-speaker", { path: state.path, speaker: state.selectedSpeaker }).then((res) => {
      $("exportBtn").textContent = "Export selected speaker's voice"; $("exportBtn").disabled = false;
      if (!res.ok) { $("exportMsg").textContent = res.error || "failed"; return; }
      state.exportedRef = res.out;
      $("exportMsg").innerHTML = `✓ ${res.duration}s of clean voice → <code>${res.out}</code>`;
      $("cloneCard").classList.remove("hidden");
      $("refLine").textContent = `Cloning from Speaker ${state.selectedSpeaker} (${res.duration}s).`;
    });
  });

  $("cloneBtn").addEventListener("click", () => {
    const text = $("cloneText").value.trim();
    if (!text || !state.exportedRef) return;
    $("cloneBtn").innerHTML = '<span class="spin"></span>'; $("cloneBtn").disabled = true;
    $("cloneOut").textContent = "Rendering…";
    api("/api/clone", { ref: state.exportedRef, text, language: $("lang").value || undefined }).then((res) => {
      $("cloneBtn").textContent = "Speak"; $("cloneBtn").disabled = false;
      if (!res.ok) { $("cloneOut").textContent = res.error || "failed"; return; }
      $("cloneOut").innerHTML = `✓ spoken (${res.language}) <audio controls autoplay src="/file?path=${encodeURIComponent(res.out)}"></audio>`;
    });
  });

  // --- AI assistant (Ollama) ---
  $("aiBtn").addEventListener("click", () => {
    const prompt = $("aiPrompt").value.trim();
    if (!prompt) return;
    $("aiSpin").innerHTML = '<span class="spin"></span>';
    api("/api/ask", { prompt, model: $("aiCard").dataset.model }).then((res) => {
      $("aiSpin").innerHTML = "";
      $("aiReply").textContent = res.reply || "";
    });
  });
})();
