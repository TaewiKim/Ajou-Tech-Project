import os
import requests
import re, html

# 네이버 api에서 html 태그 제거하는 함수
TAG_RE = re.compile(r"<[^>]+>")
def clean_text(s):
    return TAG_RE.sub("", html.unescape(s)).strip() if isinstance(s, str) else ""

# 네이버 개발자센터에서 발급받은 Client ID / Client Secret 넣기
CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

def naver_shop_search(query, display=5):
    """
    네이버 쇼핑 API 검색
    query: 검색어
    display: 가져올 개수 (최대 100)
    """
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": display,
    }
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        results = []
        for item in data.get("items", []):
            results.append({
                "title": clean_text(item["title"]),   # 상품명 (HTML 태그 제거됨)
                "link": item["link"],     # 구매 링크
                "image": item["image"],   # 썸네일
                "lprice": item["lprice"], # 최저가
                "hprice": item["hprice"], # 최고가 (없으면 0)
                "mallName": item["mallName"], # 판매처
            })
        return results
    else:
        print("Error:", response.status_code, response.text)
        return None


if __name__ == "__main__":
    query = "아이폰 15 케이스"
    results = naver_shop_search(query, display=3)
    for r in results:
        print(f"상품명: {r['title']}")
        print(f"가격: {r['lprice']}원")
        print(f"링크: {r['link']}")
        print(f"이미지: {r['image']}")
        print(f"판매처: {r['mallName']}")
        print("-" * 50)
