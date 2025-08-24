// api.js
(() => {
  const meta = document.querySelector('meta[name="cognito"]');
  const redirectPath = meta?.dataset?.redirectPath || "";
  const logoutPath   = meta?.dataset?.logoutPath   || "";

  function extractBase(pathLike) {
    if (!pathLike) return "";
    const parts = String(pathLike).split("/").filter(Boolean);
    return parts.length > 0 ? `/${parts[0]}` : "";
  }

  const META_BASE = extractBase(logoutPath) || extractBase(redirectPath);
  const FALLBACK_BASE = extractBase(location.pathname || "/");
  const BASE = META_BASE || FALLBACK_BASE;

  function buildUrl(path) {
    const p = String(path || "").replace(/^\/+/, "");
    return BASE ? `${BASE}/${p}` : `/${p}`;
  }

  async function withAuthFetch(url, options = {}) {
    let token = await window.Auth.ensureValidAccessToken().catch(() => null);
    if (!token) throw new Error("로그인이 필요합니다.");

    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);
    if (typeof options.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    let resp;
    try {
      resp = await fetch(url, { ...options, headers });
    } catch (e) {
      throw new Error(`네트워크 오류: ${e?.message || e}`);
    }

    if (resp.status === 401) {
      const token2 = window.Auth.getAccessTokenSync();
      if (!token2) throw new Error("인증 만료. 다시 로그인 해주세요.");
      headers.set("Authorization", `Bearer ${token2}`);
      resp = await fetch(url, { ...options, headers });
    }
    return resp;
  }

  // POST /chat
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

  // GET /history
  async function history(conversationId = "default", limit = 50, before = null, signal) {
    const qs = new URLSearchParams({ conversationId, limit: String(limit) });
    if (before) qs.set("before", before);

    const url = buildUrl(`history?${qs.toString()}`);
    const resp = await withAuthFetch(url, { method: "GET", signal });
    if (!resp.ok) {
      const err = await resp.text().catch(() => "");
      throw new Error(`history failed: ${resp.status} ${err}`);
    }
    return resp.json(); // {conversationId, messages, nextBefore}
  }

  console.log("[Api] base:", BASE || "(root)", "→ POST", buildUrl("chat"));

  // ✅ 둘 다 등록
  window.Api = Object.freeze({ chat, history });
})();
