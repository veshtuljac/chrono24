# HubSpot POC schema setup

One-time script that creates the 4 custom objects, their property groups,
their properties, and the custom association labels described in the
Label/Internal name/Group mapping sheet (2026-07-29) and the data model
diagram.

## Run

Easiest path, no terminal needed:
1. Create `scripts/hubspot-setup/token.txt` and paste just the token into it, save.
2. Hit Run on `setup.py` in VS Code.

`token.txt` is gitignored — it never gets committed.

Terminal alternative:
```
HUBSPOT_TOKEN=pat-eu1-xxxx python3 scripts/hubspot-setup/setup.py
```

Standard library only (`urllib`) — no `pip install` needed.

Safe to re-run — every step checks for an existing schema/group/property/
association label before creating it, so a partial failure can just be
re-run after fixing the cause.

Writes `setup-result.json` next to the script with the full created/skipped/
failed list — paste that back for review if anything's in `failed`.

## What it does NOT create

- Native/HubSpot-defined associations that already exist out of the box:
  Deal↔Payment (391), Order↔Payment (523/524), Order↔Deal (512),
  Order↔Line Item (513), Deal↔Line Item, Deal↔Contact, Company↔Contact,
  Note↔Deal.
- Pipelines/stages (already created separately — Outright Purchase
  3999163609, Outright Sale 3999208677; Order pipeline stages still pending).
- Default/native properties (email, dealname, closedate, dealstage,
  hs_payment_method_type, hs_pipeline_stage, hs_shipping_tracking_number,
  hs_order_note, etc.) — the sheet marks these "default", nothing to create.
- `Order.Courier_Link__c` and `Order.Dispatch_Courier__c` — sheet
  explicitly recommends not mapping these (static per-courier URL / never
  observed populated).

## Known gaps to close before this is production-mapping, not just POC schema

- Several dropdown option lists are marked `PARTIAL` in `setup.py` — built
  from sample data seen in this conversation, not a confirmed full
  `GROUP BY` against Supabase. Affected: `deals.department`,
  `deals.lead_source_detail`, `inventory_product.status`.
  Sending a value outside the configured options will fail at write time
  until the list is extended.
- `commerce_payments.xupes_payment_method_detail` was added even though it's
  not a row in the sheet — it's the field-mapping.md recommendation for
  carrying the raw 13-value payment method past HubSpot's fixed 9-value
  `hs_payment_method_type` enum. Drop it if that's not wanted.
- `customer_product.record_type` — confirmed via a live Supabase `GROUP BY`
  + a production Developer Console RecordType lookup: the real
  Agreement_Item__c Watches value is `0124J000000MWTTQA4` ("Watch"), now the
  only option in `setup.py`. The sheet's original `0121t0000000ljSAAQ` is a
  real production Id too, just for a different object — it's Product2's
  "Watch" RecordType, not Agreement_Item__c's (each object has its own
  separate "Watch" RecordType record/Id) — see `full-migration-plan.md`
  correction #4. The "4 unused (Xupes) RecordType variants + unused Restore
  Handbag RecordType" question is still open, but
  doesn't block this property since none of those are the Watches value.
