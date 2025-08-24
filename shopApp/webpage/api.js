// api.js (final) — chat / history / conversations
(() => {
  // --- Base path detection (matches API Gateway stage like /default) ---
  const meta = document.querySelector('meta[name="cognito"]');
  const redirectPath = meta?.dataset?.redirectPath || "";
  const logoutPath   = meta?.dataset?.logoutPath   || "";

  function extractBase(pathLike) {
    if (!pathLike) return "";
    const parts = String(pathLike).split("/").filter(Boolean);
    return parts.length > 0 ? `/${parts[0]}` : "";
  }

  const META_BASE     = extractBase(logoutPath) || extractBase(redirectPath);
  const FALLBACK_BASE = extractBase(location.pathname || "/");
  const BASE          = META_BASE || FALLBACK_BASE;

  function buildUrl(path) {
    const p = String(path || "").replace(/^\/+/, "");
    return BASE ? `${BASE}/${p}` : `/${p}`;
  }

  // --- Authenticated fetch wrapper ---
  async function withAuthFetch(url, options = {}) {
    // 1) 토큰 갱신 시도
    let token = await window.Auth.ensureValidAccessToken().catch(() => null);
    if (!token) throw new Error("로그인이 필요합니다.");

    // 2) 요청 구성
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);

    // body가 문자열이면 Content-Type 자동 지정
    if (typeof options.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    // 3) 1차 요청
    let resp;
    try {
      resp = await fetch(url, { ...options, headers });
    } catch (e) {
      throw new Error(`네트워크 오류: ${e?.message || e}`);
    }

    // 4) 401 재시도(동시 만료 대비)
    if (resp.status === 401) {
      const token2 = window.Auth.getAccessTokenSync();
      if (!token2) throw new Error("인증 만료. 다시 로그인 해주세요.");
      headers.set("Authorization", `Bearer ${token2}`);
      resp = await fetch(url, { ...options, headers });
    }
    return resp;
  }

  // --- API: POST /chat ---
  /**
   * @param {string} message
   * @param {string} conversationId
   * @param {AbortSignal|null} signal
   * @returns {Promise<{answer:string, products?:Array, conversationId:string}>}
   */
  async function chat(message, conversationId, signal = null) {
    const url = buildUrl("chat");
    const payload = { message, conversationId };
    const resp = await withAuthFetch(url, {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`API 오류 (${resp.status}): ${text}`);
    }
    return resp.json();
  }

  // --- API: GET /history ---
  /**
   * 대화 이력 불러오기. conversationId 없으면 쿼리에서 생략(백엔드가 최신 세션 자동 선택할 수 있음).
   * @param {string|undefined} conversationId
   * @param {number} [limit=50]
   * @param {string|null} [before=null]  // 13자리 epoch ms string
   * @param {AbortSignal} [signal]
   * @returns {Promise<{conversationId:string, messages:Array, nextBefore:string|null}>}
   */
  async function history(conversationId, limit = 50, before = null, signal) {
    const qs = new URLSearchParams();
    if (conversationId) qs.set("conversationId", conversationId);
    qs.set("limit", String(limit));
    if (before) qs.set("before", before);

    const url = buildUrl(`history?${qs.toString()}`);
    const resp = await withAuthFetch(url, { method: "GET", signal });
    if (!resp.ok) {
      const err = await resp.text().catch(() => "");
      throw new Error(`history failed: ${resp.status} ${err}`);
    }
    return resp.json();
  }

  // --- API: GET /conversations ---
  /**
   * 최신 대화 세션 목록(가장 최근 1개만 써도 됨).
   * @param {number} [limit=20]
   * @param {AbortSignal} [signal]
   * @returns {Promise<{conversations:Array<{conversationId:string,lastTs:number,lastSnippet:string,msgCount:number,updatedAt:number}>, nextKey:null}>}
   */
  async function conversations(limit = 20, signal) {
    const url = buildUrl(`conversations?limit=${encodeURIComponent(limit)}`);
    const resp = await withAuthFetch(url, { method: "GET", signal });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`API 오류 (${resp.status}): ${text}`);
    }
    return resp.json();
  }

  console.log(
    "[Api] base:", BASE || "(root)", "→",
    "GET", buildUrl("conversations"),
    "GET", buildUrl("history?conversationId=<id>"),
    "POST", buildUrl("chat")
  );

  // export
  window.Api = Object.freeze({ chat, history, conversations });
})();
