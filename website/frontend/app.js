/* Greenfield platform SPA — no build step, vanilla JS. */

const state = {
  role: "user",
  agents: [],
  agentId: null,
  threads: JSON.parse(localStorage.getItem("gf_threads") || "{}"),
  chatHistory: JSON.parse(localStorage.getItem("gf_chat_history") || "{}"),
  pendingAttachments: [],
  hitlWatcher: null,
  adminTab: "tools",
  pollTimer: null,
};

const $ = (sel) => document.querySelector(sel);
const api = async (path, options = {}) => {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
    body: options.body instanceof FormData ? options.body : (options.body ? JSON.stringify(options.body) : undefined),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
};

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function renderMarkdown(rawText) {
  if (!rawText) return "";
  const text = String(rawText);

  // If marked.js is available in window, configure and parse with GFM
  if (typeof window.marked !== "undefined" && window.marked && typeof window.marked.parse === "function") {
    try {
      window.marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
      });
      return window.marked.parse(text);
    } catch (e) {
      console.warn("marked.js parse error, falling back to built-in renderer:", e);
    }
  }

  // Built-in Pure JS Markdown Parser Fallback
  let out = esc(text);

  // Code blocks ```lang\ncode\n```
  out = out.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="md-code-block"><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code `code`
  out = out.replace(/`([^`\n]+)`/g, '<code class="md-inline-code">$1</code>');

  // Blockquotes (> quote)
  out = out.replace(/^(?:&gt;|>)[ \t]?(.*)$/gm, '<blockquote class="md-quote">$1</blockquote>');

  // Headers (# H1, ## H2, ### H3, #### H4)
  out = out.replace(/^###### (.*$)/gm, '<h6 class="md-h6">$1</h6>');
  out = out.replace(/^##### (.*$)/gm, '<h5 class="md-h5">$1</h5>');
  out = out.replace(/^#### (.*$)/gm, '<h4 class="md-h4">$1</h4>');
  out = out.replace(/^### (.*$)/gm, '<h3 class="md-h3">$1</h3>');
  out = out.replace(/^## (.*$)/gm, '<h2 class="md-h2">$1</h2>');
  out = out.replace(/^# (.*$)/gm, '<h1 class="md-h1">$1</h1>');

  // Horizontal Rules (--- or ***)
  out = out.replace(/^(?:---|___|\*\*\*)$/gm, '<hr class="md-hr" />');

  // Bold & Italic
  out = out.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  out = out.replace(/_([^_]+)_/g, '<em>$1</em>');
  out = out.replace(/~~([^~]+)~~/g, '<del>$1</del>');

  // Markdown links [text](url)
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>');

  // Markdown tables
  out = out.replace(/((?:\|[^\n]+\|\r?\n)+)/g, (match) => {
    const lines = match.trim().split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) return match;
    let html = '<div class="md-table-wrap"><table class="md-table">';
    let isHeader = true;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^\|[-:\s|]+\|$/.test(line)) {
        isHeader = false;
        continue;
      }
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      html += '<tr>';
      for (const c of cells) {
        if (isHeader) {
          html += `<th>${c}</th>`;
        } else {
          html += `<td>${c}</td>`;
        }
      }
      html += '</tr>';
      if (i === 0) html += '</thead><tbody>';
    }
    html += '</tbody></table></div>';
    return html;
  });

  // Lists
  out = out.replace(/^[ \t]*[-*+][ \t]+(.*)$/gm, '<li class="md-li">$1</li>');
  out = out.replace(/^[ \t]*(\d+)\.[ \t]+(.*)$/gm, '<li class="md-li-ord" value="$1">$2</li>');
  out = out.replace(/((?:<li class="md-li">.*?<\/li>\s*)+)/g, '<ul class="md-ul">$1</ul>');
  out = out.replace(/((?:<li class="md-li-ord"[^>]*>.*?<\/li>\s*)+)/g, '<ol class="md-ol">$1</ol>');

  // Paragraphs
  const blocks = out.split(/\n{2,}/);
  out = blocks.map(block => {
    block = block.trim();
    if (!block) return '';
    if (/^<(?:h[1-6]|ul|ol|pre|blockquote|div|table|hr)/i.test(block)) {
      return block;
    }
    return `<p class="md-p">${block.replace(/\n/g, '<br />')}</p>`;
  }).join('\n');

  return out;
}

/* ============================================================
   Role switching
============================================================ */
document.querySelectorAll(".role-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".role-btn").forEach((b) => b.classList.toggle("active", b === btn));
    state.role = btn.dataset.role;
    $("#view-user").classList.toggle("hidden", state.role !== "user");
    $("#view-admin").classList.toggle("hidden", state.role !== "admin");
    if (state.role === "admin") startAdminPolling();
    else stopAdminPolling();
  });
});

/* ============================================================
   USER CONSOLE
============================================================ */
async function loadAgents() {
  const data = await api("/api/agents");
  state.agents = data.agents;
  const list = $("#agent-list");
  list.innerHTML = "";
  for (const a of state.agents) {
    const card = document.createElement("button");
    card.className = "agent-card" + (a.id === state.agentId ? " selected" : "");
    card.innerHTML = `
      <span class="kind">${esc(a.kind)}</span>
      <h3>${esc(a.name)}</h3>
      <p>${esc((a.description || "").slice(0, 110))}…</p>
      <div class="badges">${(a.techniques || []).map((t) => `<span class="badge-mini">${esc(t)}</span>`).join("")}</div>`;
    card.addEventListener("click", () => selectAgent(a.id));
    list.appendChild(card);
  }
}

async function selectAgent(agentId) {
  state.agentId = agentId;
  clearInterval(state.hitlWatcher);
  if (!state.threads[agentId]) {
    const { thread_id } = await api(`/api/threads/new?agent_id=${encodeURIComponent(agentId)}`, { method: "POST" });
    state.threads[agentId] = thread_id;
    localStorage.setItem("gf_threads", JSON.stringify(state.threads));
  }
  await loadAgents();
  const agent = state.agents.find((a) => a.id === agentId);
  $("#chat-agent-name").textContent = agent.name;
  $("#chat-agent-meta").textContent =
    `${agent.kind} · waits on: ${(agent.waits_on || []).join(", ") || "nothing — single-turn"}`;
  $("#thread-chip").textContent = `thread: ${state.threads[agentId]}`;
  $("#thread-chip").classList.remove("hidden");
  $("#chat-text").disabled = false;
  $("#chat-send").disabled = false;

  // Restore persistent conversation messages for this agent
  const box = $("#messages");
  box.innerHTML = "";
  const history = state.chatHistory[agentId] || [];
  if (history.length > 0) {
    for (const msg of history) {
      addMessageToDOM(msg.role, msg.text, msg.payload || {});
    }
  } else {
    const starterChips = getStarterChipsForAgent(agentId);
    box.innerHTML = `
      <div class="empty-state">
        <h3>${esc(agent.name)} is listening.</h3>
        <p>${esc(agent.description)}</p>
        <div class="chat-action-group" style="justify-content:center;margin-top:1.2rem;">
          ${starterChips.map((c, i) => `<button type="button" class="action-chip ${c.class || ''}" onclick="triggerStarterChip('${esc(agentId)}', ${i})">${esc(c.label)}</button>`).join("")}
        </div>
      </div>`;
  }
  $("#chat-text").focus();
}

window.getStarterChipsForAgent = function(agentId) {
  if (agentId === "orchestrator") {
    return [
      { label: "🌾 Diagnose Crop Leaf Symptoms", val: "Our wheat field #1 has brown rust spots on leaves and powdery mildew spread." },
      { label: "🚜 Tractor TRC-2001 Hydraulic Repair", val: "Tractor TRC-2001 has a hydraulic pump seal blowout and main pressure manifold failure." },
      { label: "💰 Apply for Operating Loan", val: "We need an emergency operating loan of $15,000 for upcoming harvest labor." },
      { label: "📋 Reshuffle Multi-Field Dispatch", val: "Reshuffle today's spraying dispatch considering high wind near canals." },
    ];
  }
  if (agentId === "crop_disease") {
    return [
      { label: "🌾 Brown rust on wheat field #1", val: "Wheat field #1 has yellow pustules and brown leaf rust patches with powdery mildew." },
      { label: "📸 Attach Wheat Leaf Rust Photo", customAction: () => {
        const photo = [{ filename: "wheat_leaf_rust_field1.jpg", size: 340000, document_type: "crop_photo" }];
        sendChatMessage("Attached crop leaf inspection photo: severe brown rust spots on wheat field #1.", photo);
      }},
      { label: "🌿 Powdery mildew on North Plot B", val: "North Plot B shows white powdery fungal spots across 30% of foliage." },
    ];
  }
  if (agentId === "maintenance") {
    return [
      { label: "🚜 Tractor TRC-2001 Hydraulic Blowout", val: "Tractor TRC-2001 has severe hydraulic pump seal blowout and main pressure manifold failure." },
      { label: "🔧 Attach Diagnostic Fault Log", customAction: () => {
        const diagLog = [{ filename: "hydraulics_diag_trc2001.txt", size: 45000, document_type: "diagnostic_log" }];
        sendChatMessage("Attached diagnostic fault report for Tractor TRC-2001: Hydraulic pressure below 500 PSI.", diagLog);
      }},
      { label: "🚜 Sprayer SPR-3001 Pressure Drop", val: "Sprayer SPR-3001 nozzle delivery pressure dropped by 40% under load." },
    ];
  }
  if (agentId === "finance") {
    return [
      { label: "💰 $15,000 Harvest Operating Loan", val: "Hello, I need an emergency operating loan of $15,000 for upcoming harvest labor." },
      { label: "🚜 $85,000 Harvester Facility (HITL)", val: "We need an operating facility of $85,000 for purchasing a combine harvester." },
      { label: "📄 Attach Verified Loan Documents", customAction: () => {
        const docs = [
          { filename: "tariq_government_id.pdf", size: 142000, document_type: "government_id" },
          { filename: "farm_tax_return_2025.pdf", size: 285000, document_type: "farm_tax_return" },
          { filename: "bank_statements_6m.pdf", size: 512000, document_type: "bank_statements" },
          { filename: "land_lease_deed.pdf", size: 320000, document_type: "land_deed_or_lease" },
        ];
        sendChatMessage("Uploaded verified financial documentation (ID, Tax Return, Bank Statements, Land Deed).", docs);
      }},
    ];
  }
  if (agentId === "fleet_planner") {
    return [
      { label: "🌳 /tot Tree of Thoughts Dispatch", val: "/tot Reshuffle the dispatch board to spray North Plot A and Plot B before wind exceeds 15 km/h." },
      { label: "📝 /ps Plan-and-Solve Schedule", val: "/ps Generate an optimal route for Tractor TRC-2002 and Sprayer SPR-3001." },
    ];
  }
  if (agentId === "knowledge_assistant") {
    return [
      { label: "🚜 Which equipment is idle in Depot A?", val: "Which equipment is currently idle in Depot A?" },
      { label: "📜 What is the canal buffer rule?", val: "What is our mandatory chemical buffer distance from water canals?" },
      { label: "💰 What are the loan DSCR requirements?", val: "What are the DSCR credit underwriting requirements for loan approval?" },
    ];
  }
  return [];
};

window.triggerStarterChip = function(agentId, index) {
  const chips = getStarterChipsForAgent(agentId);
  const chip = chips[index];
  if (!chip) return;
  if (chip.customAction) chip.customAction();
  else sendChatMessage(chip.val);
};

async function resetThreadForCurrentAgent() {
  if (!state.agentId) return;
  clearInterval(state.hitlWatcher);
  state.chatHistory[state.agentId] = [];
  state.pendingAttachments = [];
  renderAttachmentBar();
  localStorage.setItem("gf_chat_history", JSON.stringify(state.chatHistory));
  const { thread_id } = await api(`/api/threads/new?agent_id=${encodeURIComponent(state.agentId)}`, { method: "POST" });
  state.threads[state.agentId] = thread_id;
  localStorage.setItem("gf_threads", JSON.stringify(state.threads));
  $("#thread-chip").textContent = `thread: ${thread_id}`;
  selectAgent(state.agentId);
  toast("Conversation cleared. Started fresh thread.");
}

$("#new-thread-btn").addEventListener("click", resetThreadForCurrentAgent);
const clearBtn = $("#clear-chat-btn");
if (clearBtn) clearBtn.addEventListener("click", resetThreadForCurrentAgent);

/* ============================================================
   Real File Upload Handlers
============================================================ */
const attachBtn = $("#btn-attach-files");
const fileInput = $("#file-upload-input");

if (attachBtn && fileInput) {
  attachBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) {
      const formData = new FormData();
      formData.append("file", f);
      try {
        const uploaded = await api("/api/upload", { method: "POST", body: formData });
        state.pendingAttachments.push(uploaded);
        toast(`Uploaded: ${uploaded.filename}`);
      } catch (err) {
        toast(`Upload failed: ${err.message}`, true);
      }
    }
    renderAttachmentBar();
    fileInput.value = "";
  });
}

function renderAttachmentBar() {
  const bar = $("#attachment-bar");
  if (!bar) return;
  if (!state.pendingAttachments.length) {
    bar.innerHTML = "";
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  bar.innerHTML = state.pendingAttachments
    .map((att, idx) => `
      <div class="attachment-chip">
        <span>📄 ${esc(att.filename)} (${Math.round((att.size || 0) / 1024)} KB)</span>
        <button type="button" class="remove-btn" onclick="removeAttachment(${idx})">✕</button>
      </div>`)
    .join("");
}

window.removeAttachment = function(idx) {
  state.pendingAttachments.splice(idx, 1);
  renderAttachmentBar();
};

/* ============================================================
   Chat Submission & Live HITL Auto-Resumption
============================================================ */
async function sendChatMessage(text, attachments = []) {
  if (!state.agentId) return;
  const atts = attachments.length ? attachments : [...state.pendingAttachments];
  state.pendingAttachments = [];
  renderAttachmentBar();

  let displayText = text;
  if (atts.length && !text) {
    displayText = `Uploaded files: ${atts.map((a) => a.filename).join(", ")}`;
  }

  addMessage("user", displayText, { attachments: atts });
  setBusy(true);

  try {
    const res = await api("/api/chat", {
      method: "POST",
      body: {
        agent_id: state.agentId,
        thread_id: state.threads[state.agentId],
        message: text,
        attachments: atts,
      },
    });
    addMessage("agent", res.reply, res);

    // If workflow is paused at an HITL gate, automatically watch for admin decision
    if (res.paused && (res.pause_kind === "hitl" || res.paused_at === "admin_review" || res.paused_at === "cost_approval_required" || res.paused_at === "awaiting_hitl")) {
      startHitlWatcher(state.agentId, state.threads[state.agentId]);
    }
  } catch (err) {
    addMessage("agent", `Error: ${err.message}`);
  } finally {
    setBusy(false);
  }
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chat-text");
  const text = input.value.trim();
  if (!text && !state.pendingAttachments.length) return;
  input.value = "";
  await sendChatMessage(text);
});

function startHitlWatcher(agentId, threadId) {
  clearInterval(state.hitlWatcher);
  let attempts = 0;
  state.hitlWatcher = setInterval(async () => {
    attempts++;
    if (attempts > 300) {
      clearInterval(state.hitlWatcher);
      return;
    }
    try {
      const stateData = await api(`/api/threads/${encodeURIComponent(agentId)}/${encodeURIComponent(threadId)}`);
      const nextNodes = stateData.next_nodes || [];
      const pendingReason = stateData.pending_interrupt?.reason;
      const isStillPaused = nextNodes.includes("admin_review") ||
                            pendingReason === "cost_approval_required" ||
                            pendingReason === "chemical_signoff_required";

      if (!isStillPaused && stateData.exists) {
        clearInterval(state.hitlWatcher);
        document.querySelectorAll(".hitl-live-watcher").forEach((el) => {
          el.innerHTML = "✅ <b>Decision actioned in Admin Console</b> — workflow resumed.";
          el.style.background = "rgba(46, 125, 50, 0.15)";
          el.style.borderColor = "var(--accent)";
          el.style.color = "var(--accent)";
        });
        toast("Admin decision actioned! Conversation auto-resumed.");
        const res = await api("/api/chat", {
          method: "POST",
          body: { agent_id: agentId, thread_id: threadId, message: "status" },
        });
        addMessage("agent", res.reply, res);
      }
    } catch {}
  }, 1500);
}

function setBusy(busy) {
  $("#chat-send").disabled = busy;
  $("#chat-text").disabled = busy;
  if (!busy) $("#chat-text").focus();
}

function addMessage(role, text, payload = {}, save = true) {
  addMessageToDOM(role, text, payload);
  if (save && state.agentId) {
    if (!state.chatHistory[state.agentId]) {
      state.chatHistory[state.agentId] = [];
    }
    state.chatHistory[state.agentId].push({ role, text, payload });
    localStorage.setItem("gf_chat_history", JSON.stringify(state.chatHistory));
  }
}

function addMessageToDOM(role, text, payload = {}) {
  const box = $("#messages");
  box.querySelector(".empty-state")?.remove();

  if (payload.handoff_history && payload.handoff_history.length > 0) {
    for (const h of payload.handoff_history) {
      const b = document.createElement("div");
      b.className = "banner hitl";
      b.style.borderColor = "var(--accent)";
      b.style.background = "var(--accent-soft)";
      b.style.color = "var(--accent)";
      b.textContent = `🔄 Dynamic Handoff → ${h.target}: ${h.reason}`;
      box.appendChild(b);
    }
  }

  if (role === "agent" && payload.paused && payload.pause_kind === "hitl") {
    const b = document.createElement("div");
    b.className = "banner hitl";
    b.textContent = "⏸ Paused — awaiting an administrator's decision in the Admin Console.";
    box.appendChild(b);
  }
  if (payload.ticket_id) {
    const b = document.createElement("div");
    b.className = "banner ticket";
    b.textContent = `Ticket #${payload.ticket_id} opened — inspect & resume it in the Admin Console.`;
    box.appendChild(b);
  }

  const el = document.createElement("div");
  el.className = `msg ${role}`;
  const senderName = role === "user" ? "you" : (payload.active_agent ? `Agent: ${payload.active_agent}` : esc(currentAgentName()));
  const contentHtml = role === "agent" ? `<div class="md-content">${renderMarkdown(text)}</div>` : `${esc(text)}`;
  el.innerHTML = `${contentHtml}<span class="meta">${senderName}${payload.paused_at ? " · paused at: " + esc(payload.paused_at) : ""}</span>`;

  // Render interactive quick action buttons for farmer decisions & uploads
  if (role === "agent") {
    const textLower = text.toLowerCase();
    const actions = [];

    if (payload.paused_at === "farmer_confirm" || textLower.includes("reply to accept") || textLower.includes("accept, or say 'no'")) {
      actions.push({ label: "✅ Approve & Accept Terms", class: "primary", val: "accept" });
      actions.push({ label: "❌ Decline Offer", class: "danger", val: "no" });
    } else if (payload.paused_at === "awaiting_testing_confirmation" || textLower.includes("passed / failed / marginal")) {
      actions.push({ label: "✅ Field Test Passed", class: "primary", val: "passed" });
      actions.push({ label: "⚠️ Marginal Performance", class: "secondary", val: "marginal" });
      actions.push({ label: "❌ Test Failed", class: "danger", val: "failed" });
    } else if (payload.paused_at === "awaiting_technician_visit") {
      actions.push({ label: "👨‍🔧 Technician Arrived On Site", class: "primary", val: "Technician arrived on site" });
    } else if (payload.paused_at === "awaiting_parts_delivery") {
      actions.push({ label: "📦 Spare Parts Delivered to Barn", class: "primary", val: "Spare parts received in barn" });
    } else if (payload.paused_at === "wait_farmer" || textLower.includes("upload the verified documents")) {
      actions.push({
        label: "📄 Attach & Upload Verified Loan Docs (ID, Tax, Bank, Lease)",
        class: "primary",
        customAction: () => {
          const sampleDocs = [
            { filename: "tariq_government_id.pdf", size: 142000, document_type: "government_id" },
            { filename: "farm_tax_return_2025.pdf", size: 285000, document_type: "farm_tax_return" },
            { filename: "bank_statements_6m.pdf", size: 512000, document_type: "bank_statements" },
            { filename: "land_lease_deed.pdf", size: 320000, document_type: "land_deed_or_lease" },
          ];
          sendChatMessage("Uploaded verified financial documentation (ID, Tax Return, Bank Statements, Land Deed).", sampleDocs);
        },
      });
      actions.push({
        label: "📎 Browse Real Files...",
        class: "secondary",
        customAction: () => $("#file-upload-input")?.click(),
      });
    } else if (payload.paused_at === "farmer_confirmation_required" || (textLower.includes("reply 'confirm'") && textLower.includes("decline"))) {
      actions.push({ label: "✅ Confirm Treatment Plan", class: "primary", val: "confirm" });
      actions.push({ label: "❌ Decline", class: "danger", val: "no" });
    } else if (payload.paused_at === "treatment_observation_required" || textLower.includes("recovered / improved / worsened")) {
      actions.push({ label: "🌿 Crop Fully Recovered", class: "primary", val: "recovered" });
      actions.push({ label: "🌱 Crop Significantly Improved", class: "primary", val: "improved" });
      actions.push({ label: "🥀 Crop Symptoms Worsened", class: "danger", val: "worsened" });
    }

    if (payload.paused && (payload.pause_kind === "hitl" || payload.paused_at === "admin_review" || payload.paused_at === "cost_approval_required" || payload.paused_at === "awaiting_hitl")) {
      const watcherDiv = document.createElement("div");
      watcherDiv.className = "hitl-live-watcher";
      watcherDiv.innerHTML = `<span class="pulse"></span> ⏳ <b>Human-in-the-Loop Review Active</b>: Awaiting Senior Admin approval in the Admin Console (auto-resumes immediately upon action).`;
      el.appendChild(watcherDiv);

      actions.push({
        label: "⚡ Fast-Approve in Admin Console (Demo Action)",
        class: "primary",
        customAction: async () => {
          try {
            toast("Approving task in Admin Console...");
            const tasksRes = await api("/api/hitl?status=pending");
            const pendingTasks = tasksRes.tasks || [];
            const task = pendingTasks.find(t => t.thread_id === (payload.thread_id || state.threads[state.agentId])) || pendingTasks[0];
            if (task) {
              const resolveKind = task.kind || (state.agentId === "maintenance" ? "maintenance" : state.agentId === "crop_disease" ? "crop_disease" : "finance");
              await api(`/api/hitl/${resolveKind}/${task.task_id}/resolve`, {
                method: "POST",
                body: { decision: "approve", notes: "1-Click Approval via Demo Action" },
              });
              toast("✅ Approved in Admin Console! Workflow continuing...");
              setTimeout(async () => {
                const res = await api("/api/chat", {
                  method: "POST",
                  body: { agent_id: state.agentId, thread_id: state.threads[state.agentId], message: "status" },
                });
                addMessage("agent", res.reply, res);
              }, 500);
            } else {
              toast("Checking current thread status...");
              const res = await api("/api/chat", {
                method: "POST",
                body: { agent_id: state.agentId, thread_id: state.threads[state.agentId], message: "status" },
              });
              addMessage("agent", res.reply, res);
            }
          } catch (e) {
            toast(`Approval error: ${e.message}`, true);
          }
        },
      });
    }

    if (actions.length > 0) {
      const actContainer = document.createElement("div");
      actContainer.className = "chat-action-group";
      for (const act of actions) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `action-chip ${act.class || ""}`;
        btn.textContent = act.label;
        btn.addEventListener("click", () => {
          if (act.customAction) {
            act.customAction();
          } else {
            sendChatMessage(act.val);
          }
        });
        actContainer.appendChild(btn);
      }
      el.appendChild(actContainer);
    }
  }

  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

const currentAgentName = () =>
  state.agents.find((a) => a.id === state.agentId)?.name || "";

/* ============================================================
   ADMIN CONSOLE
============================================================ */
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    state.adminTab = btn.dataset.tab;
    document.querySelectorAll(".admin-section").forEach((s) => s.classList.add("hidden"));
    $(`#tab-${state.adminTab}`).classList.remove("hidden");
    refreshAdminTab(true);
  });
});

function startAdminPolling() {
  refreshAdminTab(true);
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => refreshAdminTab(false), 5000);
}
function stopAdminPolling() { clearInterval(state.pollTimer); }

function refreshAdminTab(force) {
  if (state.role !== "admin") return;
  if (state.adminTab === "tools") loadToolMatrix();
  else if (state.adminTab === "documents") loadDocuments();
  else if (state.adminTab === "hitl" || force === true) loadHitl();
  if (state.adminTab === "tickets") loadTickets();
}

/* ---------- tools matrix ---------- */
let toolMatrixCache = null;

async function loadToolMatrix() {
  try {
    const data = await api("/api/admin/tools");
    toolMatrixCache = data;
    $("#server-pill").textContent = `MCP: live · ${data.live_tools.length} tools`;

    const agents = data.agents;
    const rowsByTool = {};
    for (const r of data.rows) {
      rowsByTool[r.tool_name] ??= {};
      rowsByTool[r.tool_name][r.agent_id] = r.is_enabled;
    }
    let html = `<table class="registry"><thead><tr><th>tool</th>${agents.map((a) => `<th>${esc(a)}</th>`).join("")}</tr></thead><tbody>`;
    for (const [tool, desc] of Object.entries(data.tools)) {
      html += `<tr><td class="tool-name" title="${esc(desc)}">${esc(tool)}</td>${agents
        .map(
          (a) => `<td><input type="checkbox" class="toggle" data-agent="${esc(a)}" data-tool="${esc(tool)}"
                    ${rowsByTool[tool]?.[a] ? "checked" : ""} /></td>`
        )
        .join("")}</tr>`;
    }
    html += "</tbody></table>";
    $("#tool-matrix").innerHTML = html;

    $("#live-tools").innerHTML = data.live_tools.map((t) => `<li>${esc(t)}</li>`).join("");

    $("#tool-matrix")
      .querySelectorAll("input.toggle")
      .forEach((box) =>
        box.addEventListener("change", async () => {
          box.disabled = true;
          try {
            const res = await api("/api/admin/tools/toggle", {
              method: "POST",
              body: {
                agent_id: box.dataset.agent,
                tool_name: box.dataset.tool,
                enabled: box.checked,
              },
            });
            toast(`${box.dataset.tool} ${box.checked ? "enabled" : "disabled"} for ${box.dataset.agent}. Live server now serves: ${res.live_tools.length} tools.`);
          } catch (err) {
            toast(err.message, true);
            box.checked = !box.checked;
          } finally {
            box.disabled = false;
            loadToolMatrix();
          }
        })
      );
  } catch (err) {
    $("#tool-matrix").innerHTML = `<p class="muted">Failed to load: ${esc(err.message)}</p>`;
  }
}

/* ---------- documents ---------- */
async function loadDocuments() {
  try {
    const data = await api("/api/admin/documents");
    const list = $("#doc-list");
    if (!data.documents.length) {
      list.innerHTML = '<p class="muted">No documents ingested yet.</p>';
      return;
    }
    list.innerHTML = "";
    for (const d of data.documents) {
      const row = document.createElement("div");
      row.className = "doc-row";
      row.innerHTML = `<div><div class="name">${esc(d.source)}</div>
        <span class="muted small">${d.chunks} chunk${d.chunks === 1 ? "" : "s"} embedded</span></div>
        <button class="btn reject">Remove</button>`;
      row.querySelector("button").addEventListener("click", async () => {
        if (!confirm(`Remove '${d.source}' from the vector store?`)) return;
        try {
          await api(`/api/admin/documents/${encodeURIComponent(d.source)}`, { method: "DELETE" });
          toast(`Removed '${d.source}' — next retrieval reflects the change.`);
        } catch (err) { toast(err.message, true); }
        loadDocuments();
      });
      list.appendChild(row);
    }
  } catch (err) {
    $("#doc-list").innerHTML = `<p class="muted">Failed to load: ${esc(err.message)}</p>`;
  }
}

$("#doc-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (!$("#doc-name").value) $("#doc-name").value = file.name;
  file.text().then((t) => ($("#doc-text").value = t));
});

$("#doc-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const res = await api("/api/admin/documents", {
      method: "POST",
      body: { source_name: $("#doc-name").value.trim(), text: $("#doc-text").value },
    });
    toast(`Ingested '${res.source}' (${res.chunks_added} chunks).`);
    $("#doc-name").value = ""; $("#doc-text").value = ""; $("#doc-file").value = "";
    loadDocuments();
  } catch (err) { toast(err.message, true); }
});

/* ---------- HITL inbox ---------- */
async function loadHitl() {
  try {
    const data = await api("/api/hitl");
    const pending = data.tasks.filter((t) => (t.status || "").toLowerCase() === "pending");
    const badge = $("#hitl-badge");
    badge.textContent = pending.length;
    badge.classList.toggle("hidden", pending.length === 0);

    const box = $("#hitl-list");
    if (!data.tasks.length) {
      box.innerHTML = '<p class="muted">No HITL tasks yet. Escalations appear here the moment a graph pauses.</p>';
      return;
    }
    box.innerHTML = "";
    for (const t of [...pending, ...data.tasks.filter((t) => !pending.includes(t))]) {
      const isPending = (t.status || "").toLowerCase() === "pending";
      const card = document.createElement("div");
      card.className = "task-card";
      const who = t.kind === "finance"
        ? `Finance thread <code>${esc(t.thread_id)}</code>${t.company_name ? " · " + esc(t.company_name) : ""}`
        : t.kind === "maintenance"
        ? `Maintenance thread <code>${esc(t.thread_id)}</code> · Repair Cost: $${Number(t.assessed_amount || 0).toLocaleString()}`
        : `Crop case #${t.case_id || ""} · thread <code>${esc(t.thread_id)}</code>`;
      card.innerHTML = `
        <div class="task-head">
          <div>
            <h3>HITL #${t.task_id} · ${esc(t.node_name || "")}</h3>
            <p class="muted small">${who}${t.assessed_amount != null && t.kind !== "maintenance" ? ` · $${Number(t.assessed_amount).toLocaleString()} · DSCR ${t.dscr ?? "?"} · risk ${esc(t.risk_level ?? "?")}` : ""}</p>
          </div>
          <span class="pill ${esc(t.status)}">${esc(t.status)}</span>
        </div>
        <p>${esc(t.reason)}</p>
        <details class="snapshot">
          <summary>Persisted graph state at pause</summary>
          <pre>${esc(JSON.stringify(t.state_snapshot_parsed ?? {}, null, 2))}</pre>
        </details>
        ${isPending ? `
        <div class="actions">
          <button class="btn approve" data-d="approve">Approve</button>
          <button class="btn reject" data-d="reject">Reject</button>
          ${t.kind === "finance" ? '<button class="btn info" data-d="more_info">Request more info</button>' : ""}
          <input type="text" class="notes" placeholder="Decision notes (optional)" style="flex:1;min-width:180px;border:1px solid var(--line);border-radius:8px;padding:.45rem .7rem;" />
        </div>` : `<p class="muted small">Resolved ${esc(t.resolved_at || "")}${t.admin_notes ? " · notes: " + esc(t.admin_notes) : ""}</p>`}
      `;
      card.querySelectorAll("[data-d]").forEach((btn) =>
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            const res = await api(`/api/hitl/${t.kind}/${t.task_id}/resolve`, {
              method: "POST",
              body: { decision: btn.dataset.d, notes: card.querySelector(".notes")?.value || "" },
            });
            toast(`Task #${t.task_id} ${res.decision} — run resumed from checkpoint.`);
          } catch (err) { toast(err.message, true); btn.disabled = false; }
          loadHitl();
        })
      );
      box.appendChild(card);
    }
  } catch (err) {
    $("#hitl-list").innerHTML = `<p class="muted">Failed to load: ${esc(err.message)}</p>`;
  }
}

/* ---------- tickets board ---------- */
async function loadTickets() {
  try {
    const data = await api("/api/tickets");
    const openCount = data.tickets.filter((t) => t.status !== "resolved").length;
    const badge = $("#ticket-badge");
    badge.textContent = openCount;
    badge.classList.toggle("hidden", openCount === 0);

    const box = $("#ticket-list");
    if (!data.tickets.length) {
      box.innerHTML = '<p class="muted">No failure tickets. Mid-node failures open tickets here automatically.</p>';
      return;
    }
    box.innerHTML = "";
    for (const t of data.tickets) {
      const isOpen = t.status !== "resolved";
      const card = document.createElement("div");
      card.className = "task-card";
      card.innerHTML = `
        <div class="task-head">
          <div>
            <h3>Ticket #${t.ticket_id} · failed node <code>${esc(t.failed_node)}</code></h3>
            <p class="muted small">thread <code>${esc(t.thread_id)}</code> · ${esc(t.created_at || "")}</p>
          </div>
          <span class="pill ${esc(t.status)}">${esc(t.status)}</span>
        </div>
        <p><strong>${esc(t.error_type)}</strong> — ${esc(t.error_message)}</p>
        <details class="snapshot">
          <summary>Checkpointed state at failure</summary>
          <pre>${esc(prettySnapshot(t.state_snapshot))}</pre>
        </details>
        ${isOpen ? `
        <div class="actions">
          ${t.status === "open" ? '<button class="btn neutral act-investigate">Mark investigating</button>' : ""}
          <button class="btn approve act-resolve">Resolve & resume from checkpoint</button>
          <input type="text" class="notes" placeholder="Resolution notes (optional)" style="flex:1;min-width:200px;border:1px solid var(--line);border-radius:8px;padding:.45rem .7rem;" />
        </div>` : `<p class="muted small">Resolved ${esc(t.resolved_at || "")}${t.resolution_notes ? " · " + esc(t.resolution_notes) : ""}</p>`}
      `;
      const inv = card.querySelector(".act-investigate");
      if (inv) inv.addEventListener("click", async () => {
        inv.disabled = true;
        try {
          await api(`/api/tickets/${t.ticket_id}/investigate`, {
            method: "POST",
            body: { notes: card.querySelector(".notes")?.value || "" },
          });
          toast(`Ticket #${t.ticket_id} marked investigating.`);
        } catch (err) { toast(err.message, true); }
        loadTickets();
      });
      const resolve = card.querySelector(".act-resolve");
      if (resolve) resolve.addEventListener("click", async () => {
        resolve.disabled = true;
        try {
          const res = await api(`/api/tickets/${t.ticket_id}/resolve`, {
            method: "POST",
            body: { notes: card.querySelector(".notes")?.value || "" },
          });
          toast(`Ticket #${t.ticket_id} resolved — run resumed from '${res.resumed_from_node || res.paused_at || "checkpoint"}'.`);
        } catch (err) { toast(err.message, true); resolve.disabled = false; }
        loadTickets();
      });
      box.appendChild(card);
    }
  } catch (err) {
    $("#ticket-list").innerHTML = `<p class="muted">Failed to load: ${esc(err.message)}</p>`;
  }
}

function prettySnapshot(raw) {
  try { return JSON.stringify(JSON.parse(raw), null, 2); }
  catch { return raw || "{}"; }
}

/* ============================================================
   Boot
============================================================ */
(async function boot() {
  try {
    const h = await api("/api/health");
    $("#server-pill").textContent = `MCP: ${h.mcp_url.replace(/^https?:\/\//, "")}`;
  } catch {
    $("#server-pill").textContent = "MCP: offline";
  }
  await loadAgents();
})();
