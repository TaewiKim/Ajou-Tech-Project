# chat.py
import json
import os
import re
import time
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

# shop.py에서 함수 임포트
from shop import naver_shop_search

# ---- 고정 엔드포인트 ----
_DEFAULT_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _is_http_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith(("http://", "https://"))


def _sanitize_url(val: object, default: str) -> str:
    if isinstance(val, str):
        v = val.strip()
        if _is_http_url(v):
            return v
    return default


class ChatService:
    def __init__(self):
        # gpt-5-nano는 존재하지 않는 모델이므로, gpt-4o-mini와 같이 실제 존재하는 모델로 수정하는 것이 좋습니다.
        self.model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        env_url_raw = os.getenv("OPENAI_BASE_URL")
        base_url = _sanitize_url(env_url_raw, _DEFAULT_CHAT_URL)
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

        if not _is_http_url(self.base_url):
            raise RuntimeError(f"잘못된 OPENAI_BASE_URL / base_url: {repr(self.base_url)}")

    # ---------------- 내부 유틸 ---------------- #

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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
            print(json.dumps(
                {"level": "error", "msg": "openai.unknown.error", "err": str(e)},
                ensure_ascii=False
            ))
            raise

    def _extract_response(self, data: Dict[str, Any]) -> str:
        """
        Chat Completions 응답에서 최종 텍스트를 추출.
        """
        choices = data.get("choices")
        if not (isinstance(choices, list) and choices):
            raise ValueError(f"응답에서 choices를 찾을 수 없습니다. keys={list(data.keys())[:10]}")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("응답에서 message를 찾을 수 없습니다.")

        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        
        # content가 없으면 함수 호출 응답일 수 있음
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            # 함수 호출 정보는 이 시점에서 직접 반환하지 않고, 호출자(complete 메서드)가 처리해야 함
            return "" # 또는 적절한 예외 처리

        raise ValueError("응답에서 텍스트 또는 함수 호출을 추출하지 못했습니다.")

    # ---------------- 외부 API ---------------- #

    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
            raise ValueError("messages 형식이 올바르지 않습니다.")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        # 1차 GPT 호출 (함수 호출 여부 판단)
        response_data = self._post(payload)

        try:
            message_from_response = response_data["choices"][0]["message"]
            tool_calls = message_from_response.get("tool_calls")
        except (KeyError, IndexError):
            tool_calls = None

        products: List[Dict[str, Any]] = []
        answer: str = ""

        if tool_calls:
            tool_call = tool_calls[0]
            function_name = tool_call["function"]["name"]

            if function_name == "naver_shop_search":
                try:
                    function_args = json.loads(tool_call["function"]["arguments"])
                    query = function_args.get("query")

                    # 네이버 쇼핑 검색 실행
                    search_results = naver_shop_search(query)

                    if not search_results:
                        products = []
                        tool_result_str = json.dumps({"result": "상품을 찾을 수 없습니다."})
                    else:
                        # HTML 태그 제거 및 필요한 필드만 정리
                        clean_results = []
                        for item in search_results:
                            clean_title = re.sub('<[^>]+>', '', item['title'])
                            clean_results.append({
                                "title": clean_title,
                                "link": item['link'],
                                "image": item['image'],
                                "lprice": item['lprice'],
                                "mallName": item['mallName'],
                            })
                        products = clean_results
                        tool_result_str = json.dumps(clean_results, ensure_ascii=False)

                    # 네이버 검색 결과를 다시 GPT에게 전달
                    messages.append(message_from_response)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function_name,
                        "content": tool_result_str,
                    })
                    messages.append({
                        "role": "system",
                        "content": "상품 정보는 카드로 보여준다. 이 이후의 텍스트 답변에는 상품명/가격/링크/번호 목록을 넣지 말고, 설명만 간단히 작성하라."
                    })
                    # 2차 GPT 호출 (최종 답변 텍스트 생성)
                    final_response_data = self._post(payload)
                    answer = self._extract_response(final_response_data)

                    return {"answer": answer, "products": products}

                except Exception as e:
                    print(json.dumps({"level": "error", "msg": "tool_call.error", "err": str(e)}))
                    return {"answer": "상품 추천 기능 실행 중 오류가 발생했습니다.", "products": []}

        # 함수 호출 없는 경우 → 바로 텍스트 응답
        answer = self._extract_response(response_data)
        return {"answer": answer, "products": []}
