# Database schema

## products
Stable product specifications: variety, colour, spiciness, SHU, ASTA.

## prices
Dynamic pricing records:
- product_id
- market_cost
- processing_cost
- packaging_cost
- other_cost
- margin_percent
- min_selling_price
- max_selling_price
- effective_from
- verified_on
- source
- price_type (domestic/export)

## price_history
Never overwrite historical prices. Add a new record whenever a price is updated.

## pricing_tiers
Quantity-tiered pricing per product:
- product_id
- min_qty
- max_qty (nullable for the highest tier)
- rate_per_kg

## leads
IndiaMART/customer enquiries:
- customer
- company
- phone
- email
- location
- delivery_address
- requirement
- product_id
- quantity_kg
- quoted_price
- status (New / Follow-up / Quoted / Converted / Lost)
- created_at
- last_contacted
- next_follow_up
- notes
- enquiry_raw_text — original text pulled from IndiaMART
- parsed_variety — variety extracted by AI parser
- parsed_quantity — quantity in kg extracted by AI parser
- parsed_location — location extracted by AI parser
- synced_at — when pulled from IndiaMART
- is_parsed — boolean flag (0/1)

## quotation_history
Every quotation that's actually sent to a customer:
- lead_id
- quotation_no
- customer
- product_id
- quantity_kg
- rate_per_kg
- total_value
- channel (email / whatsapp)
- sent_at
- status (sent / failed)
