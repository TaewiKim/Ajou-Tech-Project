# chat.py
import json
import os
import time
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

# ---- 고정 엔드포인트 ----
_DEFAULT_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _is_http_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith(("http://", "https://"))


def _sanitize_url(val: object, default: str) -> str:
    """
    환경변수나 외부 값이 Ellipsis(...) 등 비문자 타입이거나
    잘못된 문자열일 때 기본값으로 보정.
    """
    if isinstance(val, str):
        v = val.strip()
        if _is_http_url(v):
            return v
    return default


class ChatService:
    """
    OpenAI Chat Completions 호출 전담 서비스.
    ENV:
      - OPENAI_API_KEY (필수)
      - OPENAI_MODEL (기본: gpt-5-nano)
      - OPENAI_BASE_URL (선택, 기본: https://api.openai.com/v1/chat/completions)
      - OPENAI_TIMEOUT (초, 기본: 60)
    """

    def __init__(self):
        self.model: str = os.getenv("OPENAI_MODEL", "gpt-5-nano")

        env_url_raw = os.getenv("OPENAI_BASE_URL")
        base_url = _sanitize_url(env_url_raw, _DEFAULT_CHAT_URL)

        # /responses 등 다른 경로가 들어오면 강제로 /chat/completions 로 교정
        forced = False
        if not base_url.rstrip("/").endswith("/v1/chat/completions"):
            forced = True
            base_url = _DEFAULT_CHAT_URL

        self.base_url: str = base_url

        self.api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        if not self.api_key or not isinstance(self.api_key, str) or not self.api_key.strip():
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            self.timeout: int = int(os.getenv("OPENAI_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60

        # 설정 로그
        print(json.dumps(
            {
                "level": "info",
                "msg": "openai.config",
                "model": self.model,
                "base_url": self.base_url,
                "base_url_type": str(type(self.base_url)),
                "timeout_sec": self.timeout,
                "env_base_url_raw": env_url_raw,
                "forced_chat_completions": forced,
            },
            ensure_ascii=False
        ))

        # 최종 방어선: 잘못된 URL이면 즉시 실패
        if not _is_http_url(self.base_url):
            raise RuntimeError(f"잘못된 OPENAI_BASE_URL / base_url: {repr(self.base_url)}")

    # ---------------- 내부 유틸 ---------------- #

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        공통 POST 호출. JSON 응답을 dict로 반환.
        """
        # 런타임 변조 방지: 호출 직전에도 점검
        if not _is_http_url(self.base_url):
            raise RuntimeError(f"잘못된 OPENAI_BASE_URL / base_url: {repr(self.base_url)}")

        t0 = time.time()
        try:
            print(json.dumps({"level": "info", "msg": "openai.post.begin", "url": self.base_url}, ensure_ascii=False))
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self.base_url,
                data=body_bytes,
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read().decode("utf-8", errors="replace")
                data = json.loads(raw)

            print(json.dumps(
                {"level": "info", "msg": "openai.post.ok", "ms": int((time.time() - t0) * 1000)},
                ensure_ascii=False
            ))
            return data

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print(json.dumps(
                {
                    "level": "error",
                    "msg": "openai.http.error",
                    "status": e.code,
                    "body": body[:1000],
                },
                ensure_ascii=False
            ))
            raise RuntimeError(f"OpenAI API 오류: {e.code} {body}") from e

        except urllib.error.URLError as e:
            print(json.dumps(
                {"level": "error", "msg": "openai.url.error", "reason": getattr(e, "reason", str(e))},
                ensure_ascii=False
            ))
            raise RuntimeError(f"OpenAI API 연결 실패: {getattr(e, 'reason', str(e))}") from e

        except Exception as e:
            # JSON 파싱 실패 등
            print(json.dumps(
                {"level": "error", "msg": "openai.unknown.error", "err": str(e)},
                ensure_ascii=False
            ))
            raise

    @staticmethod
    def _extract_text_from_response(data: Dict[str, Any]) -> str:
        """
        Chat Completions 응답에서 텍스트를 최대한 안전하게 추출.
        """
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    return content
                # content가 조각 리스트로 오는 경우(드문 케이스) 처리
                if isinstance(content, list):
                    parts = []
                    for p in content:
                        if isinstance(p, dict) and isinstance(p.get("text"), str):
                            parts.append(p["text"])
                    if parts:
                        return "\n".join(parts).strip()

        # 실패 시 디버깅 하도록 키만 표시
        raise ValueError(f"응답에서 텍스트를 추출하지 못했습니다. keys={list(data.keys())[:10]}")

    # ---------------- 외부 API ---------------- #

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """
        messages: [{"role":"system"|"user"|"assistant", "content":"..."}]
        반환: 생성된 텍스트(문자열)
        """
        # 입력 방어
        if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
            raise ValueError("messages 형식이 올바르지 않습니다. List[Dict] 이어야 합니다.")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            # temperature 등은 지정하지 않음(기본값)
        }

        data = self._post(payload)
        text = self._extract_text_from_response(data).strip()

        print(json.dumps(
            {"level": "info", "msg": "openai.answer.size", "len": len(text)},
            ensure_ascii=False
        ))
        return text
