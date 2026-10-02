"""주택 수 산정, 1세대1주택 판정, 만 나이·보유연수 계산."""
from __future__ import annotations

from datetime import date

from .models import ASSESSMENT_DATE, House, TaxpayerInput


def full_years(start: date, on: date = ASSESSMENT_DATE) -> int:
    """start부터 on까지 만 햇수 (생일·취득일 당일이 지나야 1년)."""
    years = on.year - start.year
    if (on.month, on.day) < (start.month, start.day):
        years -= 1
    return max(years, 0)


def age_on_assessment(birth_date: date) -> int:
    """과세기준일 기준 만 나이."""
    return full_years(birth_date)


def holding_years(acquired_date: date) -> int:
    """과세기준일 기준 보유연수."""
    return full_years(acquired_date)


def exclusion_ignored(houses: list[House]) -> bool:
    """모든 주택에 '주택 수 제외 특례'가 체크된 경우. 제외 특례는 다른 주택이 있을 때만 의미가 있다."""
    return bool(houses) and all(h.exclude_from_count for h in houses)


def counted_houses(houses: list[House]) -> list[House]:
    """주택 수 산정 대상 (상속·지방저가 등 특례 체크 주택 제외). 지분 보유도 1채로 센다.

    모든 주택이 제외 대상이면 제외하지 않는다 (예: 상속주택 1채만 보유 → 1주택).
    """
    if exclusion_ignored(houses):
        return list(houses)
    return [h for h in houses if not h.exclude_from_count]


def house_count(houses: list[House]) -> int:
    return len(counted_houses(houses))


def one_house_override_conflict(inp: TaxpayerInput) -> bool:
    """사용자가 '1세대1주택 예'를 골랐지만 산정 대상 주택이 1채가 아닌 모순 입력."""
    return inp.is_one_house_household is True and house_count(inp.houses) != 1


def is_one_house_household(inp: TaxpayerInput) -> bool:
    """재산세용 1세대1주택 여부. 사용자가 지정하면 그 값을, 아니면 주택 수 1채로 판정.

    '예' 지정은 산정 대상 주택이 1채일 때만 인정한다 (모순이면 무시하고 경고는 calculator가 남김).
    MVP에서는 입력된 주택을 세대 전체 보유 주택으로 간주한다.
    """
    if one_house_override_conflict(inp):
        return False
    if inp.is_one_house_household is not None:
        return inp.is_one_house_household
    return house_count(inp.houses) == 1


def is_one_house_target(inp: TaxpayerInput, house: House) -> bool:
    """이 주택이 재산세 1세대1주택 특례(비율·세율) 대상인지."""
    return is_one_house_household(inp) and any(house is h for h in counted_houses(inp.houses))


def is_one_house_owner_for_comprehensive(inp: TaxpayerInput) -> bool:
    """종부세용 1세대1주택자 여부: 1세대1주택이면서 그 주택을 단독 소유."""
    if not is_one_house_household(inp):
        return False
    counted = counted_houses(inp.houses)
    if len(counted) != 1:
        return False
    return counted[0].ownership_ratio >= 1.0
