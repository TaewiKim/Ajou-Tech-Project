from openai import OpenAI
import ast




system_prompt = "여기에 당신의 프롬프트를 작성해 주세요"





questions = """
{
    "다음 중 체내에서 완전히 산화될 때 가장 많은 에너지를 방출하는 것은?": {
        "options": {
            "A": "1그램의 포도당",
            "B": "1그램의 팔미트산",
            "C": "1그램의 류신",
            "D": "1그램의 알코올"
        }
    },
    "미토콘드리아의 내막에 박혀 있는 것은?": {
        "options": {
            "A": "시트르산 회로(크렙스 회로)의 효소들",
            "B": "전자 전달계의 구성 요소들",
            "C": "글리코겐 분자들",
            "D": "트라이아실글리세롤 분자들"
        }
    },
    "운동 중 남자 선수의 평균 산소 소비율이 2 l/min이라면 그의 에너지 소비율은 약 얼마인가?": {
        "options": {
            "A": "400 kJ/min",
            "B": "200 kJ/min",
            "C": "80 kJ/min",
            "D": "40 kJ/min"
        }
    },
    "성인의 안정 시 정상 심박수는?": {
        "options": {
            "A": "60-80 bpm",
            "B": "60-100 bpm",
            "C": "60-90 bpm",
            "D": "60-110 bpm"
        }
    },
    "다음 중 거짓인 것은?": {
        "options": {
            "A": "포스포프럭토키나아제는 해당과정의 속도 제한 효소이다.",
            "B": "포스포릴레이스 활성은 제 II형 근섬유에서 제 I형보다 높다.",
            "C": "지구력 훈련은 근육 내 TCA 회로 효소의 양을 증가시킨다.",
            "D": "TCA 회로에서 산소가 소비된다."
        }
    },
    "다음 중 척골 신경 마비(ulna nerve palsy)에 대한 설명으로 옳은 것은?": {
        "options": {
            "A": "척골 신경은 상완골 나선구 골절에 의해 손상될 수 있다.",
            "B": "파렌 검사(Phalen's sign)가 양성으로 나타난다.",
            "C": "손바닥과 손등에서 손의 내측 절반과 내측 1.5지의 감각 소실을 초래한다.",
            "D": "이 근육은 이두근을 지배한다."
        }
    },
    "치아를 닦기 위해 권장되는 치약 양은?": {
        "options": {
            "A": "소량(얇게 바른 정도)",
            "B": "완두콩 크기 정도",
            "C": "칫솔 길이만큼",
            "D": "반 인치 정도"
        }
    },
    "다음 중 쿠싱증후군(Cushing's Syndrome)에 대한 설명으로 옳은 것은?": {
        "options": {
            "A": "코르티솔 호르몬 결핍으로 발생한다.",
            "B": "사지가 비대해지는 것이 흔하다.",
            "C": "골다공증은 특징이 아니다.",
            "D": "달덩이 얼굴(moon face)과 물소 혹(buffalo hump)이 특징이다."
        }
    },
    "스포츠에서 성공을 결정짓는 주요 요인은?": {
        "options": {
            "A": "고열량 식단과 큰 식욕",
            "B": "높은 지능과 성공하려는 동기",
            "C": "좋은 코치와 성공하려는 동기",
            "D": "타고난 능력과 훈련 자극에 반응하는 능력"
        }
    },
    "이중 가닥 DNA 분자에서 퓨린:피리미딘의 비율은?": {
        "options": {
            "A": "가변적이다.",
            "B": "RNA의 염기서열에 의해 결정된다.",
            "C": "유전적으로 결정된다.",
            "D": "항상 1:1이다."
        }
    }
}
"""
answers = ["B", "B", "D", "B", "D", "C", "B", "D", "D", "D"]

apikey = "여기에 당신의 OpenAI API 키를 입력하세요"

client = OpenAI(api_key=apikey)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": '답변 형식은 List로 ["A", "B", "C", "D"] 형식으로 작성해 주세요' + system_prompt},
        {"role": "user", "content": questions}
    ]
)

# 응답 출력
gpt_answers = response.choices[0].message.content
print(gpt_answers)

# 안전하게 리스트로 변환
gpt_answers_list = ast.literal_eval(gpt_answers)

# 정답률 계산
correct_count = sum(1 for i in range(len(answers)) if gpt_answers_list[i] == answers[i])
total_questions = len(answers)
accuracy = correct_count / total_questions * 100

print("정답률:", accuracy, "%")