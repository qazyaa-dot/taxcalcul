"""입력·출력 데이터 모델 (PRD 8.1·8.2)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ASSESSMENT_DATE = date(2026, 6, 1)


class House(BaseModel):
    """주택 한 채."""

    name: str
    official_price: int | None = Field(default=None, gt=0, description="공시가격(원)")
    market_price: int | None = Field(default=None, gt=0, description="실거래가(원), 선택")
    region: str = "서울"
    is_urban_area: bool = True
    acquired_date: date
    ownership_ratio: float = Field(default=1.0, gt=0, le=1)
    house_type: Literal["apartment", "detached", "multi"] = "apartment"
    exclude_from_count: bool = False
    price_estimated: bool = False  # 실거래가로 공시가격을 추정했는지 (estimator가 설정)

    @field_validator("acquired_date")
    @classmethod
    def _acquired_before_assessment(cls, v: date) -> date:
        if v > ASSESSMENT_DATE:
            raise ValueError("취득일은 과세기준일(2026-06-01) 이전이어야 합니다")
        return v

    @model_validator(mode="after")
    def _need_price(self) -> House:
        if self.official_price is None and self.market_price is None:
            raise ValueError("공시가격 또는 실거래가 중 하나는 입력해야 합니다")
        return self


class TaxpayerInput(BaseModel):
    """납세자와 보유 주택 정보."""

    tax_year: int = 2026
    birth_date: date
    houses: list[House] = Field(min_length=1)
    is_one_house_household: bool | None = None
    prev_property_tax: int | None = Field(default=None, ge=0)
    prev_comprehensive_tax: int | None = Field(default=None, ge=0)
    prev_property_tax_base: dict[str, int] | None = None


class CalculationStep(BaseModel):
    """계산 단계 하나 (화면 '계산 근거' 표와 AI 해설의 근거)."""

    tax: Literal["재산세", "종부세", "부가세", "공통"]
    label: str
    formula: str
    value: int
    basis: str = ""
    unit: Literal["원", "채", "세", "여부"] = "원"  # 금액이 아닌 단계(주택 수·나이·판정) 구분용

    def display_value(self) -> str:
        """화면·CSV·PDF용 값 표기 ('1,234원', '2채', '66세', '예')."""
        if self.unit == "여부":
            return "예" if self.value else "아니오"
        return f"{self.value:,}{self.unit}"


class HousePropertyTax(BaseModel):
    """주택별 재산세 결과 (지분 반영 후)."""

    name: str
    official_price: int
    ownership_ratio: float
    fair_market_ratio: float
    tax_base: int
    special_rate_applied: bool
    price_estimated: bool = False
    property_tax: int
    urban_area_tax: int
    local_education_tax: int
    total: int
    july: int
    september: int


class PropertyTaxResult(BaseModel):
    houses: list[HousePropertyTax]
    property_tax_total: int
    urban_area_tax: int
    local_education_tax: int
    total: int
    steps: list[CalculationStep]
    warnings: list[str] = []


class ComprehensiveTaxResult(BaseModel):
    taxable: bool
    is_one_house_owner: bool
    house_count: int
    price_sum: int
    deduction: int
    tax_base: int
    calculated_tax: int
    property_tax_overlap: int
    senior_credit_rate: float
    long_term_credit_rate: float
    credit_amount: int
    burden_cap_reduction: int
    comprehensive_tax: int
    rural_special_tax: int
    total: int
    installment_available: int
    steps: list[CalculationStep]
    warnings: list[str] = []


class TaxResult(BaseModel):
    property_tax_by_house: list[HousePropertyTax]
    property_tax_total: int
    urban_area_tax: int
    local_education_tax: int
    comprehensive_tax: int
    rural_special_tax: int
    total: int
    effective_rate: float
    payment_schedule: list[dict]
    steps: list[CalculationStep]
    warnings: list[str]
