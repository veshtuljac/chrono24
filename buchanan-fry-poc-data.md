# Buchanan / Fry — POC data entry reference

Real values pulled from the sample sheet (shared 2026-07-29), filtered down to only the
fields/properties actually created for the POC (per `field-mapping.md` and
`scripts/hubspot-setup/setup.py`). Use this to manually recreate both examples in HubSpot
(task #7).

**Known data-quality flags in the source sheet — read before trusting a blank:**
1. The Product2 (Inventory Product) and Opportunity Line Item tables in the sample sheet have
   a column misalignment starting right after the `Name` field (a cell appears to have gone
   missing during copy/paste into the Google Doc). Values below for those two objects come
   from the already-validated `field-mapping.md` examples, not a fresh re-parse of the
   misaligned columns — flagged inline where relevant.
2. Fry's **Account** row in the sample sheet has most fields blank (`PersonEmail`,
   `FirstName`, `LastName`, etc.) even though we know from `Customer_Email__c` elsewhere that
   Fry has a real email (`ianfry85@gmail.com`). Looks like an incomplete paste for that
   specific row — worth re-copying that row from the source before trusting it fully. Only
   the fields that *are* populated (billing address) are listed below with confidence.

---

## Company / Contact (Account, Person Account model)

| HubSpot property | Buchanan | Fry |
|---|---|---|
| `email` (default) | jbuchanan181282@gmail.com | ianfry85@gmail.com *(from Customer_Email\_\_c — Account row itself is blank, re-verify)* |
| `firstname` (default) | John | **blank in source — re-verify** |
| `lastname` (default) | Buchanan | **blank in source — re-verify** |
| `hs_email_optout` (default) | TRUE | **blank in source — re-verify** |
| `is_supplier` | TRUE | **blank in source — re-verify** |
| `currency` | GBP | **blank in source — re-verify** |
| `salutation` (default) | *(null)* | **blank in source — re-verify** |
| `type_of_purchaser` | *(null)* | **blank in source — re-verify** |
| `account_source` | *(null)* | *(null)* |
| `is_serving_customer` | FALSE | **blank in source — re-verify** |
| `phone` (default) | 447715562598 *(sheet shows `4.48E+11` — Excel/Sheets mangled it as a number; use the known real value)* | 447557674888 *(from Phone\_Rollup\_\_c on the Opportunity)* |
| `address` (default) | 37 Swanston Drive | 4 Sutton Close |
| `city` (default) | Edinburgh | Weymouth |
| `zip` (default) | EH10 7BP | DT3 6LJ |
| `country` (default) | United Kingdom | United Kingdom |
| `person_sf_id` | 0014J00000vbwwqQAA | 001Q500000nvzAkIAI |

---

## Deal (Opportunity)

| HubSpot property | Buchanan | Fry |
|---|---|---|
| `dealname` (default) | John Buchanan - W010025 - 2023-04-06 | Ian Fry - Rolex Daytona - 2025-09-22 |
| `closedate` (default) | 2025-09-04 *(re-set date, not the original CloseDate)* | 2025-09-25 |
| `dealstage` (default) | Closed Won | Closed Won |
| pipeline (via RecordTypeId, not a property) | `0121t0000000n8cAAA` → **Outright Purchase** pipeline | `0121t0000000aLzAAI` → **Outright Sale** pipeline |
| `department` | Watches | Watches |
| `is_new_opportunity` | TRUE | TRUE |
| `deal_currency_code` | GBP | GBP |
| `customer_email` | jbuchanan181282@gmail.com | ianfry85@gmail.com |
| `last_customer_email_date` | 2023-04-06 | 2025-09-22 |
| `lead_source` | Chrono24 | Chrono24 |
| `country_held` | United Kingdom | United Kingdom |
| `feed_location` | UK | UK |
| `lead_source_detail` | Chrono24 Offer | Direct Sale |
| `xupes_product_reference` | W010025 | W011758 |
| `chrono24_reply_to_email` | 06b6a12d-e28f-4223-ace0-f04bdd2ab97a-gfwh5@reply.chrono24.com | *(null — expected, Sale not Purchase)* |
| `phone_rollup` | 447715562598 | 447557674888 |
| `delivery_address_line_1` | 20 Alloa Road | *(null)* |
| `delivery_city` | Fishcross | *(null)* |
| `delivery_country` | United Kingdom | *(null)* |
| `delivery_postcode` | FK10 3HY | *(null)* |
| `tc_number` | *(null)* | *(null)* |
| `po_number` | PO-SF-00006903 | PO-SF-00036756 |
| `opportunity_sf_id` | 0064J00000MuqT4QAJ | 006Q500000NcFNNIA3 |
| (association → Company) | AccountId = 0014J00000vbwwqQAA | AccountId = 001Q500000nvzAkIAI |

---

## Line Item (Opportunity Line Item) — Buchanan only in this sheet

Table had the column-shift issue — values below are the already-validated ones from
`field-mapping.md`, not re-parsed from this specific export.

| HubSpot property | Buchanan |
|---|---|
| `price` (default, UnitPrice) | 12000 |
| `pricebook_entry_id` | 01u4J000004g3AUQAY |
| `tc_number` | TC-6568904 |
| `opportunity_line_item_sf_id` | *(not captured in this sheet — Id field wasn't in the visible columns)* |
| (association → Deal) | OpportunityId = 0064J00000MuqT4QAJ |
| (association → Inventory Product) | Product2Id = 01t4J0000057dNDQAY |

---

## Inventory Product (Product2) — both

Table had the column-shift issue past `Name` — values below are the already-validated ones
from `field-mapping.md`, cross-checked against the reliable (pre-shift) columns in this sheet
(`Name`, `Brand__c`, `Model__c`, `Model_Number__c`, `CurrencyIsoCode`, `Country_Held__c` all
confirmed directly).

| HubSpot property | Buchanan | Fry |
|---|---|---|
| `inventory_product_name` | Rolex Sea-Dweller W010025 *(confirmed)* | Rolex Daytona W011758 *(confirmed)* |
| `brand` | Rolex *(confirmed)* | Rolex *(confirmed)* |
| `model` | Sea-Dweller *(confirmed)* | Daytona *(confirmed)* |
| `model_number` | 126600 *(confirmed)* | 116520 *(confirmed)* |
| `currency` | GBP *(confirmed)* | GBP *(confirmed)* |
| `country_held` | *(null, confirmed)* | *(null, confirmed)* |
| `product_code` | W010025 | W011758 |
| `xupes_reference` | W010025 | W011758 |
| `serial_number` | 76LZ3675 *(cross-checked against Order Item's serial_number\_c, which matched cleanly)* | K999140 *(cross-checked against Customer Product's Serial_Number\_\_c, which matched cleanly)* |
| `status` | Sold | Sold |
| `vat_scheme` | Marginal | Marginal |
| `rrp` | 12450 | 16450 |
| `product_type` | Part Exchange In | Xupes Stock |
| `total_cost` | 10500 | 12500 |
| `website_price` | *(—, not populated)* | *(—, not populated)* |
| `feed_location` | *(null)* | *(null)* |
| `product_sf_id` | 01t4J0000057dNDQAY | 01tQ500000AvAhdIAF |

---

## Customer Product (Agreement_Item__c) — Fry only in this sheet

| HubSpot property | Fry |
|---|---|
| `record_type` | `0124J000000MWTTQA4` (Watch) |
| `brand` | Rolex |
| `model` | Daytona |
| `model_number` | 116520 |
| `condition` | Very Good |
| `age` | 2003 |
| `original_box` | FALSE |
| `original_papers` | TRUE |
| `case_material` | Stainless Steel |
| `dial_colour` | White |
| `serial_number` | K999140 |
| `price` | 12500 |
| `commission_pct` | *(null)* |
| `commission_type` | *(null)* |
| `customer_product_sf_id` | a1uQ500000ARo2zIAD |
| (association → Deal) | Opportunity\_\_c = 006Q500000NcFNNIA3 |
| (soft link → Inventory Product, update-only) | Product\_\_c = 01tQ500000AvAhdIAF *(already populated here — post-intake)* |

Buchanan has no Customer Product row in this sheet — consistent with the model (Customer
Product is central to Outright Sale, not Outright Purchase).

---

## Offer History — Buchanan only in this sheet (3 rows, append-only)

| HubSpot property | Offer 1 | Offer 2 | Offer 3 |
|---|---|---|---|
| `offer_type` | Price Suggestion | Offer Rejected | Offer Accepted |
| `offered_price` | 11250 | 12250 | 11250 |
| `offer_date` | 2023-04-05 | 2023-04-06 | 2023-04-06 |
| `currency` | GBP | GBP | GBP |
| `is_customer_offer` | TRUE | FALSE | FALSE |
| `status` | Pending | Declined | Accepted |
| `response_url` | chrono24.co.uk/.../checkoutId=6568904 | (same) | (same) |
| `offer_history_sf_dc` | a1t4J000006kHK3QAM | a1t4J000006kHc7QAE | a1t4J000006kHcRQAU |
| (association → Deal) | Opportunity\_\_c = 0064J00000MuqT4QAJ for all three |

---

## Payment (native Commerce Payments) — Buchanan only in this sheet

| HubSpot property | Buchanan |
|---|---|
| `hs_currency_code` | GBP |
| `hs_initial_amount` | 12000 |
| `hs_initiated_date` | 2023-04-06 |
| `hs_payment_method_type` | Bank Transfer → map to native `wire_transfer` (closest fit) or `other` |
| `xupes_payment_method_detail` | Bank Transfer |
| `payment_sf_dc` | a0K4J000009m4P4UAI |
| (native association → Deal) | Opportunity_Payment\_\_c = 0064J00000MuqT4QAJ |
| (native association → Order) | Order_Payment\_\_c = 8014J000007TvISQA0 |

---

## Order (native Commerce Orders) — Buchanan only in this sheet

| HubSpot property | Buchanan |
|---|---|
| `hs_pipeline_stage` (via Status) | Dispatched |
| `hs_shipping_tracking_number` (via Tracking_URL\_\_c) | *(null — despite being populated on ~2% of real orders, blank on this one)* |
| `product_tracking_url` | DS543662328GB *(note: this is actually a real tracking-number-shaped value sitting in `Product_Tracking_URL__c`, not `Tracking_URL__c` — inconsistent with the general pattern documented in field-mapping.md, worth a note)* |
| `courier` | *(null)* |
| `order_sf_dc` | 8014J000007TvISQA0 |
| (native association → Deal) | OpportunityId = 0064J00000MuqT4QAJ |

**Not mapped to a property (no SMS-documented source, confirmed populated here — see
full-migration-plan.md open question on Invoice fields):** `Invoice_Number__c` = INV-1601912,
`Invoice_Date__c` = 2025-09-04, `Has_Invoice__c` = TRUE, `DueDate__c` = 2023-04-20.

---

## Attached Image (Lead_Attached_Image__c) — Fry only, 9 rows

All 9 rows share the same parent (`Opportunity__c` = 006Q500000NcFNNIA3) and the same shape:

| HubSpot property | Pattern |
|---|---|
| `image_name` | `{ContentVersionId}_{OpportunityId}_{Main\|1\|2\|3\|4\|5\|6\|7\|8}` |
| `original_image_url` | `xupes-customer-product-images.s3.eu-west-2.amazonaws.com/{ContentVersionId}_{OpportunityId}_{suffix}` |
| `resized_image_url` | CloudFront-wrapped version of the same key |
| `description` | Same value as `image_name` |
| `sf_content_version_id` | The `ContentVersionId__c` for that row |
| `attached_image_sf_dc` | The record's own `Id` (e.g. a27Q500000Cq60oIAB) |

Full list of the 9 `ContentVersionId__c` / record `Id` pairs is in the source sheet if you
need to recreate all 9 individually — the pattern above should be enough to build them
quickly by hand.
