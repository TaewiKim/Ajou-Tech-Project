// api.js
/* API Gateway 호출 래퍼: Cognito 메타에서 베이스 경로 추출하여 항상 올바른 경로로 POST */
(() => {
  const meta = document.querySelector('meta[name="cognito"]');

  const redirectPath = meta?.dataset?.redirectPath || ""; // 예: /default/auth/callback
  const logoutPath   = meta?.dataset?.logoutPath   || ""; // 예: /default/

  // '/default/auth/callback' → '/default'
  // '/default/' → '/default'
  // '' → ''
  function extractBase(pathLike) {
    if (!pathLike) return "";
    const s = String(pathLike);
    // 1) '/default/auth/callback'처럼 세그먼트가 많으면 첫 세그먼트만 사용
    const parts = s.split("/").filter(Boolean); // ['', 'default', 'auth', 'callback'] → ['default','auth','callback']
    if (parts.length > 0) return `/${parts[0]}`;
    return "";
  }

  // meta 우선, 없으면 현재 URL의 첫 세그먼트 추정
  const META_BASE = extractBase(logoutPath) || extractBase(redirectPath);
  const FALLBACK_BASE = extractBase(location.pathname || "/");
  const BASE = META_BASE || FALLBACK_BASE; // 최종 베이스 (예: '/default')

  function buildUrl(path) {
    const p = String(path || "").replace(/^\/+/, "");
    if (!BASE) return `/${p}`;
    return `${BASE}/${p}`;
  }

  async function withAuthFetch(url, options = {}) {
    let token;
    try {
      token = await window.Auth.ensureValidAccessToken();
    } catch {
      throw new Error("로그인이 필요합니다.");
    }
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
      try {
        await window.Auth.ensureValidAccessToken();
        const token2 = window.Auth.getAccessTokenSync();
        if (!token2) throw new Error("인증 만료. 다시 로그인 해주세요.");
        headers.set("Authorization", `Bearer ${token2}`);
        resp = await fetch(url, { ...options, headers });
      } catch (e) {
        throw new Error(e?.message || "인증 갱신 실패");
      }
    }
    return resp;
  }

  // 서버(DynamoDB)에서 이력을 관리하므로 message + conversationId만 전송
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
      let detail = text;
      try { detail = JSON.stringify(JSON.parse(text)); } catch {}
      throw new Error(`API 오류 (${resp.status}): ${detail || "응답 본문 없음"}`);
    }

    try {
      return await resp.json();
    } catch {
      const t = await resp.text().catch(() => "");
      throw new Error(`JSON 파싱 실패: ${t || "본문 없음"}`);
    }
  }

  // 디버그: 실제 요청 URL 확인용
  console.log("[Api] base:", BASE || "(root)","→ POST", buildUrl("chat"));

  window.Api = Object.freeze({ chat });
})();
