// Recast Web UI — Vanilla JS SPA

const API = '/api';
let currentShow = null;
let currentJobId = null;
let currentCutlist = null;
let audioCtx = null;
let audioSource = null;
let ws = null;
let stageStartTime = null;
let stageTimes = {}; // track timing per stage for ETA

// --- Navigation ---

document.querySelectorAll('nav a').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    showView(a.dataset.view);
  });
});

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
  const el = document.getElementById(`view-${name}`);
  if (el) el.style.display = 'block';
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('active', a.dataset.view === name));

  if (name === 'dashboard') loadDashboard();
  if (name === 'log') connectWebSocket();
}

// --- Dashboard ---

async function loadDashboard() {
  const resp = await fetch(`${API}/shows`);
  const shows = await resp.json();
  const container = document.getElementById('shows-list');

  if (shows.length === 0) {
    container.innerHTML = '<p>No shows found. Create a show folder with a show.toml file.</p>';
    return;
  }

  let html = '<table><thead><tr><th>Show</th><th>Jobs</th><th>Last Status</th><th>Actions</th></tr></thead><tbody>';
  for (const show of shows) {
    html += `<tr>
      <td><strong>${esc(show.name)}</strong></td>
      <td>${show.n_jobs}</td>
      <td>${show.last_status ? `<span class="badge ${show.last_status}">${show.last_status}</span>` : '-'}</td>
      <td>
        <button onclick="openShow('${esc(show.name)}')">Jobs</button>
        <button class="secondary" onclick="openShowSettings('${esc(show.name)}')">Settings</button>
      </td>
    </tr>`;
  }
  html += '</tbody></table>';
  container.innerHTML = html;
}

// --- Jobs ---

async function openShow(name) {
  currentShow = name;
  document.getElementById('jobs-title').textContent = `Jobs — ${name}`;
  showView('jobs');
  await loadJobs();
}

async function loadJobs() {
  const resp = await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs`);
  const jobs = await resp.json();
  const tbody = document.getElementById('jobs-table');

  if (jobs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">No jobs yet.</td></tr>';
    return;
  }

  let html = '';
  for (const job of jobs) {
    html += `<tr onclick="openEditor('${job.id}')">
      <td>${esc(job.filename)}</td>
      <td><span class="badge ${job.status}">${job.status}</span></td>
      <td>${job.stage || '-'}</td>
      <td>${new Date(job.created_at).toLocaleString()}</td>
      <td>${job.error ? `<span title="${esc(job.error)}" style="color:var(--red)">Error</span>` : ''}</td>
    </tr>`;
  }
  tbody.innerHTML = html;
}

// --- Episode Editor ---

async function openEditor(jobId) {
  currentJobId = jobId;
  document.getElementById('editor-title').textContent = `Episode Editor`;
  showView('editor');

  // Load job details
  const resp = await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${jobId}`);
  const data = await resp.json();
  document.getElementById('editor-title').textContent = `Editor — ${data.job.filename}`;

  // Load cutlist
  try {
    const clResp = await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${jobId}/cutlist`);
    if (clResp.ok) {
      currentCutlist = await clResp.json();
      renderCutlist();
    }
  } catch (e) { console.log('No cutlist yet'); }

  // Load transcript
  try {
    const trResp = await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${jobId}/transcript`);
    if (trResp.ok) {
      const transcript = await trResp.json();
      renderTranscript(transcript);
    }
  } catch (e) { console.log('No transcript yet'); }

  // Load metadata
  if (data.episode) {
    document.getElementById('meta-title').value = data.episode.title || '';
    document.getElementById('meta-description').value = data.episode.description || '';
    renderChapters(data.episode.chapters || []);
  }

  // Draw waveform
  drawWaveform();
}

function renderCutlist() {
  if (!currentCutlist) return;
  const panel = document.getElementById('cutlist-panel');
  let html = '<table><thead><tr><th>Start</th><th>End</th><th>Duration</th><th>Action</th><th>Source</th><th></th></tr></thead><tbody>';
  for (let i = 0; i < currentCutlist.decisions.length; i++) {
    const d = currentCutlist.decisions[i];
    const cls = d.keep ? 'keep' : 'remove';
    html += `<tr style="opacity:${d.keep ? 1 : 0.6}">
      <td>${fmtTime(d.start)}</td>
      <td>${fmtTime(d.end)}</td>
      <td>${(d.end - d.start).toFixed(1)}s</td>
      <td><span class="badge ${d.keep ? 'done' : 'failed'}">${d.keep ? 'KEEP' : 'REMOVE'}</span></td>
      <td>${d.source || ''} ${d.reason ? `(${d.reason})` : ''}</td>
      <td>
        ${d.keep
          ? `<button onclick="removeCut(${i})" class="secondary" style="padding:2px 8px;font-size:0.8rem">Remove</button>`
          : `<button onclick="restoreCut(${i})" style="padding:2px 8px;font-size:0.8rem">Restore</button>`
        }
      </td>
    </tr>`;
  }
  html += '</tbody></table>';
  panel.innerHTML = html;
}

function renderTranscript(transcript) {
  const panel = document.getElementById('transcript-panel');
  let html = '';
  for (const seg of transcript.segments || []) {
    const removed = currentCutlist && currentCutlist.decisions.some(
      d => !d.keep && d.start <= seg.start && d.end >= seg.end
    );
    html += `<div class="transcript-line ${removed ? 'removed' : ''}" onclick="seekTo(${seg.start})">
      <span class="timestamp">${fmtTime(seg.start)}</span> ${esc(seg.text)}
    </div>`;
  }
  panel.innerHTML = html;
}

function renderChapters(chapters) {
  const container = document.getElementById('chapters-list');
  let html = '';
  for (const ch of chapters) {
    html += `<div style="display:flex;gap:8px;margin-bottom:4px;align-items:center">
      <input type="text" value="${fmtTime(ch.start_time)}" style="width:80px" disabled>
      <input type="text" value="${esc(ch.title)}" style="flex:1">
    </div>`;
  }
  container.innerHTML = html || '<p style="color:var(--text-dim)">No chapters</p>';
}

// --- Cut actions ---

function restoreCut(idx) {
  if (!currentCutlist) return;
  currentCutlist.decisions[idx].keep = true;
  renderCutlist();
  drawWaveform();
}

function removeCut(idx) {
  if (!currentCutlist) return;
  currentCutlist.decisions[idx].keep = false;
  renderCutlist();
  drawWaveform();
}

function restoreAllLLM() {
  if (!currentCutlist) return;
  for (const d of currentCutlist.decisions) {
    if (d.source === 'llm' && !d.keep) d.keep = true;
  }
  renderCutlist();
  drawWaveform();
}

function restoreAllPyannote() {
  if (!currentCutlist) return;
  for (const d of currentCutlist.decisions) {
    if (d.source === 'pyannote' && !d.keep) d.keep = true;
  }
  renderCutlist();
  drawWaveform();
}

// --- Audio ---

function playOriginal() {
  if (!currentShow || !currentJobId) return;
  playAudioUrl(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${currentJobId}/audio?original=true`);
}

function playPreview() {
  if (!currentShow || !currentJobId) return;
  playAudioUrl(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${currentJobId}/audio`);
}

function playAudioUrl(url) {
  stopAudio();
  const audio = new Audio(url);
  audio.play();
  window._currentAudio = audio;
}

function stopAudio() {
  if (window._currentAudio) {
    window._currentAudio.pause();
    window._currentAudio = null;
  }
}

function seekTo(time) {
  if (window._currentAudio) {
    window._currentAudio.currentTime = time;
  }
}

// --- Waveform ---

function drawWaveform() {
  const canvas = document.getElementById('waveform');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.parentElement.clientWidth;
  canvas.width = w;
  canvas.height = 150;

  // Background
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, w, 150);

  if (!currentCutlist || !currentCutlist.total_duration) return;
  const dur = currentCutlist.total_duration;

  // Draw regions
  for (const d of currentCutlist.decisions) {
    const x = (d.start / dur) * w;
    const rw = ((d.end - d.start) / dur) * w;
    if (d.keep) {
      ctx.fillStyle = 'rgba(76,175,80,0.3)'; // green
    } else if (d.source === 'llm') {
      ctx.fillStyle = 'rgba(255,152,0,0.3)'; // orange
    } else if (d.source === 'pyannote') {
      ctx.fillStyle = 'rgba(244,67,54,0.3)'; // red
    } else {
      ctx.fillStyle = 'rgba(102,102,102,0.3)'; // grey
    }
    ctx.fillRect(x, 0, rw, 150);
  }

  // Fake waveform visualization
  ctx.strokeStyle = '#4caf50';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x < w; x++) {
    const y = 75 + Math.sin(x * 0.05) * 30 * Math.random();
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Hover tooltip
  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const t = (mx / w) * dur;
    for (const d of currentCutlist.decisions) {
      if (t >= d.start && t <= d.end) {
        canvas.title = `${fmtTime(d.start)} → ${fmtTime(d.end)} | ${(d.end - d.start).toFixed(1)}s | ${d.reason || (d.keep ? 'speech' : 'removed')} | confidence: ${(d.confidence || 1).toFixed(2)} | source: ${d.source || '-'}`;
        return;
      }
    }
    canvas.title = fmtTime(t);
  };

  // Click to seek
  canvas.onclick = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const t = (mx / w) * dur;
    seekTo(t);
  };
}

// --- Settings ---

async function openShowSettings(name) {
  currentShow = name;
  document.getElementById('settings-title').textContent = `Settings — ${name}`;
  showView('settings');

  const resp = await fetch(`${API}/shows/${encodeURIComponent(name)}/settings`);
  const settings = await resp.json();

  const form = document.getElementById('settings-form');
  let html = '';
  const fields = [
    ['name', 'Show Name', 'text'],
    ['description', 'Description', 'text'],
    ['author', 'Author', 'text'],
    ['language', 'Language', 'text'],
    ['whisper_model', 'Whisper Model', 'text'],
    ['ollama_model', 'Ollama Model', 'text'],
    ['ollama_base_url', 'Ollama URL', 'text'],
    ['join_mode', 'Join Mode', 'select:crossfade,hard_cut,silence'],
    ['crossfade_duration_ms', 'Crossfade (ms)', 'number'],
    ['cut_pad_ms', 'Cut Padding (ms)', 'number'],
    ['min_speech_gap_s', 'Min Speech Gap (s)', 'number'],
    ['min_keep_duration_s', 'Min Keep Duration (s)', 'number'],
    ['llm_confidence_threshold', 'LLM Confidence Threshold', 'number'],
    ['audio_format', 'Audio Format', 'text'],
    ['audio_bitrate', 'Audio Bitrate', 'text'],
    ['feed_base_url', 'Feed Base URL', 'text'],
  ];

  for (const [key, label, type] of fields) {
    const val = settings[key] ?? '';
    html += `<div class="form-group"><label>${label}</label>`;
    if (type.startsWith('select:')) {
      const opts = type.split(':')[1].split(',');
      html += `<select id="setting-${key}">`;
      for (const o of opts) {
        html += `<option value="${o}" ${val === o ? 'selected' : ''}>${o}</option>`;
      }
      html += '</select>';
    } else {
      html += `<input type="${type}" id="setting-${key}" value="${esc(String(val))}"${type === 'number' ? ' step="any"' : ''}>`;
    }
    html += '</div>';
  }

  // Boolean toggles
  html += `<div class="form-group"><label><input type="checkbox" id="setting-auto_publish" ${settings.auto_publish ? 'checked' : ''}> Auto Publish</label></div>`;
  html += `<div class="form-group"><label><input type="checkbox" id="setting-review_mode" ${settings.review_mode ? 'checked' : ''}> Review Mode</label></div>`;

  form.innerHTML = html;
}

async function saveSettings() {
  const settings = {};
  document.querySelectorAll('#settings-form input, #settings-form select').forEach(el => {
    const key = el.id.replace('setting-', '');
    if (el.type === 'checkbox') settings[key] = el.checked;
    else if (el.type === 'number') settings[key] = parseFloat(el.value);
    else settings[key] = el.value;
  });

  await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/settings`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({settings}),
  });
  document.getElementById('settings-status').innerHTML = '<p style="color:var(--green)">Saved!</p>';
}

async function testOllama() {
  const url = document.getElementById('setting-ollama_base_url')?.value || 'http://localhost:11434';
  const resp = await fetch(`${API}/test/ollama?base_url=${encodeURIComponent(url)}`);
  const data = await resp.json();
  const status = document.getElementById('settings-status');
  if (data.status === 'ok') {
    status.innerHTML = `<p style="color:var(--green)">Ollama OK. Models: ${data.models.join(', ')}</p>`;
  } else {
    status.innerHTML = `<p style="color:var(--red)">Ollama error: ${data.error}</p>`;
  }
}

async function testFfmpeg() {
  const resp = await fetch(`${API}/test/ffmpeg`);
  const data = await resp.json();
  const status = document.getElementById('settings-status');
  status.innerHTML = data.available
    ? '<p style="color:var(--green)">ffmpeg found!</p>'
    : '<p style="color:var(--red)">ffmpeg not found on PATH</p>';
}

// --- Editor Actions ---

async function saveEdits() {
  if (!currentCutlist || !currentShow || !currentJobId) return;
  await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${currentJobId}/cutlist`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(currentCutlist),
  });
  alert('Saved!');
}

async function renderPreview() {
  await saveEdits();
  await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${currentJobId}/render`, {method: 'POST'});
  alert('Rendering started. Check the log for progress.');
}

async function approvePublish() {
  await saveEdits();
  await fetch(`${API}/shows/${encodeURIComponent(currentShow)}/jobs/${currentJobId}/publish`, {method: 'POST'});
  alert('Published!');
}

function discardEdits() {
  if (confirm('Discard all edits and reload?')) {
    openEditor(currentJobId);
  }
}

// --- WebSocket ---

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'progress') {
      const now = Date.now();
      // Track stage timing
      if (stageStartTime && data.stage_idx > 1) {
        const elapsed = (now - stageStartTime) / 1000;
        stageTimes[data.stage_idx - 1] = elapsed;
      }
      stageStartTime = now;

      const pct = (data.stage_idx / data.total) * 100;
      document.getElementById('progress-fill').style.width = `${pct}%`;

      // Estimate remaining time
      let eta = '';
      const completedStages = Object.keys(stageTimes).length;
      if (completedStages > 0) {
        const avgTime = Object.values(stageTimes).reduce((a, b) => a + b, 0) / completedStages;
        const remaining = (data.total - data.stage_idx) * avgTime;
        if (remaining > 60) eta = ` — ~${Math.ceil(remaining / 60)}m remaining`;
        else eta = ` — ~${Math.ceil(remaining)}s remaining`;
      }

      document.getElementById('progress-text').textContent =
        `Stage ${data.stage_idx}/${data.total}: ${data.stage}${eta}`;
      addLogEntry(`[${data.stage_idx}/${data.total}] ${data.stage}${eta}`, 'info');
    }
  };

  ws.onclose = () => {
    addLogEntry('WebSocket disconnected. Reconnecting...', 'warn');
    setTimeout(connectWebSocket, 3000);
  };
}

function addLogEntry(text, level = 'info') {
  const container = document.getElementById('log-container');
  const entry = document.createElement('div');
  entry.className = `log-entry ${level}`;
  entry.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  container.appendChild(entry);
  container.scrollTop = container.scrollHeight;
}

// --- Helpers ---

function fmtTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function esc(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Init ---

window.addEventListener('resize', drawWaveform);
loadDashboard();
