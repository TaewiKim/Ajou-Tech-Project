# lambda_function.py
import json
import os
import sys
import time
import base64
import re
import traceback
from typing import Any, Dict

from chat import ChatService
from db import write_message, fetch_recent_messages_for_conversation

# ===== 환경 변수 =====
API_GATEWAY_ENDPOINT = os.getenv("API_GATEWAY_ENDPOINT", "*")  # CORS

MODEL_SYSTEM_PROMPT = """
You are a helpful assistant.
- Keep it tight: 1–2 sentences; at most 3 bullets if needed.
- No unnecessary prefaces, apologies, or thanks.
- If you don't know, don't guess—say "I don't know" and ask for the single most needed detail in one line.
- Ask only one clear question, and only when necessary.
- Keep code/examples minimal; give explanations only on request.
- Reply in Korean unless the user requests otherwise.
- 공손하고 사려깊게 대답해줘.
"""

MAX_TURNS = int(os.getenv("MAX_TURNS", "12"))

# ===== 공통 유틸 =====
_LOG_LEVEL = (os.getenv("LOG_LEVEL") or "info").lower()
_LEVEL_RANK = {"debug":10, "info":20, "warn":30, "error":40}
def _log(level:str, msg:str, **fields):
    if _LEVEL_RANK.get(level, 20) < _LEVEL_RANK.get(_LOG_LEVEL, 20):
        return
    rec = {"level": level, "ts": int(time.time()*1000), "msg": msg}
    # JSON 직렬화 안전 처리
    for k, v in fields.items():
        try:
            json.dumps(v)  # 직렬화 가능?
            rec[k] = v
        except Exception:
            rec[k] = str(v)
    print(json.dumps(rec, ensure_ascii=False))

def _route_tail(path: str) -> str:
    if not path:
        return ""
    return path.rstrip("/").rsplit("/", 1)[-1].lower()

# 유틸: Base64 여부 고려한 JSON 바디 파싱
def _parse_json_body(event) -> dict:
    raw = event.get("body")
    if raw is None:
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8", errors="ignore")
        except Exception as e:
            raise ValueError(f"body base64 decode 실패: {e}")
    try:
        return json.loads(raw)
    except Exception as e:
        raise ValueError(f"body JSON 파싱 실패: {e}")

def _cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": API_GATEWAY_ENDPOINT,
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,ANY",
        "Access-Control-Allow-Credentials": "true",
    }

def _json(status: int, body: Any):
    try:
        body_str = json.dumps(body, ensure_ascii=False)
    except Exception as e:
        # JSON 직렬화 실패까지 방어
        body_str = json.dumps({"error": f"serialize failed: {e}"}, ensure_ascii=False)

    return {
        "statusCode": status,
        "headers": {**_cors_headers(), "Content-Type": "application/json"},
        "body": body_str,
        "isBase64Encoded": False,
    }

def _ok(body: Any):
    return _json(200, body)

def _error(status: int, msg: str):
    return _json(status, {"error": msg})

def _serve_static_file(path: str):
    # 단일 파일 HTML로 번들하여 서빙
    static_dir = os.path.join(os.path.dirname(__file__), "webpage")

    def _read(p): 
        with open(os.path.join(static_dir, p), "r", encoding="utf-8") as f:
            return f.read()

    html = _read("index.html")
    css = _read("styles.css")

    js_bundle_parts = []
    for name in ["auth.js", "api.js", "app.js"]:
        js_bundle_parts.append(f"/* ===== {name} ===== */\n" + _read(name))
    js_bundle = "\n\n".join(js_bundle_parts)

    # 외부 링크 제거 후 인라인 주입
    html = re.sub(r'<link[^>]+href=["\'][^"\']*styles\.css[^"\']*["\'][^>]*>\s*', "", html, flags=re.I|re.S)
    for fname in ["config.js", "auth.js", "api.js", "app.js"]:
        pattern = rf'<script[^>]+src=["\'][^"\']*{re.escape(fname)}[^"\']*["\'][^>]*>\s*</script>\s*'
        html = re.sub(pattern, "", html, flags=re.I|re.S)

    if re.search(r'</head\s*>', html, flags=re.I):
        html = re.sub(
            r'</head\s*>',
            lambda m: f"<style>\n{css}\n</style>\n{m.group(0)}",
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = f"<style>\n{css}\n</style>\n" + html

    # </body> 주입 (없으면 append)
    if re.search(r'</body\s*>', html, flags=re.I):
        html = re.sub(
            r'</body\s*>',
            lambda m: f"<script>\n{js_bundle}\n</script>\n{m.group(0)}",
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = html + f"\n<script>\n{js_bundle}\n</script>\n"

    return {
        "statusCode": 200,
        "headers": {**_cors_headers(), "Content-Type": "text/html; charset=utf-8"},
        "body": html,
        "isBase64Encoded": False,
    }

# ===== JWT 유틸 (서명 검증 없이 payload만 디코드) =====
def _b64url_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)

def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid jwt format")
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        return payload
    except Exception as e:
        raise RuntimeError(f"JWT 디코드 실패: {e}")

def _get_auth_claims(event) -> Dict[str, Any]:
    headers = event.get("headers") or {}
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise PermissionError("Authorization 헤더가 필요합니다.")
    token = auth[7:].strip()
    claims = _decode_jwt_payload(token)
    if not claims.get("sub"):
        raise PermissionError("유효한 사용자 식별자(sub)가 없습니다.")
    return claims

# ===== Lambda 핸들러 =====
def lambda_handler(event, context):
    try:
        method = (
            ((event.get("requestContext") or {}).get("http") or {}).get("method")
            or event.get("httpMethod")
            or ""
        ).upper()
        raw_path = event.get("rawPath") or event.get("path") or "/"
        rid = getattr(context, "aws_request_id", None)

        # 요청 개요 로그
        hdrs = event.get("headers") or {}
        has_auth = bool(hdrs.get("authorization") or hdrs.get("Authorization"))
        _log(
            "info",
            "req.start",
            rid=rid,
            method=method,
            path=raw_path,
            tail=_route_tail(raw_path),
            isBase64=bool(event.get("isBase64Encoded")),
            hasAuth=has_auth,
        )

        if method == "OPTIONS":
            return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

        # === POST /chat ===
        if method == "POST" and _route_tail(raw_path) == "chat":
            try:
                # 인증
                t0 = time.time()
                claims = _get_auth_claims(event)
                user_id = str(claims.get("sub"))
                _log("debug", "auth.ok", rid=rid, userId=user_id, ms=int((time.time() - t0) * 1000))

                # 입력 파싱
                t0 = time.time()
                body = _parse_json_body(event)
                msg_raw = body.get("message")
                message = (msg_raw if isinstance(msg_raw, str) else "").strip()
                conversation_id = body.get("conversationId") or "default"
                if not isinstance(conversation_id, str):
                    conversation_id = "default"
                conversation_id = conversation_id.strip() or "default"
                _log(
                    "debug",
                    "body.parsed",
                    rid=rid,
                    message_len=len(message),
                    convId=conversation_id,
                    ms=int((time.time() - t0) * 1000),
                )

                if not message:
                    _log("warn", "body.invalid", rid=rid, reason="empty message")
                    return _error(400, "message는 필수입니다.")

                # 히스토리 로드
                t0 = time.time()
                need = MAX_TURNS * 2
                items = fetch_recent_messages_for_conversation(user_id, conversation_id, need)
                _log(
                    "debug",
                    "ddb.history.loaded",
                    rid=rid,
                    count=len(items),
                    ms=int((time.time() - t0) * 1000),
                )

                history_msgs = [{"role": it["role"], "content": it["content"]} for it in items]
                messages = [
                    {"role": "system", "content": MODEL_SYSTEM_PROMPT},
                    *history_msgs,
                    {"role": "user", "content": message},
                ]

                # 모델 호출 (예외 시 반드시 표준 에러 응답)
                t0 = time.time()
                service = ChatService()
                try:
                    answer = service.complete(messages)
                    _log("info", "openai.ok", rid=rid, answer_len=len(answer), ms=int((time.time() - t0) * 1000))
                except Exception as e:
                    _log("error", "openai.fail", rid=rid, err=str(e), stack=traceback.format_exc())
                    return _error(500, f"OpenAI 호출 실패: {e}")

                # 저장
                t0 = time.time()
                ts = int(time.time() * 1000)
                write_message(user_id, conversation_id, "user", message, ts_ms=ts)
                write_message(user_id, conversation_id, "assistant", answer, ts_ms=ts + 1)
                _log("debug", "ddb.write.ok", rid=rid, writes=2, ms=int((time.time() - t0) * 1000))

                _log("info", "req.done", rid=rid, status=200)
                return _ok({"answer": answer, "conversationId": conversation_id})

            except PermissionError as e:
                _log("warn", "auth.fail", rid=rid, err=str(e))
                return _error(401, str(e))
            except Exception as e:
                _log("error", "chat.error", rid=rid, err=str(e), stack=traceback.format_exc())
                return _error(500, f"서버 오류: {e}")

        # 정적 번들
        if method in ("GET", "HEAD", "ANY"):
            return _serve_static_file(raw_path)

        _log("warn", "route.miss", rid=rid, method=method, path=raw_path)
        return _error(404, f"{method} {raw_path} not found")

    except Exception as e:
        _log("error", "fatal", err=str(e), stack=traceback.format_exc())
        return _error(500, f"서버 오류(최상위): {e}")