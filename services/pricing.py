from dataclasses import dataclass

@dataclass
class PriceInput:
    market_cost: float
    processing_cost: float = 0.0
    packaging_cost: float = 0.0
    other_cost: float = 0.0
    margin_percent: float = 0.0

def calculate_selling_price(p: PriceInput) -> float:
    cost = p.market_cost + p.processing_cost + p.packaging_cost + p.other_cost
    return round(cost * (1 + p.margin_percent / 100), 2)

def parse_price_range(price_range: str):
    """Parse values such as '150-160' or '470 - 490' into (min, max)."""
    import re
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", price_range)]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    return nums[0], nums[1]
