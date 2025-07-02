import boto3
import json

dynamo = boto3.client('dynamodb')
table_name = 'DynamoDB-Taewi-CRUD'

def respond(err, res=None, is_options=False):
    return {
        'statusCode': '200' if is_options else ('400' if err else '200'),
        'body': json.dumps("CORS preflight successful") if is_options else (str(err) if err else json.dumps(res)),
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # 모든 도메인 허용
            'Access-Control-Allow-Methods': 'OPTIONS, POST, GET, PUT, DELETE',  # 허용할 HTTP 메서드
            'Access-Control-Allow-Headers': 'Content-Type',  # 필요한 경우 확장 가능
        },
    }

def lambda_handler(event, context):
    print("Received event:", json.dumps(event, indent=4))  # 전체 이벤트 로그 출력

    # ✅ HTTP Method 추출
    operation = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    # ✅ OPTIONS 요청 처리 (CORS Preflight 요청)
    if operation == "OPTIONS":
        print("Handling OPTIONS request for CORS Preflight")  # 로그 추가
        return respond(None, is_options=True)

    if not operation:
        return respond(ValueError("Missing 'httpMethod' in event"))

    # ✅ CRUD 작업 정의
    operations = {
        'DELETE': lambda dynamo, x: dynamo.delete_item(**x),
        'GET': lambda dynamo, x: dynamo.get_item(**x),
        'POST': lambda dynamo, x: dynamo.put_item(**x),
        'PUT': lambda dynamo, x: dynamo.update_item(**x),
    }

    # ✅ HTTP 메서드 확인
    if operation in operations:
        try:
            body = json.loads(event.get('body', '{}'))

            if operation == 'GET':
                if "queryStringParameters" not in event or event["queryStringParameters"] is None:
                    return respond(ValueError("Missing 'Key' in queryStringParameters"))

                key = json.loads(event['queryStringParameters']['Key'])
                payload = {'TableName': table_name, 'Key': key}

            elif operation == 'DELETE':
                if "Key" not in body:
                    return respond(ValueError("Missing 'Key' in request body"))

                key = body['Key']
                payload = {'TableName': table_name, 'Key': key}

            elif operation == 'POST':
                if "Item" not in body:
                    return respond(ValueError("Missing 'Item' in request body"))

                item = body['Item']
                payload = {'TableName': table_name, 'Item': item}

            elif operation == 'PUT':
                if "Key" not in body or "UpdateExpression" not in body:
                    return respond(ValueError("Missing 'Key' or 'UpdateExpression' in request body"))

                key = body['Key']
                update_expression = body['UpdateExpression']
                expression_values = body.get('ExpressionAttributeValues', {})

                payload = {
                    'TableName': table_name,
                    'Key': key,
                    'UpdateExpression': update_expression,
                    'ExpressionAttributeValues': expression_values,
                    'ReturnValues': "UPDATED_NEW"
                }

            return respond(None, operations[operation](dynamo, payload))

        except Exception as e:
            return respond(f"Error processing request: {str(e)}")

    else:
        return respond(ValueError(f'Unsupported method "{operation}"'))
