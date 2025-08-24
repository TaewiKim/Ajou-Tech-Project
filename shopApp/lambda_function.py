# lambda_function.py  —  single-table (CHAT_TABLE) friendly
import json
import os
import time
import base64
import re
import traceback
from typing import Any, Dict
from decimal import Decimal

from chat import ChatService
from db import (
    write_message,
    fetch_recent_messages_for_conversation,
    list_conversations_for_user_single_table,  # ✅ 단일 테이블용 세션 목록
)

# ===== 환경 변수 =====
API_GATEWAY_ENDPOINT = os.getenv("API_GATEWAY_ENDPOINT", "*")  # CORS 허용 오리진
MAX_TURNS = int(os.getenv("MAX_TURNS", "12"))

MODEL_SYSTEM_PROMPT = """
너는 물품을 추천하는 판매원이야. 사용자의 상황이나 고민을 파악해서 해당 상황에 맞는 물품이 있다면 추천해줘
- 역할은 판매지만 사용자와 평범하게 대화하는 것도 좋아.
- 사용자의 고민이나 경험이 없을때 불필요한 추천은 하지 마.
- 증상이나 고민을 알더라도 명확한 원인과 해결책을 모르면 원인 파악을 우선시해.
- 상품 카드는 프런트에서 렌더링된다. 최종 답변 텍스트에는 상품명/가격/링크/번호 목록을 **나열하지 말고**, 상황 설명과 조언만 간단히 써라.
- 상품을 추천할 때는 마지막에 ‘아래 추천 상품을 확인해 주세요.’ 한 줄만 덧붙여라.
- 공손하고 사려깊게 대답하되 불필요한 수식어 사용은 줄여.
"""

# ── 로깅 ───────────────────────────────────────────────────────────────
_LOG_LEVEL = (os.getenv("LOG_LEVEL") or "info").lower()
_LEVEL_RANK = {"debug": 10, "info": 20, "warn": 30, "error": 40}
def _log(level: str, msg: str, **fields):
    if _LEVEL_RANK.get(level, 20) < _LEVEL_RANK.get(_LOG_LEVEL, 20):
        return
    rec = {"level": level, "ts": int(time.time() * 1000), "msg": msg}
    for k, v in fields.items():
        try:
            json.dumps(v, ensure_ascii=False)
            rec[k] = v
        except Exception:
            rec[k] = str(v)
    print(json.dumps(rec, ensure_ascii=False))

# ── 유틸 ───────────────────────────────────────────────────────────────
def _to_int(v):
    try:
        if isinstance(v, Decimal):
            return int(v)
        return int(v)
    except Exception:
        return 0

def _json_dumps(obj: Any) -> str:
    def _default(o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        raise TypeError
    return json.dumps(obj, ensure_ascii=False, default=_default)

def _route_tail(path: str) -> str:
    if not path: return ""
    return path.rstrip("/").rsplit("/", 1)[-1].lower()

def _match_path(raw_path: str, name: str) -> bool:
    p = (raw_path or "").lower().rstrip("/")
    return p.endswith(f"/{name}") or p.endswith(f"/shoppingapp/{name}")

def _parse_json_body(event) -> dict:
    raw = event.get("body")
    if raw is None: return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8", errors="ignore")
        except Exception as e:
            raise ValueError(f"body base64 decode 실패: {e}")
    try:
        return json.loads(raw)
    except Exception as e:
        raise ValueError(f"body JSON 파싱 실패: {e}")

def _parse_query(event) -> dict:
    qs = event.get("queryStringParameters") or {}
    if qs: return qs
    raw = event.get("rawQueryString")
    if not raw: return {}
    from urllib.parse import parse_qs
    return {k: v[0] for k, v in parse_qs(raw).items() if v}

def _cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": API_GATEWAY_ENDPOINT,
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,ANY",
        "Access-Control-Allow-Credentials": "true",
    }

def _json(status: int, body: Any):
    try:
        body_str = _json_dumps(body)
    except Exception as e:
        body_str = _json_dumps({"error": f"serialize failed: {e}"})
    return {
        "statusCode": status,
        "headers": {**_cors_headers(), "Content-Type": "application/json"},
        "body": body_str,
        "isBase64Encoded": False,
    }

def _ok(b): return _json(200, b)
def _error(s, m): return _json(s, {"error": m})

def _serve_static_file(path: str):
    static_dir = os.path.join(os.path.dirname(__file__), "webpage")
    if not os.path.isdir(static_dir):
        static_dir = os.path.dirname(__file__)  # 폴백

    def _read(p):
        with open(os.path.join(static_dir, p), "r", encoding="utf-8") as f:
            return f.read()

    html = _read("index.html"); css = _read("styles.css")
    js_bundle = "\n\n".join([f"/* ===== {n} ===== */\n{_read(n)}" for n in ["auth.js","api.js","app.js"]])

    # 외부 링크 제거
    html = re.sub(r'<link[^>]+styles\.css[^>]*>\s*', "", html, flags=re.I|re.S)
    for fname in ["config.js","auth.js","api.js","app.js"]:
        html = re.sub(rf'<script[^>]+{re.escape(fname)}[^>]*>\s*</script>\s*', "", html, flags=re.I|re.S)

    # 인라인 주입
    if re.search(r'</head\s*>', html, flags=re.I):
        html = re.sub(r'</head\s*>', lambda m: f"<style>\n{css}\n</style>\n{m.group(0)}", html, count=1, flags=re.I)
    else:
        html = f"<style>\n{css}\n</style>\n{html}"
    if re.search(r'</body\s*>', html, flags=re.I):
        html = re.sub(r'</body\s*>', lambda m: f"<script>\n{js_bundle}\n</script>\n{m.group(0)}", html, count=1, flags=re.I)
    else:
        html = html + f"\n<script>\n{js_bundle}\n</script>\n"

    return {"statusCode": 200, "headers": {**_cors_headers(), "Content-Type": "text/html; charset=utf-8"}, "body": html, "isBase64Encoded": False}

# ── JWT 유틸 (Authorizer 우선, 없으면 헤더 디코드) ─────────────────────
def _b64url_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4); return base64.urlsafe_b64decode(data + pad)

def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3: raise ValueError("invalid jwt format")
    return json.loads(_b64url_decode(parts[1]).decode("utf-8"))

def _get_auth_claims(event) -> Dict[str, Any]:
    rc = (event.get("requestContext") or {})
    jwt = (rc.get("authorizer") or {}).get("jwt") or {}
    claims = jwt.get("claims")
    if claims and claims.get("sub"): return claims

    headers = event.get("headers") or {}
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth.startswith("Bearer "): raise PermissionError("Authorization 헤더가 필요합니다.")
    token = auth[7:].strip()
    claims = _decode_jwt_payload(token)
    if not claims.get("sub"): raise PermissionError("유효한 사용자 식별자(sub)가 없습니다.")
    return claims

def _pick_nick(claims: Dict[str, Any]) -> str:
    return str(claims.get("nickname") or claims.get("preferred_username") or claims.get("cognito:username") or claims.get("username") or "")

# ── 핸들러 ─────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    try:
        method = (
            ((event.get("requestContext") or {}).get("http") or {}).get("method")
            or event.get("httpMethod")
            or ""
        ).upper()
        raw_path = event.get("rawPath") or event.get("path") or "/"
        _log("info", "req.start", method=method, path=raw_path, tail=_route_tail(raw_path))
        if method == "OPTIONS":
            return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

        # === GET /conversations : 유저의 대화 세션 목록 (단일 테이블에서 계산) ===
        if method == "GET" and (_route_tail(raw_path) == "conversations" or _match_path(raw_path, "conversations")):
            _log("info", "route.conversations")
            try:
                claims = _get_auth_claims(event)
                user_id = str(claims["sub"])
                qs = _parse_query(event)
                limit = int(qs.get("limit") or 50)
                resp = list_conversations_for_user_single_table(user_id, limit=limit)
                return _ok({"conversations": resp["items"], "nextKey": None})
            except PermissionError as e:
                return _error(401, str(e))
            except Exception as e:
                return _error(500, f"서버 오류: {e}")

        # === GET /history : 특정 세션의 메시지 목록 ===
        if method == "GET" and (_route_tail(raw_path) == "history" or _match_path(raw_path, "history")):
            _log("info", "route.history.begin")
            try:
                claims = _get_auth_claims(event)
                user_id = str(claims["sub"])
                qs = _parse_query(event)
                conv_id = (qs.get("conversationId") or "").strip()
                if not conv_id:
                    return _error(400, "conversationId는 필수입니다.")
                limit = int(qs.get("limit") or 50)
                before = qs.get("before")

                items = fetch_recent_messages_for_conversation(user_id, conv_id, limit)
                if before:
                    thr = _to_int(before)
                    items = [it for it in items if _to_int(it.get("timestamp")) < thr]

                def _norm(it: Dict[str, Any]) -> Dict[str, Any]:
                    content = it.get("content")
                    if isinstance(content, dict):
                        try: content = json.dumps(content, ensure_ascii=False)
                        except Exception: content = str(content)
                    msg = {"role": it.get("role") or "", "content": content or "", "ts": _to_int(it.get("timestamp"))}
                    if "products" in it: msg["products"] = it["products"]
                    return msg

                messages = [_norm(i) for i in items]
                next_before = str(min((m["ts"] for m in messages), default=0)) if messages else None
                _log("info", "route.history.end", convId=conv_id, count=len(messages))
                return _ok({"conversationId": conv_id, "messages": messages, "nextBefore": next_before})
            except PermissionError as e:
                return _error(401, str(e))
            except Exception as e:
                return _error(500, f"서버 오류: {e}")

        # === POST /chat : 메시지 전송 ===
        if method == "POST" and (_route_tail(raw_path) == "chat" or _match_path(raw_path, "chat")):
            try:
                # 1) 인증
                claims = _get_auth_claims(event)
                user_id = str(claims.get("sub"))
                nickname = _pick_nick(claims)

                # 2) 입력 파싱
                body = _parse_json_body(event)
                message = (body.get("message") or "").strip()
                conv_id = (body.get("conversationId") or "").strip() or f"c_{int(time.time()*1000)}"
                if not message:
                    return _error(400, "message는 필수입니다.")

                # 3) 히스토리 로드 (프롬프트 컨텍스트)
                need = MAX_TURNS * 2
                items = fetch_recent_messages_for_conversation(user_id, conv_id, need)
                _log("info", "route.chat.begin", convId=conv_id)
                def _safe(v):
                    if isinstance(v, str): return v
                    if isinstance(v, dict) and isinstance(v.get("answer"), str): return v["answer"]
                    try: return json.dumps(v, ensure_ascii=False)
                    except Exception: return str(v)

                history_msgs = [{"role": it["role"], "content": _safe(it.get("content"))} for it in items]

                # 4) GPT 호출
                messages = [
                    {"role": "system", "content": MODEL_SYSTEM_PROMPT},
                    *history_msgs,
                    {"role": "user", "content": message},
                ]
                tools = [{
                    "type": "function",
                    "function": {
                        "name": "naver_shop_search",
                        "description": "네이버 쇼핑 검색",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "display": {"type": "integer"},
                            },
                            "required": ["query"],
                        },
                    },
                }]

                service = ChatService()
                resp = service.complete(messages=messages, tools=tools)

                def _only_text(v):
                    if isinstance(v, str): return v
                    if isinstance(v, dict) and isinstance(v.get("answer"), str): return v["answer"]
                    try: return json.dumps(v, ensure_ascii=False)
                    except Exception: return str(v)

                if isinstance(resp, dict):
                    answer = resp.get("answer", "")
                    products = resp.get("products", [])
                else:
                    answer, products = str(resp), []

                answer_str = _only_text(answer)

                # 5) 저장
                ts = int(time.time() * 1000)
                # (선택) 아이템 사이즈 줄이기: 필요한 필드만 남기기 + 개수 제한
                def _slim_products(arr, limit=6):
                    keep = ("title","link","image","lprice","mallName")
                    out = []
                    for p in (arr or [])[:limit]:
                        out.append({k: p.get(k) for k in keep if k in p})
                    return out
                slim = _slim_products(products)
                write_message(user_id, conv_id, nickname or "user", "user", message, ts_ms=ts)
                write_message(user_id, conv_id, "assistant", "assistant", answer_str, ts_ms=ts + 1, products=slim)
                _log("info", "route.chat.end", convId=conv_id, answer_len=len(answer_str))
                return _ok({"answer": answer_str, "products": products, "conversationId": conv_id})
            except PermissionError as e:
                return _error(401, str(e))
            except Exception as e:
                return _error(500, f"서버 오류: {e}")

        # === 정적 번들(SPA) ===
        if method in ("GET", "HEAD", "ANY"):
            _log("info", "route.static", path=raw_path)
            return _serve_static_file(raw_path)

        return _error(404, f"{method} {raw_path} not found")

    except Exception as e:
        return _error(500, f"서버 오류(최상위): {e}")
