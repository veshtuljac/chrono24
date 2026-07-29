#!/usr/bin/env python3
"""
Chrono24 SFDC -> HubSpot POC: one-time schema setup (objects, properties, associations).

Source of truth: the Label/Internal name/Group mapping sheet (shared 2026-07-29) +
the data model diagram (Deal/Payment/Order association typeIds).

Usage — easiest path (VS Code Run button, no terminal needed):
    1. Create a file called token.txt in this same folder
       (scripts/hubspot-setup/token.txt).
    2. Paste your HubSpot Private App token into it (just the token, nothing
       else) and save. That file is gitignored — it will never get committed.
    3. Hit Run on this file.

Usage — terminal alternative:
    HUBSPOT_TOKEN=pat-eu1-xxxx python3 setup.py

No pip install needed — standard library only.

Safe to re-run: every step checks for an existing schema/group/property/
association label first and skips it if found.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    token_file = Path(__file__).parent / "token.txt"
    if token_file.exists():
        TOKEN = token_file.read_text().strip()

if not TOKEN:
    print(
        "No token found. Either:\n"
        "  - create scripts/hubspot-setup/token.txt with just the token pasted in, or\n"
        "  - run: HUBSPOT_TOKEN=pat-... python3 setup.py"
    )
    sys.exit(1)

BASE = "https://api.hubapi.com"
summary = {"created": [], "skipped": [], "failed": [], "warnings": []}


def hs(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as res:
            text = res.read().decode("utf-8")
            return {"ok": True, "status": res.status, "body": json.loads(text) if text else {}}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"raw": text}
        return {"ok": False, "status": e.code, "body": parsed}


def slug(label):
    s = label.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def opt(label):
    return {"label": label, "value": slug(label)}


# ---------------------------------------------------------------------------
# 1. Custom object schemas
# ---------------------------------------------------------------------------

CUSTOM_OBJECTS = [
    {
        "name": "inventory_product",
        "labels": {"singular": "Inventory Product", "plural": "Inventory Products"},
        "primaryDisplayProperty": "inventory_product_name",
        "secondaryDisplayProperties": ["brand", "model", "xupes_reference"],
        "searchableProperties": ["xupes_reference", "product_code", "serial_number"],
    },
    {
        "name": "customer_product",
        "labels": {"singular": "Customer Product", "plural": "Customer Products"},
        "primaryDisplayProperty": "brand",
        "secondaryDisplayProperties": ["model", "serial_number"],
        "searchableProperties": ["serial_number", "customer_product_sf_id"],
    },
    {
        "name": "offer_history",
        "labels": {"singular": "Offer History", "plural": "Offer Histories"},
        "primaryDisplayProperty": "offer_type",
        "secondaryDisplayProperties": ["offered_price", "status"],
        "searchableProperties": ["offer_history_sf_dc"],
    },
    {
        "name": "attached_image",
        "labels": {"singular": "Attached Image", "plural": "Attached Images"},
        "primaryDisplayProperty": "image_name",
        "secondaryDisplayProperties": ["description"],
        "searchableProperties": ["attached_image_sf_dc"],
    },
]


def ensure_object_schema(defn):
    # NOTE: secondaryDisplayProperties/searchableProperties are deliberately left
    # out here — they reference properties that don't exist yet at this point
    # (created later in step 3). Setting them inline caused HubSpot to reject
    # (or half-create) the schema. ensure_schema_display_properties() sets them
    # afterwards, once every property actually exists.
    existing = hs("GET", f"/crm/v3/schemas/{defn['name']}")
    if existing["ok"]:
        summary["skipped"].append(f"schema:{defn['name']} (already exists)")
        return
    res = hs("POST", "/crm/v3/schemas", {
        "name": defn["name"],
        "labels": defn["labels"],
        "primaryDisplayProperty": defn["primaryDisplayProperty"],
        "requiredProperties": [],
        "properties": [
            {
                "name": defn["primaryDisplayProperty"],
                "label": defn["primaryDisplayProperty"],
                "type": "string",
                "fieldType": "text",
            }
        ],
    })
    if res["ok"]:
        summary["created"].append(f"schema:{defn['name']}")
    else:
        summary["failed"].append(f"schema:{defn['name']} -> {res['status']} {json.dumps(res['body'])}")


def ensure_schema_display_properties(defn):
    """Best-effort: set secondary display + searchable properties now that
    every property on the object actually exists. Purely cosmetic (HubSpot
    UI list view / search) — failure here is logged as a warning, not a
    blocking failure."""
    res = hs("PATCH", f"/crm/v3/schemas/{defn['name']}", {
        "secondaryDisplayProperties": defn["secondaryDisplayProperties"],
        "searchableProperties": defn["searchableProperties"],
    })
    if res["ok"]:
        summary["created"].append(f"schema-display-props:{defn['name']}")
    else:
        summary["warnings"].append(
            f"schema-display-props:{defn['name']} -> {res['status']} {json.dumps(res['body'])}"
        )


# ---------------------------------------------------------------------------
# 2. Property groups
# ---------------------------------------------------------------------------

GROUP_NAME = "sf_migration"
GROUP_LABEL = "SF Migration"

OBJECTS_WITH_GROUP = [
    "contacts", "deals", "line_items", "commerce_payments", "orders",
    "inventory_product", "customer_product", "offer_history", "attached_image",
]


def ensure_property_group(object_type):
    res = hs("POST", f"/crm/v3/properties/{object_type}/groups", {
        "name": GROUP_NAME,
        "label": GROUP_LABEL,
    })
    if res["ok"]:
        summary["created"].append(f"group:{object_type}.{GROUP_NAME}")
    elif res["status"] == 409:
        summary["skipped"].append(f"group:{object_type}.{GROUP_NAME} (already exists)")
    else:
        summary["failed"].append(f"group:{object_type}.{GROUP_NAME} -> {res['status']} {json.dumps(res['body'])}")


# ---------------------------------------------------------------------------
# 3. Properties per object
#    Internal names taken verbatim from the mapping sheet. Dropdown option
#    lists marked PARTIAL are built from sample GROUP BY data seen so far,
#    not a confirmed full picklist — extend via HubSpot UI once a full
#    GROUP BY is run against Supabase.
# ---------------------------------------------------------------------------

def TXT(name, label):
    return {"name": name, "label": label, "type": "string", "fieldType": "text"}


def NUM(name, label):
    return {"name": name, "label": label, "type": "number", "fieldType": "number"}


def BOOL(name, label):
    return {
        "name": name, "label": label, "type": "bool", "fieldType": "booleancheckbox",
        "options": [
            {"label": "True", "value": "true", "hidden": False, "displayOrder": 0},
            {"label": "False", "value": "false", "hidden": False, "displayOrder": 1},
        ],
    }


def DATE(name, label):
    return {"name": name, "label": label, "type": "date", "fieldType": "date"}


def SELECT(name, label, labels):
    return {"name": name, "label": label, "type": "enumeration", "fieldType": "select",
            "options": [opt(l) for l in labels]}


def MULTI(name, label, labels):
    return {"name": name, "label": label, "type": "enumeration", "fieldType": "checkbox",
            "options": [opt(l) for l in labels]}


CURRENCIES = ["GBP", "EUR", "USD"]  # PARTIAL — only GBP confirmed in samples

PROPERTIES = {
    "contacts": [
        BOOL("is_supplier", "Is Supplier"),
        SELECT("currency", "Currency", CURRENCIES),
        MULTI("type_of_purchaser", "Type of Purchaser",
              ["Trade", "Collector", "Investor", "First time buyer", "Platform", "Gifter", "Aspirational"]),
        SELECT("account_source", "Account Source", [
            "Invoice", "Xupes direct", "Member", "User Registration", "Chrono24", "Ebay", "1st Dibs",
            "Other", "De Bijenkorf", "Newsletter Register", "Enquiry", "Rebelle", "PaypalOutput",
            "Chronohunter", "William George", "Product Enquiry", "Contact", "Social Media",
            "Sell Your Item", "Vestiare", "SM", "Looking fro Something Else", "MarktPlaats",
        ]),
        BOOL("is_serving_customer", "Is Serving Customer"),
        TXT("person_sf_id", "Person SF ID"),
    ],

    "deals": [
        SELECT("department", "Department", ["Watches"]),  # PARTIAL — only value seen in Supabase to date
        BOOL("is_new_opportunity", "Is New Opportunity"),
        SELECT("deal_currency_code", "Currency", CURRENCIES),
        TXT("customer_email", "Customer Email"),
        DATE("last_customer_email_date", "Last Customer Email Date"),
        SELECT("lead_source", "Lead Source", [
            "Chrono24", "Xupes direct", "Ebay", "De Bijenkorf", "1st Dibs", "Auction", "Chronohunter",
            "Secret Sales", "Other", "William George", "Social Media", "Trade Fairs",
            "Business Development", "MarktPlaats", "Partner", "Mr JWW", "SM",
        ]),
        TXT("country_held", "Country Held"),
        TXT("feed_location", "Feed location"),
        SELECT("lead_source_detail", "Lead Source Detail", ["Chrono24 Offer", "Direct Sale"]),  # PARTIAL
        TXT("xupes_product_reference", "Xupes Product Reference"),
        TXT("chrono24_reply_to_email", "Chrono24 Reply To Email"),
        TXT("phone_rollup", "Phone Rollup"),
        TXT("delivery_address_line_1", "Delivery Address"),
        TXT("delivery_city", "Delivery city"),
        TXT("delivery_country", "Delivery country"),
        TXT("delivery_postcode", "Delivery Postcode"),
        TXT("tc_number", "TC Number"),
        TXT("po_number", "PO Number"),
        TXT("opportunity_sf_id", "Opportunity SF ID"),
    ],

    "line_items": [
        TXT("pricebook_entry_id", "Pricebook Entry ID"),
        TXT("tc_number", "TC Number"),
        TXT("opportunity_line_item_sf_id", "Opportunity Line Item SF ID"),
    ],

    "inventory_product": [
        # inventory_product_name created inline with the schema
        TXT("product_code", "Product Code"),
        TXT("xupes_reference", "Xupes reference"),
        TXT("brand", "Brand"),
        TXT("model", "Model"),
        TXT("serial_number", "Serial Number"),
        SELECT("status", "Status", ["Sold", "In Stock", "Sold By Partner"]),  # PARTIAL
        TXT("model_number", "Model Number"),
        TXT("vat_scheme", "Vat Scheme"),
        NUM("rrp", "RRP"),
        SELECT("product_type", "Product Type", [
            "Xupes Stock", "Consignment", "Partner Product", "Part Exchange In", "Chrono24 Stock",
            "Sourcing", "ATS Catalog", "Held In Trust", "To Order", "C2B", "ATS Product", "ATO Catalog",
        ]),
        NUM("total_cost", "Total Cost"),
        NUM("website_price", "Website Price"),
        SELECT("currency", "Currency", CURRENCIES),
        TXT("country_held", "Country Held"),
        TXT("feed_location", "Feed Location"),
        TXT("product_sf_id", "Product SF ID"),
    ],

    "customer_product": [
        # brand created inline with the schema (primary display)
        SELECT("record_type", "Record Type", ["0121t0000000ljSAAQ"]),  # PARTIAL — see README
        TXT("model", "Model"),
        TXT("model_number", "Model Number"),
        SELECT("condition", "Condition", [
            "Very Good", "Unused, sealed with tags and/or original packaging", "Good", "Excellent", "Fair", "Poor",
        ]),
        NUM("age", "Age"),
        BOOL("original_box", "Original Box"),
        BOOL("original_papers", "Original Papers"),
        TXT("case_material", "Case Material"),
        TXT("dial_colour", "Dial Colour"),
        TXT("serial_number", "Serial Number"),
        NUM("price", "Price"),
        NUM("commission_pct", "Commission Percentage"),
        SELECT("commission_type", "Commission Type", [
            "Chrono 24 Percentage Commission", "Fixed Return to client", "Xupes Percentage Commission",
            "Chrono 24 Fixed Commission", "Xupes Fixed Commission",
        ]),
        TXT("customer_product_sf_id", "Customer Product SF ID"),
    ],

    "offer_history": [
        # offer_type created inline with the schema (primary display)
        NUM("offered_price", "Offered Price"),
        DATE("offer_date", "Offer Date"),
        SELECT("currency", "Currency", CURRENCIES),
        BOOL("is_customer_offer", "Is Customer Offer"),
        SELECT("status", "Status", ["Pending", "Declined", "Accepted"]),
        TXT("response_url", "Response URL"),
        TXT("offer_history_sf_dc", "Offer History SF ID"),
    ],

    "commerce_payments": [
        # Not on the sheet, but flagged as needed in field-mapping.md since
        # hs_payment_method_type is a fixed 9-value enum that our 13 real
        # values don't map to 1:1 — remove if you decide not to keep the raw value.
        SELECT("xupes_payment_method_detail", "Xupes Payment Method Detail", [
            "Other Cards Online", "Bank Transfer", "Third Party Platform", "Paypal",
            "Other Cards Chip n Pin", "Amex Online", "Legacy", "Cash", "Amex Chip n Pin",
            "Credit on Account", "Cheque", "Splitit", "Finance Options",
        ]),
        TXT("payment_sf_dc", "Payment SF ID"),
    ],

    "orders": [
        TXT("product_tracking_url", "Product Tracking URL"),
        TXT("courier", "Courier"),
        TXT("order_sf_dc", "Order SF ID"),
        # dispatch_courier intentionally skipped — sheet: never observed populated.
        # courier_link intentionally skipped — static per-courier URL, adds nothing beyond `courier`.
    ],

    "attached_image": [
        # image_name created inline with the schema (primary display)
        TXT("original_image_url", "Original Image URL"),
        TXT("resized_image_url", "Resized Image URL"),
        TXT("description", "Description"),
        TXT("sf_content_version_id", "SF Content Version ID"),
        TXT("attached_image_sf_dc", "Attached Image SF ID"),
    ],
}


def ensure_property(object_type, defn):
    existing = hs("GET", f"/crm/v3/properties/{object_type}/{defn['name']}")
    if existing["ok"]:
        summary["skipped"].append(f"property:{object_type}.{defn['name']} (already exists)")
        return
    payload = {**defn, "groupName": GROUP_NAME}
    res = hs("POST", f"/crm/v3/properties/{object_type}", payload)
    if res["ok"]:
        summary["created"].append(f"property:{object_type}.{defn['name']}")
    else:
        summary["failed"].append(f"property:{object_type}.{defn['name']} -> {res['status']} {json.dumps(res['body'])}")


# ---------------------------------------------------------------------------
# 4. Custom associations
#    Native/HubSpot-defined associations (Deal<->Payment typeId 391,
#    Order<->Payment 523/524, Order<->Deal 512, Order<->Line Item 513,
#    Deal<->Line Item, Deal<->Contact, Company<->Contact, Note<->Deal) already
#    exist out of the box and are NOT created here.
# ---------------------------------------------------------------------------

ASSOCIATIONS = [
    {"from": "deals", "to": "customer_product", "name": "deal_to_customer_product", "label": "Customer Product"},
    {"from": "deals", "to": "offer_history", "name": "deal_to_offer_history", "label": "Offer History"},
    {"from": "deals", "to": "attached_image", "name": "deal_to_attached_image", "label": "Attached Image"},
    {"from": "customer_product", "to": "inventory_product", "name": "customer_product_to_inventory_product", "label": "Linked Inventory Product"},
    {"from": "line_items", "to": "inventory_product", "name": "line_item_to_inventory_product", "label": "Inventory Product"},
]


def ensure_association_label(defn):
    existing = hs("GET", f"/crm/v4/associations/{defn['from']}/{defn['to']}/labels")
    if existing["ok"] and isinstance(existing["body"].get("results"), list):
        found = next((r for r in existing["body"]["results"] if r.get("label") == defn["label"]), None)
        if found:
            summary["skipped"].append(f"association:{defn['from']}->{defn['to']}:{defn['label']} (already exists)")
            return
    res = hs("POST", f"/crm/v4/associations/{defn['from']}/{defn['to']}/labels", {
        "label": defn["label"],
        "name": defn["name"],
    })
    if res["ok"]:
        summary["created"].append(f"association:{defn['from']}->{defn['to']}:{defn['label']}")
    else:
        summary["failed"].append(
            f"association:{defn['from']}->{defn['to']}:{defn['label']} -> {res['status']} {json.dumps(res['body'])}"
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main():
    print("== 1. Custom object schemas ==")
    for defn in CUSTOM_OBJECTS:
        ensure_object_schema(defn)

    print("== 2. Property groups ==")
    for obj in OBJECTS_WITH_GROUP:
        ensure_property_group(obj)

    print("== 3. Properties ==")
    for object_type, props in PROPERTIES.items():
        for defn in props:
            ensure_property(object_type, defn)

    print("== 4. Custom associations ==")
    for defn in ASSOCIATIONS:
        ensure_association_label(defn)

    print("== 5. Schema display/search properties (cosmetic, best-effort) ==")
    for defn in CUSTOM_OBJECTS:
        ensure_schema_display_properties(defn)

    print("\n=== SUMMARY ===")
    print(f"Created: {len(summary['created'])}")
    for x in summary["created"]:
        print("  +", x)
    print(f"Skipped (already existed): {len(summary['skipped'])}")
    print(f"Warnings (non-blocking): {len(summary['warnings'])}")
    for x in summary["warnings"]:
        print("  ~", x)
    print(f"Failed: {len(summary['failed'])}")
    for x in summary["failed"]:
        print("  !", x)

    result_path = Path(__file__).parent / "setup-result.json"
    result_path.write_text(json.dumps(summary, indent=2))
    print(f"\nFull result written to {result_path}")

    if summary["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
