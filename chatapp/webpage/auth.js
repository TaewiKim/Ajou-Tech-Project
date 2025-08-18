/* auth.js — Cognito Auth for SPA (API Gateway HTTP API stage-aware)
   - 우선 oidc-client-ts(UMD: window.oidc)가 있으면 사용, 없으면 네이티브 PKCE로 동작
   - <meta name="cognito"> 로 설정을 주입 (data-domain, data-client-id, data-user-pool-id, data-redirect-path, data-logout-path)
   - window.Auth: { login, logout, isLoggedIn, getTokens, getAccessTokenSync, ensureValidAccessToken, handleRedirectIfPresent }
   - window.AuthReady: Promise (초기화 완료시 resolve)
*/

/* ── 0) 안전 스텁 노출 ─────────────────────────────────────────────────────── */
const __AuthStub = {
  login: () => { throw new Error("Auth not initialized"); },
  logout: () => {},
  isLoggedIn: () => false,
  getTokens: () => null,
  getAccessTokenSync: () => null,
  ensureValidAccessToken: async () => null,
  handleRedirectIfPresent: async () => {}
};
window.Auth = __AuthStub;

(() => {
  /* ── 1) 공통 설정 로더 (+ API GW 스테이지 자동 감지) ───────────────────── */
  function loadMetaCfg() {
    const meta = document.querySelector('meta[name="cognito"]');
    if (!meta) throw new Error('meta[name="cognito"] not found');

    const domain = (meta.dataset.domain || "").trim();         // e.g. taewi-chatapp.auth.ap-northeast-2.amazoncognito.com
    const clientId = (meta.dataset.clientId || "").trim();
    const userPoolId = (meta.dataset.userPoolId || "").trim(); // e.g. ap-northeast-2_XXXXXXXXX
    const redirectPath = (meta.dataset.redirectPath || "/auth/callback").trim() || "/auth/callback";
    const logoutPath   = (meta.dataset.logoutPath   || "/").trim() || "/";

    if (!domain)     throw new Error("Cognito Hosted UI domain missing in meta[data-domain]");
    if (!clientId)   throw new Error("Cognito client id missing in meta[data-client-id]");
    if (!userPoolId) throw new Error("Cognito user pool id missing in meta[data-user-pool-id]");

    const origin = window.location.origin;

    // ★ API Gateway HTTP API는 /{stage} 프리픽스가 경로에 붙음. (예: /default, /prod)
    //    커스텀 도메인을 쓰면 보통 프리픽스가 없음.
    const stagePrefix = (() => {
      // 첫 슬래시부터 다음 슬래시 전까지를 스테이지로 가정하되,
      // 일반적인 SPA(커스텀 도메인)에서는 빈 문자열이 된다.
      const path = window.location.pathname || "/";
      const m = path.match(/^\/[^/]+/);
      // 커스텀 도메인에서 "/auth"로 시작하면 m[0] === "/auth"가 되므로,
      // 이를 스테이지로 잘못 인식하지 않도록 보호 장치 추가:
      if (!m) return "";
      const candidate = m[0]; // "/default" 또는 "/auth" 같은 것
      // 콜백 경로가 곧바로 따라오는 경우(예: "/auth")는 스테이지 아님
      if (redirectPath.startsWith(candidate + "/") || redirectPath === candidate) return "";
      return candidate; // "/default" 등
    })();

    const redirectUri = origin + stagePrefix + (redirectPath.startsWith("/") ? redirectPath : "/" + redirectPath);
    const postLogoutRedirectUri = origin + stagePrefix + (logoutPath.startsWith("/") ? logoutPath : "/" + logoutPath);

    const region = userPoolId.split("_")[0];
    const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`;
    const hostedUi = `https://${domain}`;

    return {
      clientId, issuer, hostedUi,
      redirectUri, postLogoutRedirectUri,
      redirectPath, logoutPath,
      stagePrefix
    };
  }

  /* ── 2) 스토리지 & 유틸 ─────────────────────────────────────────────────── */
  const STORAGE_KEY = "cognito_tokens_v1";
  const nowSec = () => Math.floor(Date.now() / 1000);

  function saveTokens(tokens) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  }
  function readTokens() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  }
  function clearTokens() {
    localStorage.removeItem(STORAGE_KEY);
  }
  function isLoggedIn() {
    const t = readTokens();
    return !!(t?.access_token && t?.expires_at && nowSec() < (t.expires_at - 30));
  }
  function getTokens() {
    return readTokens();
  }
  function getAccessTokenSync() {
    return readTokens()?.access_token || null;
  }
  function base64urlencode(bytes) {
    return btoa(String.fromCharCode.apply(null, new Uint8Array(bytes)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  async function sha256(plain) {
    const data = new TextEncoder().encode(plain);
    const digest = await crypto.subtle.digest("SHA-256", data);
    return base64urlencode(new Uint8Array(digest));
  }
  function randomString(len = 64) {
    const bytes = new Uint8Array(len);
    crypto.getRandomValues(bytes);
    return base64urlencode(bytes).slice(0, len);
  }
  function parseJwt(token) {
    try {
      const payload = token.split(".")[1];
      const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
      return JSON.parse(decodeURIComponent(escape(json)));
    } catch { return null; }
  }

  /* ── 3) Path A: oidc-client-ts(UMD) 우선 사용 ──────────────────────────── */
  async function initWithOidcClientTs(cfg) {
    const oidc = (window.oidc || {});
    const { UserManager, WebStorageStateStore /*, Log*/ } = oidc;
    if (!UserManager) return null;

    const settings = {
      authority: cfg.issuer,
      client_id: cfg.clientId,
      redirect_uri: cfg.redirectUri,
      response_type: "code",
      scope: "openid email profile",
      userStore: new WebStorageStateStore({ store: window.localStorage }),
      metadata: {
        issuer: cfg.issuer,
        authorization_endpoint: `${cfg.hostedUi}/oauth2/authorize`,
        token_endpoint:        `${cfg.hostedUi}/oauth2/token`,
        jwks_uri:              `${cfg.issuer}/.well-known/jwks.json`,
        end_session_endpoint:  `${cfg.hostedUi}/logout`,
      },
      // silent renew을 쓰려면 추가 라우트 필요. 기본은 비활성화.
    };

    const userManager = new UserManager(settings);

    function packFromUser(user) {
      if (!user) return null;
      const json = {
        access_token:  user.access_token || null,
        id_token:      user.id_token || null,
        refresh_token: user.refresh_token || null,
        expires_at:    user.expires_at || 0,
        id_claims:     user.profile || null,
      };
      saveTokens(json);
      return json;
    }

    async function login() {
      await userManager.signinRedirect();
    }

    async function handleRedirectIfPresent() {
      const here = new URL(window.location.href);
      // 경로 비교는 pathname만(쿼리 제외), 디코딩 후 비교
      if (decodeURIComponent(here.pathname) !== decodeURIComponent(new URL(cfg.redirectUri).pathname)) return;
      const hasCode = here.searchParams.has("code") && here.searchParams.has("state");
      if (!hasCode) return;

      const user = await userManager.signinCallback();
      packFromUser(user);

      // 콜백 쿼리 제거 & 홈으로
      window.history.replaceState({}, "", cfg.postLogoutRedirectUri);
    }

    let refreshLock = null;
    async function ensureValidAccessToken() {
      const t = readTokens();
      if (t && nowSec() < (t.expires_at - 30)) return t.access_token;

      // 동시 갱신 방지
      if (refreshLock) return refreshLock;
      refreshLock = (async () => {
        try {
          const current = await userManager.getUser().catch(() => null);
          if (current) {
            const packed = packFromUser(current);
            return (packed && nowSec() < (packed.expires_at - 30)) ? packed.access_token : null;
          }
          return null;
        } finally {
          refreshLock = null;
        }
      })();
      return refreshLock;
    }

    async function logout() {
      clearTokens();
      try {
        await userManager.signoutRedirect({ post_logout_redirect_uri: cfg.postLogoutRedirectUri });
      } catch {
        const url = `${cfg.hostedUi}/logout?client_id=${encodeURIComponent(cfg.clientId)}&logout_uri=${encodeURIComponent(cfg.postLogoutRedirectUri)}`;
        window.location.assign(url);
      }
    }

    return { login, logout, isLoggedIn, getTokens, getAccessTokenSync, ensureValidAccessToken, handleRedirectIfPresent };
  }

  /* ── 4) Path B: 네이티브 PKCE (외부 라이브러리 없이) ───────────────────── */
  function initWithNativePkce(cfg) {
    const STATE_KEY = "oauth_state_v1";
    const VERIFIER_KEY = "pkce_verifier_v1";

    async function login() {
      const state = randomString(24);
      const verifier = randomString(64);
      const challenge = await sha256(verifier);

      sessionStorage.setItem(STATE_KEY, state);
      sessionStorage.setItem(VERIFIER_KEY, verifier);

      const scope = encodeURIComponent("openid email profile");
      const url =
        `${cfg.hostedUi}/oauth2/authorize?` +
        `client_id=${encodeURIComponent(cfg.clientId)}` +
        `&response_type=code` +
        `&scope=${scope}` +
        `&redirect_uri=${encodeURIComponent(cfg.redirectUri)}` +
        `&state=${encodeURIComponent(state)}` +
        `&code_challenge=${encodeURIComponent(challenge)}` +
        `&code_challenge_method=S256`;

      window.location.assign(url);
    }

    async function exchangeCodeForTokens(code) {
      const verifier = sessionStorage.getItem(VERIFIER_KEY);
      if (!verifier) throw new Error("PKCE verifier not found");

      const body = new URLSearchParams();
      body.set("grant_type", "authorization_code");
      body.set("client_id", cfg.clientId);
      body.set("code", code);
      body.set("redirect_uri", cfg.redirectUri);
      body.set("code_verifier", verifier);

      const resp = await fetch(`${cfg.hostedUi}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      if (!resp.ok) {
        const t = await resp.text().catch(()=>"");
        throw new Error("Token exchange failed: " + t);
      }
      const json = await resp.json();
      const expires_at = nowSec() + (json.expires_in || 3600);
      const id_claims = json.id_token ? parseJwt(json.id_token) : null;
      saveTokens({ ...json, expires_at, id_claims });
    }

    async function refreshTokens() {
      const t = readTokens();
      if (!t?.refresh_token) return false;

      const body = new URLSearchParams();
      body.set("grant_type", "refresh_token");
      body.set("client_id", cfg.clientId);
      body.set("refresh_token", t.refresh_token);

      const resp = await fetch(`${cfg.hostedUi}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      if (!resp.ok) return false;
      const json = await resp.json();
      const expires_at = nowSec() + (json.expires_in || 3600);
      const id_claims = json.id_token ? parseJwt(json.id_token) : t.id_claims;
      saveTokens({ ...t, ...json, expires_at, id_claims });
      return true;
    }

    let refreshLock = null;
    async function ensureValidAccessToken() {
      const t = readTokens();
      if (t && nowSec() < (t.expires_at - 30)) return t.access_token;

      if (!refreshLock) {
        refreshLock = (async () => {
          try { return (await refreshTokens()) ? (readTokens()?.access_token || null) : null; }
          finally { refreshLock = null; }
        })();
      }
      return refreshLock;
    }

    async function handleRedirectIfPresent() {
      const here = new URL(window.location.href);
      if (decodeURIComponent(here.pathname) !== decodeURIComponent(new URL(cfg.redirectUri).pathname)) return;

      const code = here.searchParams.get("code");
      const state = here.searchParams.get("state");
      if (!code || !state) return;

      const expectedState = sessionStorage.getItem(STATE_KEY);
      if (!expectedState || state !== expectedState) {
        console.warn("STATE mismatch; aborting.");
        return;
      }

      await exchangeCodeForTokens(code);

      // 쿼리 제거 & 홈으로
      window.history.replaceState({}, "", cfg.postLogoutRedirectUri);
    }

    function logout() {
      clearTokens();
      const url = `${cfg.hostedUi}/logout?client_id=${encodeURIComponent(cfg.clientId)}&logout_uri=${encodeURIComponent(cfg.postLogoutRedirectUri)}`;
      window.location.assign(url);
    }

    return { login, logout, isLoggedIn, getTokens, getAccessTokenSync, ensureValidAccessToken, handleRedirectIfPresent };
  }

  /* ── 5) 부트스트랩 ──────────────────────────────────────────────────────── */
  let cfg = null;
  try { cfg = loadMetaCfg(); }
  catch (e) { console.error("[Auth] config error:", e?.message || e); }

  window.AuthReady = (async () => {
    try {
      let api = await initWithOidcClientTs(cfg);
      if (!api) api = initWithNativePkce(cfg);
      window.Auth = api;
    } catch (e) {
      console.error("[Auth] init failed:", e);
      // 스텁 유지
    }
  })();
})();
