# db.py
import os
import time
from typing import List, Dict, Any, Optional
from time import time as _now
from json import dumps as _dumps

import boto3
from boto3.dynamodb.conditions import Key

_CHAT_TABLE = os.getenv("CHAT_TABLE")
if not _CHAT_TABLE:
    raise RuntimeError("CHAT_TABLE 환경변수가 필요합니다.")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_CHAT_TABLE)

# ===== logging helpers =====
def _dlog(level: str, msg: str, **kw):
    try:
        print(_dumps({"level": level, "ts": int(_now() * 1000), "msg": msg, **kw}, ensure_ascii=False))
    except Exception:
        print(f'{{"level":"{level}","msg":"{msg}"}}')

_PAGE_LIMIT = int(os.getenv("DDB_PAGE_LIMIT", "200"))
_MAX_SCAN_PAGES = int(os.getenv("DDB_MAX_SCAN_PAGES", "5"))

_ZERO_PAD = int(os.getenv("TS_ZERO_PAD", "13"))  # 밀리초 13자리

def _ts_str(ts_ms: int) -> str:
    # 사전식 정렬 == 시간 정렬이 되도록 zero-pad
    return f"{int(ts_ms):0{_ZERO_PAD}d}"

def write_message(
    user_id: str,
    conversation_id: str,
    nickname: str,
    role: str,
    content: str,
    ts_ms: Optional[int] = None,
) -> int:
    """단일 메시지 저장 (PK: userId, SK: timestamp[ms] 문자열)."""
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    ts_str = _ts_str(ts_ms)  # ← 반드시 문자열

    item = {
        "userId": user_id,
        "timestamp": ts_str,           # ← 문자열(S)로 저장
        "conversationId": conversation_id,
        "role": role,
        "nickname": nickname,
        "content": content,
    }

    t0 = _now()
    # 저장 직전 타입 찍기 (디버깅용)
    _dlog("debug", "ddb.put.before", pk=user_id, sk=ts_str, sk_type="S", conv=conversation_id, role=role)
    _table.put_item(Item=item)
    _dlog("debug", "ddb.put",
          pk=user_id, sk=ts_str, conv=conversation_id, role=role,
          ms=int((_now() - t0) * 1000))
    return ts_ms

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
    t_total = _now()

    while len(collected) < limit_needed and pages < _MAX_SCAN_PAGES:
        kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ScanIndexForward": False,  # 최신 → 과거
            "Limit": _PAGE_LIMIT,
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        t_page = _now()
        resp = _table.query(**kwargs)
        _dlog("debug", "ddb.query.page",
              pk=user_id,
              items=len(resp.get("Items", [])),
              lek=bool(resp.get("LastEvaluatedKey")),
              ms=int((_now() - t_page) * 1000))

        items = resp.get("Items", [])
        for it in items:
            if it.get("conversationId") == conversation_id:
                collected.append(it)
                if len(collected) >= limit_needed:
                    break

        last_evaluated_key = resp.get("LastEvaluatedKey")
        pages += 1
        if not last_evaluated_key:
            break

    # 안전하게 숫자 변환해서 정렬 (문자열 13자리면 그대로 int 변환 OK)
    def _to_int_ts(v):
        try:
            from decimal import Decimal
            if isinstance(v, Decimal):
                return int(v)
            return int(v)
        except Exception:
            return 0

    collected.sort(key=lambda x: _to_int_ts(x.get("timestamp")))
    _dlog("debug", "ddb.history.done",
          conv=conversation_id,
          count=len(collected),
          pages=pages,
          total_ms=int((_now() - t_total) * 1000))
    return collected
