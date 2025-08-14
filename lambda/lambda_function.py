# lambda_function.py
import os
import json
from decimal import Decimal
from typing import Any, Dict, Tuple
import mimetypes
import base64
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.getenv("TABLE_NAME")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)

def _assert_keys(evt: Dict[str, Any]) -> Tuple[str, str]:
    if "userId" not in evt or "timestamp" not in evt:
        raise ValueError("`userId`와 `timestamp`는 필수입니다.")
    return str(evt["userId"]), str(evt["timestamp"])

def _build_update_expression(data: Dict[str, Any]):
    if not data:
        raise ValueError("업데이트할 data가 없습니다.")
    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(data.items()):
        if v is None:
            continue
        nk, vk = f"#n{i}", f":v{i}"
        names[nk] = k
        values[vk] = v
        set_parts.append(f"{nk} = {vk}")
    if not set_parts:
        raise ValueError("유효한 업데이트 필드가 없습니다.")
    return "SET " + ", ".join(set_parts), names, values

def response_json(status: int, body: Any, extra_headers: Dict[str, str] | None = None):
    headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
    if extra_headers: headers.update(extra_headers)
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, cls=DecimalEncoder, ensure_ascii=False),
    }

def response_static(body, content_type="text/plain; charset=utf-8", status=200, cache="max-age=300"):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Cache-Control": cache,
            # CORS (정적 파일도 안전하게 허용)
            "Access-Control-Allow-Origin": "*",
        },
        "body": body,
        "isBase64Encoded": False,
    }

def _guess_mime(path):
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        # 기본값들 보정
        if path.endswith(".css"): mime = "text/css"
        elif path.endswith(".js"): mime = "application/javascript"
        else: mime = "text/plain"
    if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
        mime += "; charset=utf-8"
    return mime

def _strip_stage_prefix(path, event):
    """
    API Gateway HTTP API(v2) 기본 도메인 사용 시 rawPath가 '/{stage}/...' 형태.
    커스텀 도메인이면 stage가 안 붙을 수 있음.
    """
    try:
        stage = event.get("requestContext", {}).get("stage")
        if stage:
            pref = f"/{stage}"
            if path.startswith(pref + "/") or path == pref:
                path = path[len(pref):] or "/"
    except Exception:
        pass
    return path

def _normalize_request_path(event):
    path = (event.get("rawPath") or event.get("path") or "/") or "/"
    path = _strip_stage_prefix(path, event)
    if "?" in path:
        path = path.split("?", 1)[0]
    low = path.lower()

    # Treat common entrypoints as index.html
    ui_roots = {"/", "/ui", "/index", "/index.html",
                "/lambda-crud", "/lambda-crud/"}  # <-- add these
    if low in ui_roots:
        return "/index.html"

    if low.startswith("/webpage/"):
        low = low[len("/webpage"):] or "/index.html"
    return low

def serve_single_file_ui(root_dir):
    index_path = os.path.join(root_dir, "webpage", "index.html")
    styles_path = os.path.join(root_dir, "webpage", "styles.css")
    app_path = os.path.join(root_dir, "webpage", "app.js")

    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    with open(styles_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    with open(app_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    # <link rel="stylesheet" href="./styles.css"> → <style>...</style>
    html_content = html_content.replace(
        '<link rel="stylesheet" href="./styles.css" />',
        f"<style>\n{css_content}\n</style>"
    )

    # <script src="./app.js" defer></script> → <script>...</script>
    html_content = html_content.replace(
        '<script src="./app.js" defer></script>',
        f"<script>\n{js_content}\n</script>"
    )

    return response_static(html_content, "text/html; charset=utf-8", 200, cache="no-store")

def _to_bool(v):
    if isinstance(v, bool): return v
    if v is None: return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")

# ─────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────
def create_item(evt: Dict[str, Any]):
    user_id, ts = _assert_keys(evt)
    data = evt.get("data", {}) or {}
    overwrite = _to_bool(evt.get("overwrite", False))
    if isinstance(data, str):
        # 쿼리스트링으로 들어온 JSON 문자열 처리
        data = json.loads(data)

    item = {"userId": user_id, "timestamp": ts, **data}
    try:
        kwargs = {"Item": item}
        if not overwrite:
            kwargs["ConditionExpression"] = "attribute_not_exists(userId) AND attribute_not_exists(#ts)"
            kwargs["ExpressionAttributeNames"] = {"#ts": "timestamp"}
        table.put_item(**kwargs)
        return response_json(200, {"message": "created", "item": item})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response_json(409, {"message": "already exists"})
        raise

def read_item(evt: Dict[str, Any]):
    user_id, ts = _assert_keys(evt)
    res = table.get_item(Key={"userId": user_id, "timestamp": ts})
    return response_json(200, res.get("Item"))

def update_item(evt: Dict[str, Any]):
    user_id, ts = _assert_keys(evt)
    data = evt.get("data", {}) or {}
    if isinstance(data, str):
        data = json.loads(data)
    expr, names, values = _build_update_expression(data)
    res = table.update_item(
        Key={"userId": user_id, "timestamp": ts},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return response_json(200, {"message": "updated", "item": res.get("Attributes")})

def delete_item(evt: Dict[str, Any]):
    user_id, ts = _assert_keys(evt)
    table.delete_item(Key={"userId": user_id, "timestamp": ts})
    return response_json(200, {"message": "deleted"})

def list_items(evt: Dict[str, Any]):
    if "userId" not in evt:
        raise ValueError("`userId`는 필수입니다.")
    user_id = str(evt["userId"])
    ascending = _to_bool(evt.get("ascending", True))
    res = table.query(
        KeyConditionExpression=Key("userId").eq(user_id),
        ScanIndexForward=ascending,
    )
    return response_json(200, res.get("Items", []))

# ─────────────────────────────────────────────────────────────
# lambda_Handler
# ─────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    """
    - GET (쿼리스트링에 action 없음)  → UI HTML 반환
    - POST → CRUD
    """
    try:
        # API Gateway v2(httpApi) / v1(restApi) 모두 대응
        method = (
            (event.get("requestContext", {}) or {}).get("http", {}).get("method")
            or event.get("httpMethod")
            or ""
        ).upper()

        # 1) OPTIONS 프리플라이트 우선 처리 (선택)
        if method == "OPTIONS":
            return {
                "statusCode": 204,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                    "Access-Control-Max-Age": "600",
                },
                "body": "",
            }

        # 쿼리 파라미터를 상위로 펼쳐서 기존 로직과 호환
        qs = event.get("queryStringParameters") or {}
        evt: Dict[str, Any] = {**event, **qs}

        # body JSON이 있으면 병합(POST 대비)
        body = event.get("body")
        if body:
            try:
                # HTTP API v2는 base64Encoding 여부가 올 수 있음
                if event.get("isBase64Encoded"):
                    body = json.loads(
                        base64.b64decode(body.encode("utf-8")).decode("utf-8")
                    )
                else:
                    body = json.loads(body)
                # 쿼리스트링보다 body를 우선
                evt.update(body if isinstance(body, dict) else {})
            except Exception:
                pass

        action = (str(evt.get("action")) if evt.get("action") is not None else "").lower()

        # GET 이고 action이 없으면 UI 반환
        path = (event.get("rawPath") or event.get("path") or "/").lower()
        if method == "GET" and (not action or action == "ui"):
            current_dir = os.path.dirname(__file__)
            return serve_single_file_ui(current_dir)

        # CRUD 분기
        if action == "create":
            return create_item(evt)
        elif action == "read":
            return read_item(evt)
        elif action == "update":
            return update_item(evt)
        elif action == "delete":
            return delete_item(evt)
        elif action == "list":
            return list_items(evt)
        else:
            # 알 수 없는 액션 → UI로 유도
            return response_json(400, {"message": "Invalid action. Try '?action=list' or open the root path for UI."})

    except (ValueError, KeyError) as e:
        return response_json(400, {"message": str(e)})
    except ClientError as e:
        return response_json(500, {"message": e.response["Error"]})
    except Exception as e:
        return response_json(500, {"message": str(e)})
