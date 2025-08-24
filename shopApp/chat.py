# chat.py (clean, tool-calls handled, no external deps)
import json
import os
import time
from typing import Any, Dict, List

import urllib.request
import urllib.error

from shop import naver_shop_search  # (query:str, display:int) -> list[dict]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT", "60"))


def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Minimal JSON POST with urllib + simple logging."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.time()
    print(json.dumps({"level": "info", "msg": "openai.post.begin", "url": url}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ms = int((time.time() - t0) * 1000)
            print(json.dumps({"level": "info", "msg": "openai.post.ok", "ms": ms}))
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode("utf-8", errors="ignore")
        print(json.dumps({"level": "error", "msg": "openai.http.error", "status": e.code, "body": body}))
        raise RuntimeError(f"OpenAI API 오류: {e.code} {body}") from None
    except Exception as e:
        raise RuntimeError(f"OpenAI 호출 실패: {e}") from None


class ChatService:
    @staticmethod
    def _as_list_products(x):
        if not x:
            return []
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            for k in ("items", "products", "results", "data", "list", "hits"):
                v = x.get(k)
                if isinstance(v, list):
                    return v
            vals = list(x.values())
            if vals and all(isinstance(v, dict) for v in vals):
                return vals
        return []

    @staticmethod
    def _norm_product(p: dict) -> dict:
        if not isinstance(p, dict):
            return {}
        title = p.get("title") or p.get("name") or p.get("productName") or ""
        link = p.get("link") or p.get("url") or p.get("productUrl") or ""
        image = p.get("image") or p.get("thumbnail") or p.get("imageUrl") or ""
        price = p.get("lprice") or p.get("price") or p.get("salePrice") or p.get("lowPrice") or ""
        mall = p.get("mallName") or p.get("shop") or p.get("seller") or p.get("store") or ""
        return {
            "title": str(title),
            "link": str(link),
            "image": str(image),
            "lprice": str(price) if price is not None else "",
            "mallName": str(mall),
        }

    @classmethod
    def _norm_products(cls, arr, limit=6):
        out = []
        for p in cls._as_list_products(arr)[:limit]:
            np = cls._norm_product(p)
            if np.get("title") or np.get("link"):
                out.append(np)
        return out

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        messages: [{role, content}, ...]
        tools: OpenAI tools schema
        return: {"answer": str, "products": list[dict]}
        """
        url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"

        # 1) 첫 호출
        payload = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.5}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        first = _post_json(url, payload, OPENAI_TIMEOUT)
        choice = (first.get("choices") or [{}])[0]
        msg = (choice.get("message") or {})
        tool_calls = msg.get("tool_calls") or []

        # 툴콜 없으면 텍스트만 반환
        if not tool_calls:
            return {"answer": msg.get("content", "") or "", "products": []}

        # 2) 툴콜 실행
        messages2 = messages + [{"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}]
        tool_messages = []
        collected_products = []

        for tc in tool_calls:
            if (tc.get("type") != "function") or not tc.get("function"):
                continue
            fn = tc["function"]["name"]
            raw_args = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}
            tool_call_id = tc.get("id") or f"tool_{int(time.time()*1000)}"

            if fn == "naver_shop_search":
                query = (args.get("query") or "").strip()
                display = int(args.get("display") or 6)
                try:
                    items = naver_shop_search(query=query, display=display) or []
                except Exception as e:
                    print(json.dumps({"level": "error", "msg": "tool_call.error", "err": str(e)}))
                    items = []
                norm = self._norm_products(items, limit=display)
                collected_products.extend(norm)
                tool_content = json.dumps({"ok": True, "items": norm}, ensure_ascii=False)
            else:
                tool_content = json.dumps({"ok": False, "error": f"unknown function {fn}"}, ensure_ascii=False)

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": fn,
                "content": tool_content,
            })

        # 3) 툴 결과 포함하여 두 번째 호출
        payload2 = {"model": OPENAI_MODEL, "messages": messages2 + tool_messages, "temperature": 0.5}
        final = _post_json(url, payload2, OPENAI_TIMEOUT)
        fchoice = (final.get("choices") or [{}])[0]
        fmsg = (fchoice.get("message") or {})
        answer = fmsg.get("content", "") or ""

        # 최종 결과
        try:
            print(json.dumps({"level": "info", "msg": "chat.products", "norm_len": len(collected_products)}))
        except Exception:
            pass
        return {"answer": answer, "products": collected_products}
