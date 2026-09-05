from services.pricing import PriceInput, calculate_selling_price, parse_price_range

def test_price():
    assert calculate_selling_price(PriceInput(180, 15, 5, 5, 10)) == 225.5

def test_range():
    assert parse_price_range("150-160") == (150.0, 160.0)
