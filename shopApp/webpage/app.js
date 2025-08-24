// app.js (final) — 부팅 시 서버 최신 세션 복원 + 상품카드 유지
/* Chat UI + 로컬 저장소 대화 관리 */
(() => {
  const $ = (sel) => document.querySelector(sel);

  const el = {
    sidebar: $("#sidebar"),
    sidebarToggle: $("#sidebarToggle"),
    convList: $("#convList"),
    newChatBtn: $("#newChatBtn"),
    clearAllBtn: $("#clearAllBtn"),
    messages: $("#messages"),
    composerForm: $("#composerForm"),
    promptInput: $("#promptInput"),
    stopBtn: $("#stopBtn"),
    sendBtn: $("#sendBtn"),
    userCard: $("#userCard"),
    userInitial: $("#userInitial"),
    userName: $("#userName"),
    userEmail: $("#userEmail"),
    loginBtn: $("#loginBtn"),
    logoutBtn: $("#logoutBtn"),
  };

  let conversations = [];
  let activeId = null;
  let currentAbort = null;

  // ---------- 대화 관리 ----------
  function createConversation() {
    const id = "c_" + Math.random().toString(36).slice(2, 10);
    const conv = { id, title: "새 대화", createdAt: Date.now(), messages: [] };
    conversations.unshift(conv);
    setActive(id);
    return conv;
  }
  function createConversationWithId(id, title = "대화") {
    let conv = conversations.find((c) => c.id === id);
    if (!conv) {
      conv = { id, title, createdAt: Date.now(), messages: [] };
      conversations.unshift(conv);
    }
    setActive(id);
    return conv;
  }
  function getActiveConv() { return conversations.find((c) => c.id === activeId); }
  function setActive(id) {
    activeId = id;
    try { localStorage.setItem("lastConv", id); } catch {}
    renderConversations(); renderMessages();
  }
  function deleteConversation(id) {
    const idx = conversations.findIndex((c) => c.id === id);
    if (idx >= 0) conversations.splice(idx, 1);
    if (!conversations.length) { createConversation(); return; }
    if (activeId === id) activeId = conversations[0].id;
    renderConversations(); renderMessages();
  }
  function renameConversation(id, title) {
    const c = conversations.find((c) => c.id === id); if (!c) return;
    c.title = title; renderConversations();
  }

  // ---------- 렌더링 ----------
  function renderConversations() {
    el.convList.innerHTML = "";
    conversations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "conv-item" + (c.id === activeId ? " active" : "");
      item.innerHTML = `
        <div class="conv-title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</div>
        <div class="conv-actions">
          <button data-act="rename" title="이름 변경">✎</button>
          <button data-act="delete" title="삭제">🗑</button>
        </div>
      `;
      item.addEventListener("click", (e) => {
        const btn = e.target.closest("button"); if (btn) return;
        setActive(c.id);
      });
      item.querySelector('[data-act="rename"]').addEventListener("click", (e) => {
        e.stopPropagation(); const title = prompt("대화 제목을 입력하세요", c.title);
        if (title) renameConversation(c.id, title);
      });
      item.querySelector('[data-act="delete"]').addEventListener("click", (e) => {
        e.stopPropagation(); if (confirm("이 대화를 삭제하시겠습니까?")) deleteConversation(c.id);
      });
      el.convList.appendChild(item);
    });
  }

  function renderMessages() {
    const conv = getActiveConv();
    el.messages.innerHTML = "";
    if (!conv) return;
    conv.messages.forEach((m) => { appendMessage(m.role, m.content, m.products); });
    scrollToBottom();
  }

  function appendMessage(role, content, products = null) {
    const tpl = document.getElementById("msgTemplate");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.classList.toggle("user", role === "user");
    node.querySelector(".avatar").textContent = role === "user" ? "U" : "A";

    // 말풍선 텍스트
    node.querySelector(".bubble").innerHTML = renderMarkdown(content);
    el.messages.appendChild(node);

    // 상품 섹션 추가 (assistant 답변일 때만)
    if (role === "assistant" && Array.isArray(products) && products.length > 0) {
      const wrapper = document.createElement("div");
      wrapper.className = "product-list";

      const tplProduct = document.getElementById("productTemplate");
      products.forEach(item => {
        const card = tplProduct.content.firstElementChild.cloneNode(true);
        if (item.link)  card.querySelector("a").href = item.link;
        if (item.image) card.querySelector("img").src = item.image;
        card.querySelector("img").alt = item.title || "";
        card.querySelector(".p-title").textContent = item.title || "";
        if (item.lprice != null) card.querySelector(".p-price").textContent = String(item.lprice) + "원";
        card.querySelector(".p-mall").textContent = item.mallName || "";
        wrapper.appendChild(card);
      });

      el.messages.appendChild(wrapper);
    }

    scrollToBottom();
  }

  function updateAssistantLastBubble(text) {
    const last = el.messages.querySelector(".msg:last-child .bubble");
    if (last) { last.innerHTML = renderMarkdown(text); scrollToBottom(); }
  }

  function scrollToBottom() {
    el.messages.parentElement.scrollTop = el.messages.parentElement.scrollHeight;
  }

  // ---------- 유틸 ----------
  function escapeHtml(str = "") {
    return String(str).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
  }

  // 미니 마크다운 렌더러
  function renderMarkdown(src = "") {
    const esc = escapeHtml(src);
    let out = esc.replace(/```([\s\S]*?)```/g, (m, code) => `<pre><code>${code}</code></pre>`);
    out = out.replace(/`([^`]+)`/g, (m, c) => `<code>${c}</code>`);
    out = out.replace(/\*\*([^*]+)\*\*/g, (m, b) => `<strong>${b}</strong>`);
    out = out.replace(/(https?:\/\/[^\s)]+)(?![^<]*>)/g, (m) => `<a href="${m}" target="_blank" rel="noopener noreferrer">${m}</a>`);
    return out;
  }

  // 타자 효과
  async function typeOut(text, onUpdate, signal) {
    const delay = 8 + Math.random() * 14;
    let shown = "";
    for (let i = 0; i < text.length; i++) {
      if (signal?.aborted) throw new Error("cancelled");
      shown += text[i]; onUpdate(shown);
      await new Promise((r) => setTimeout(r, delay));
    }
    onUpdate(text);
  }

  // ---------- Composer ----------
  el.composerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = el.promptInput.value.trim();
    if (!prompt) return;
    if (!window.Auth.isLoggedIn()) { alert("로그인 후 사용하세요."); return; }

    const conv = getActiveConv() || createConversation();
    conv.messages.push({ role: "user", content: prompt, ts: Date.now() });
    appendMessage("user", prompt);

    el.promptInput.value = ""; autosizeTextarea();
    const abortController = new AbortController(); currentAbort = abortController;
    el.stopBtn.disabled = false; el.sendBtn.disabled = true;

    conv.messages.push({ role: "assistant", content: "생각 중...", ts: Date.now() });
    appendMessage("assistant", "생각 중...");

    try {
      const { answer, products } = await window.Api.chat(prompt, conv.id, abortController.signal);
      await typeOut(answer, (txt) => updateAssistantLastBubble(txt), abortController.signal);

      // 답변 반영 + 상품카드 유지
      conv.messages[conv.messages.length - 1].content = answer;
      conv.messages[conv.messages.length - 1].products = products || [];
      renderMessages(); // 상품 리스트 렌더를 위해 전체 갱신

      if (conv.title === "새 대화") {
        const title = prompt.length > 20 ? prompt.slice(0, 20) + "…" : prompt;
        renameConversation(conv.id, title);
      }
    } catch (err) {
      console.error(err);
      updateAssistantLastBubble(`오류가 발생했습니다: ${escapeHtml(err.message || String(err))}`);
    } finally {
      el.stopBtn.disabled = true; el.sendBtn.disabled = false;
      currentAbort = null; scrollToBottom();
    }
  });

  el.stopBtn.addEventListener("click", () => {
    if (currentAbort) currentAbort.abort();
    el.stopBtn.disabled = true; el.sendBtn.disabled = false;
  });

  el.newChatBtn.addEventListener("click", () => { createConversation(); el.promptInput.focus(); });
  el.clearAllBtn.addEventListener("click", () => {
    if (confirm("모든 대화를 삭제할까요?")) { conversations = []; createConversation(); }
  });

  function autosizeTextarea() {
    const ta = el.promptInput;
    ta.style.height = "auto";
    ta.style.height = Math.min(180, ta.scrollHeight) + "px";
  }
  el.promptInput.addEventListener("input", autosizeTextarea);
  el.promptInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      el.composerForm.requestSubmit();
      el.promptInput.disabled = true;
      setTimeout(() => {
        el.promptInput.disabled = false;
        el.promptInput.focus();
      }, 300);
    }
  });

  // ---------- Auth UI ----------
  function applyAuthUI() {
    const t = window.Auth.getTokens?.() || null;
    const loggedIn = window.Auth.isLoggedIn?.() || false;
    el.loginBtn.style.display = loggedIn ? "none" : "inline-block";
    el.logoutBtn.style.display = loggedIn ? "inline-block" : "none";
    if (loggedIn && t?.id_claims) {
      const name = t.id_claims.name || t.id_claims.nickname || "사용자";
      const email = t.id_claims.email || "";
      $("#userName").textContent = name;
      $("#userEmail").textContent = email;
      $("#userInitial").textContent = (name[0] || "?").toUpperCase();
    } else {
      $("#userName").textContent = "로그인 필요";
      $("#userEmail").textContent = "";
      $("#userInitial").textContent = "?";
    }
  }
  $("#loginBtn").addEventListener("click", () => window.Auth.login());
  $("#logoutBtn").addEventListener("click", () => window.Auth.logout());

  if (el.sidebarToggle) {
    el.sidebarToggle.addEventListener("click", () => {
      el.sidebar.classList.toggle("open");
    });
  }

  // ---------- 서버 이력 로드 ----------
  async function loadHistoryInto(convId) {
    const { messages } = await window.Api.history(convId, 50);
    const count = (messages || []).length;
    if (count === 0) {
      // 이 convId엔 서버 이력이 없음 → 복원 실패 신호
      return 0;
    }
  
    let conv = conversations.find(c => c.id === convId);
    if (!conv) {
      conv = { id: convId, title: "대화", createdAt: Date.now(), messages: [] };
      conversations.unshift(conv);
    }
    conv.messages = messages.map(m => ({
      role: m.role,
      content: m.content,
      ts: m.ts,
      products: m.products,
    }));
    setActive(convId);        // 이때만 활성화/렌더
    return count;             // 복원 성공(개수 반환)
  }

  // ---------- Boot ----------
  (async function boot() {
    if (window.AuthReady?.then) { try { await window.AuthReady; } catch {} }
    if (window.Auth?.handleRedirectIfPresent) { await window.Auth.handleRedirectIfPresent(); }
    applyAuthUI();
  
    let restored = false;
  
    // 1) localStorage 저장된 마지막 세션 우선 시도
    if (window.Auth.isLoggedIn?.()) {
      try {
        const last = localStorage.getItem("lastConv");
        if (last) {
          const cnt = await loadHistoryInto(last);
          restored = cnt > 0;               // 0건이면 복원 실패로 간주
          if (!restored) {
            // 쓰레기 값이면 정리(선택)
            try { localStorage.removeItem("lastConv"); } catch {}
          }
        }
      } catch (e) {
        console.warn("restore lastConv failed:", e);
      }
    }
  
    // 2) 실패했다면 서버 최신 세션으로 폴백
    if (!restored && window.Auth.isLoggedIn?.()) {
      try {
        const { conversations: list } = await window.Api.conversations(1);
        const latestId = list?.[0]?.conversationId;
        if (latestId) {
          const cnt = await loadHistoryInto(latestId);
          restored = cnt > 0;
        }
      } catch (e) {
        console.error("boot load failed", e);
      }
    }
  
    // 3) 그래도 없으면 로컬 새 대화
    if (!restored) {
      if (conversations.length === 0) { createConversation(); }
      else { setActive(conversations[0].id); }
    }
  })();
})();
