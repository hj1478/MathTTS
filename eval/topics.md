# Korean math topics to test (초등 → 중등)

Testing roadmap for the OCR→normalize→SRE-ko pipeline. Each topic notes the
notation it stresses. Status: [x] worksheet passed through inbox_eval,
[~] notation partially covered by golden cases, [!] known struggle, [ ] untested.

## 초1–2 (mostly prose, low risk)
- [x] 수와 덧셈·뺄셈 (받아올림) — untested-topics-worksheet clean
- [x] 곱셈구구 — 3×4 (untested-topics-worksheet)
- [~] 시각과 시간 — 시:분 colon (schedule-line case covers 14:00)
- [x] 길이 재기 — cm/m 단위 변환 with □ blanks (untested-topics-worksheet)

## 초3–4
- [x] 나눗셈 — 몫과 나머지 13÷4=3⋯1 -> "몫 3 나머지 1" (division-remainder-dots)
- [x] 분수 기초: 대분수/가분수 — "2 와 3 분의 1" all 3 OCR forms (mixed-number-* cases)
- [x] 소수 — 자릿값 문제 clean (untested-topics-worksheet)
- [x] 각도 — ∠, ° (angle-degree, degree-circ cases)
- [~] 막대/꺾은선그래프 — prose questions clean (problems-2); graph figures still absent
- [x] 큰 수와 어림 — 반올림, 억/만 단위 clean (untested-topics-worksheet)

## 초5–6
- [x] 약수와 배수, 최대공약수·최소공배수 (소인수분해 sheets)
- [~] 분수의 사칙연산 — fractions ✓; 대분수 연산 untested
- [x] 소수의 곱셈·나눗셈 — 6.3÷0.9, 1.5L×4 clean (problems-2)
- [~] 혼합 계산 — nested {[( )]} (bare-braces case)
- [x] 비와 비율, 백분율 — 3:4, % (ratio, percent-prose cases)
- [x] 비례식과 비례배분 — 2:3 비례배분 clean (untested-topics-worksheet)
- [~] 원주율과 원의 넓이 — π (boxed-blank case)
- [~] 겉넓이·부피 — cm³ ✓ (unit-power); m², km² untested
- [~] 각기둥·원기둥 전개도 — prose problem clean; the figure itself is still absent (vision layer)
- [~] 띠/원그래프, 평균 — 평균/기록표 clean; graph figures still absent

## 중1
- [x] 소인수분해 (01 단원평가 — clean)
- [x] 정수와 유리수 (02 단원평가 — clean; 절댓값, 수직선)
- [x] 문자와 식, 일차방정식 (KMA sheets)
- [x] 좌표평면, 정비례·반비례 — 순서쌍 '점 괄호 열고 3 콤마 12 괄호 닫고' clean (problems-2)
- [~] 기본 도형과 작도 — ⊥ ∥ ∠ ✓; 선분/반직선 표기, \overrightarrow reading untested
- [x] 평면도형 — 부채꼴 호 l=2πr×(45/360) reads correctly (untested-topics-worksheet)
- [~] 입체도형 — 오일러 v-e+f, 원뿔 모선 prose clean (problems-2); figures absent
- [x] 자료의 정리 — 도수분포표/상대도수 tables clean (problems-2)

## 중2
- [!] 유리수와 순환소수 — 순환마디 dot/overline phrasing (top fix candidate)
- [x] 식의 계산, 지수법칙 (KMA sheets)
- [x] 일차부등식, 연립방정식 (golden cases)
- [!] 일차함수 — f(3) reads "f 의 3" (ambiguous)
- [x] 삼각형의 성질 — 외심 ∠BOC, 이등변 clean (problems-2)
- [x] 사각형의 성질 — □PQRS/□EFGH vs blank □ disambiguated in the wild (problems-2)
- [!] 도형의 닮음 — ∽ reads 물결표
- [~] 피타고라스 정리 — a²+b²=c², √ ✓
- [~] 경우의 수와 확률 — fractions ✓; tree diagrams are figures

## 중3
- [x] 제곱근과 실수 — √(a²)=□ (a<0) condition reads with 콤마 (problems-2; nested 근호 remains known)
- [~] 근호 계산 — √(200-x) ✓ (kma3); 분모의 유리화 1/√2 untested
- [x] 곱셈공식과 인수분해 — clean (problems-2)
- [x] 이차방정식 — 근의 공식 clean (stress test + problems-2)
- [x] 이차함수 — clean (problems-2)
- [x] 삼각비 — 싸인/코싸인/탄젠트 30 도 (stress test; trig-bare cases)
- [x] 원의 성질 — 원주각 clean (problems-2)
- [x] 통계 — 분산/표준편차, 상대도수 clean (problems-2; √{분산} via sqrt-hangul-arg)

## Priority queue — 2026-07-28: original 7 items all tested & resolved ✓
All topics 초1–중3 are now [x]/[~]. What remains (see eval/problems.md):
1. Figure-dependent content (graphs, 도형 diagrams, 전개도, tree diagrams) —
   needs a vision-description layer, not the text pipeline
2. The 8 [!] known struggles — SRE-ko phrasing (순환소수, ∽, f(x)) via a
   post-SRE rewrite pass; linearization ambiguities (번분수, x_{n+1}, nested
   근호) need a phrasing-policy decision validated by listening tests
3. Minor [~] gaps: 대분수 연산, 분모의 유리화 1/√2, m²/km² units,
   선분/반직선 \overrightarrow reading
