# db.py  —  Single-table (CHAT_TABLE) DynamoDB helpers
# PK: userId (S), SK: timestamp (S: 13-digit epoch ms string)

import os
import time
import json
from typing import Any, Dict, List, Optional
from collections import OrderedDict
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

# ===== Config =====
CHAT_TABLE = os.environ["CHAT_TABLE"]  # 반드시 설정
_PAGE_LIMIT = int(os.getenv("DB_PAGE_LIMIT", "100"))
_MAX_PAGES = int(os.getenv("DB_MAX_PAGES", "10"))

_DDB = boto3.resource("dynamodb")
_table = _DDB.Table(CHAT_TABLE)

_LOG_LEVEL = (os.getenv("LOG_LEVEL") or "info").lower()
_LEVEL_RANK = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def _dlog(level: str, msg: str, **fields):
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


def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_int_ts(v: Any) -> int:
    # timestamp가 "1724300000000" 같은 문자열이어도 안전하게 int로 변환
    try:
        if isinstance(v, Decimal):
            return int(v)
        return int(v)
    except Exception:
        return 0


# =====================================================================
# Writes
# =====================================================================
def write_message(
    user_id: str,
    conversation_id: str,
    display_name: str,
    role: str,
    content: Any,
    ts_ms: Optional[int] = None,
    products: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    메시지 1건 저장 (단일 테이블)
    - PK: userId (S)
    - SK: timestamp (S, 13자리 epoch ms 문자열)  ← ★ 중요
    - Filter용: conversationId
    - 기타: role, content(문자열 권장), sender(display_name), products(선택)
    """
    ts = int(ts_ms or _now_ms())
    ts_str = str(ts)  # ← ★ DynamoDB SK가 String이므로 문자열로 저장

    if not isinstance(content, (str, int, float)):
        try:
            content = json.dumps(content, ensure_ascii=False)
        except Exception:
            content = str(content)

    item: Dict[str, Any] = {
        "userId": user_id,
        "timestamp": ts_str,            # ← ★ 여기
        "conversationId": conversation_id,
        "role": role,
        "sender": display_name or "",
        "content": content,
    }
    if products:
        item["products"] = products

    _table.put_item(Item=item)
    _dlog("debug", "ddb.put", pk=user_id, ts=ts_str, cid=conversation_id, role=role)


# =====================================================================
# Reads
# =====================================================================
def fetch_recent_messages_for_conversation(
    user_id: str,
    conversation_id: str,
    limit_needed: int,
) -> List[Dict[str, Any]]:
    """
    같은 userId 파티션에서 최신→과거로 쿼리하며 conversationId로 필터링해서 수집.
    수집 후 시간 오름차순으로 정렬해서 반환.
    """
    collected: List[Dict[str, Any]] = []
    last_evaluated_key = None
    pages = 0
    t_total = time.time()

    while len(collected) < limit_needed and pages < _MAX_PAGES:
        kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ScanIndexForward": False,  # 최신 → 과거 (String SK지만 13자리면 사전순==시간순)
            "Limit": _PAGE_LIMIT,
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        t_page = time.time()
        resp = _table.query(**kwargs)
        items = resp.get("Items", [])

        _dlog(
            "debug",
            "ddb.query.page",
            pk=user_id,
            items=len(items),
            lek=bool(resp.get("LastEvaluatedKey")),
            ms=int((time.time() - t_page) * 1000),
        )

        for it in items:
            if it.get("conversationId") == conversation_id:
                collected.append(it)
                if len(collected) >= limit_needed:
                    break

        last_evaluated_key = resp.get("LastEvaluatedKey")
        pages += 1
        if not last_evaluated_key:
            break

    # timestamp 오름차순으로 정렬
    collected.sort(key=lambda x: _to_int_ts(x.get("timestamp")))

    _dlog(
        "debug",
        "ddb.history.done",
        conv=conversation_id,
        count=len(collected),
        pages=pages,
        total_ms=int((time.time() - t_total) * 1000),
    )
    return collected


def fetch_recent_messages_for_user(
    user_id: str,
    limit_needed: int,
) -> List[Dict[str, Any]]:
    """
    같은 userId 파티션에서 최신→과거로 쿼리하여 최근 메시지를 conversationId 무시하고 수집.
    반환은 시간 오름차순.
    """
    collected: List[Dict[str, Any]] = []
    last_evaluated_key = None
    pages = 0

    while len(collected) < limit_needed and pages < _MAX_PAGES:
        kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ScanIndexForward": False,
            "Limit": _PAGE_LIMIT,
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        resp = _table.query(**kwargs)
        collected.extend(resp.get("Items", []))

        last_evaluated_key = resp.get("LastEvaluatedKey")
        pages += 1
        if not last_evaluated_key:
            break

    collected.sort(key=lambda x: _to_int_ts(x.get("timestamp")))
    return collected


def list_conversations_for_user_single_table(
    user_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    단일 테이블에서 유저의 대화 세션 목록을 만들어 반환.
    - userId 파티션을 최신→과거로 페이지네이션하며 conversationId별 요약을 구성
    - 결과는 lastTs 기준 내림차순 정렬 후 limit만큼 자름
    반환 형식:
    {
      "items": [
        {"conversationId": "...", "lastTs": 123, "lastSnippet": "...", "msgCount": 42, "updatedAt": 123}
      ],
      "lastEvaluatedKey": None
    }
    """
    seen: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    last_key = None
    pages = 0
    t_total = time.time()

    while len(seen) < limit and pages < _MAX_PAGES:
        kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ScanIndexForward": False,  # 최신 → 과거
            "Limit": _PAGE_LIMIT,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        t_page = time.time()
        resp = _table.query(**kwargs)
        items = resp.get("Items", [])

        _dlog(
            "debug",
            "ddb.query.page.convlist",
            pk=user_id,
            items=len(items),
            lek=bool(resp.get("LastEvaluatedKey")),
            ms=int((time.time() - t_page) * 1000),
        )

        for it in items:
            cid = it.get("conversationId")
            if not cid:
                continue

            ts = _to_int_ts(it.get("timestamp"))
            content = it.get("content")
            if not isinstance(content, (str, int, float)):
                try:
                    content = json.dumps(content, ensure_ascii=False)
                except Exception:
                    content = str(content)

            entry = seen.get(cid)
            if entry is None:
                entry = {
                    "conversationId": cid,
                    "lastTs": ts,
                    "lastSnippet": "",
                    "msgCount": 0,
                    "updatedAt": ts,
                }
                seen[cid] = entry

            entry["msgCount"] += 1

            # 최신 메시지로 갱신, 스니펫은 assistant 우선
            if ts >= entry["lastTs"]:
                entry["lastTs"] = ts
                entry["updatedAt"] = ts
                if it.get("role") == "assistant" or not entry["lastSnippet"]:
                    entry["lastSnippet"] = (str(content) if content is not None else "")[:120]

        last_key = resp.get("LastEvaluatedKey")
        pages += 1
        if not last_key:
            break

    items_out = sorted(seen.values(), key=lambda x: x["lastTs"], reverse=True)[:limit]

    _dlog(
        "debug",
        "ddb.convlist.done",
        pk=user_id,
        conv_count=len(items_out),
        pages=pages,
        total_ms=int((time.time() - t_total) * 1000),
    )
    return {"items": items_out, "lastEvaluatedKey": None}
