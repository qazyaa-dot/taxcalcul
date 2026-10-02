import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.models import House, TaxpayerInput  # noqa: E402


@pytest.fixture
def make_input():
    """간단한 TaxpayerInput 생성기: prices는 공시가격 리스트."""

    def _make(prices, birth=date(1976, 1, 1), acquired=date(2023, 1, 1), **kw):
        house_kw = {k: kw.pop(k) for k in ("ownership_ratio", "is_urban_area") if k in kw}
        houses = [House(name=f"H{i + 1}", official_price=p, acquired_date=acquired, **house_kw)
                  for i, p in enumerate(prices)]
        return TaxpayerInput(birth_date=birth, houses=houses, **kw)

    return _make
