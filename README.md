# 주택 보유세 시뮬레이터 (2026년 귀속)

주택 공시가격, 보유기간, 주택 수, 나이를 입력하면 **재산세·종합부동산세 예상세액**을 계산하는 Streamlit 앱입니다. 요구사항은 상위 폴더의 `PRD.md`를 기준으로 합니다.

> 본 결과는 참고용 추정치이며 실제 고지세액과 다를 수 있습니다.

## 설치·실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

AI 상담 탭을 쓰려면 `.env.example`을 `.env`로 복사하고 `ANTHROPIC_API_KEY`를 입력합니다(또는 `.streamlit/secrets.toml`). 키가 없어도 간편 계산·시나리오 비교·다운로드는 동작합니다.

PDF 다운로드는 한글 폰트가 필요합니다. Windows는 맑은 고딕을 자동으로 쓰고, 그 외 환경은 `TAX_SIM_FONT` 환경변수로 `.ttf` 경로를 지정하세요.

## 테스트

```bash
pytest -q                                              # 전체
pytest tests/test_comprehensive_tax.py -q              # 파일 단위
pytest tests/test_property_tax.py::test_special_rate_9eok_boundary -q   # 단일 테스트
```

`tests/cases/verified_cases.json`의 `expected`가 `null`인 케이스는 skip됩니다. 위택스(재산세)·홈택스(종부세) 모의계산 결과를 입력하면 ±1% 오차로 검증합니다.

## 구조

| 경로 | 역할 |
|---|---|
| `rules/tax_rules_2026.json` | 세율·공제·공정시장가액비율 등 세법 수치 (코드에 하드코딩하지 않음) |
| `engine/` | 결정론적 계산 엔진: `household`(주택 수·1세대1주택 판정) → `property_tax`(주택별) → `comprehensive_tax`(인별) → `calculator`(합계·납부일정) |
| `engine/estimator.py` | 실거래가 → 공시가격 추정 (현실화율 가정, 결과에 '추정치' 표시) |
| `engine/scenarios.py`, `engine/joint.py` | What-if 시나리오 비교, 부부 공동명의 특례 비교 |
| `agent/` | Claude API Tool Use 루프(`client.py`), 도구(`tools.py`), 시스템 프롬프트, 금액 검증 가드(`guard.py`) |
| `ui/export.py` | CSV/PDF 다운로드 (화면 디자인은 3단계) |
| `data/sample_houses.csv` | 샘플 주택 10건 (가상) |

모든 중간 계산값은 `CalculationStep`(단계, 계산식, 금액, 근거 조문)으로 반환됩니다.

## 확인이 필요한 값

`tax_rules_2026.json`에서 `_note`에 ★가 붙은 항목은 매년 시행령으로 정해지거나 산식 해석이 필요한 값입니다. 사용 전에 법령 원문과 공공 모의계산기로 확인하세요.
- 1세대1주택 재산세 공정시장가액비율(43/44/45%)
- 과세표준상한률 (`base_cap_rate`, 현재 null → 미적용)
- 재산세 중복분 공제 산식
- 절사 단위
