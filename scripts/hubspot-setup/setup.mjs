#!/usr/bin/env node
// Chrono24 SFDC -> HubSpot POC: one-time schema setup (objects, properties, associations).
// Source of truth: the Label/Internal name/Group mapping sheet (shared 2026-07-29) +
// the data model diagram (Deal/Payment/Order association typeIds).
//
// Usage:
//   HUBSPOT_TOKEN=pat-eu1-xxxx node scripts/hubspot-setup/setup.mjs
//
// Requires Node 18+ (uses global fetch). Safe to re-run — every step checks for an
// existing schema/group/property/association label first and skips it if found.

const TOKEN = process.env.HUBSPOT_TOKEN;
if (!TOKEN) {
  console.error("Missing HUBSPOT_TOKEN env var. Run: HUBSPOT_TOKEN=pat-... node setup.mjs");
  process.exit(1);
}

const BASE = "https://api.hubapi.com";
const summary = { created: [], skipped: [], failed: [] };

async function hs(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  return { ok: res.ok, status: res.status, body: json };
}

function slug(label) {
  return label
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function opt(label) {
  return { label, value: slug(label) };
}

// ---------------------------------------------------------------------------
// 1. Custom object schemas
// ---------------------------------------------------------------------------

const CUSTOM_OBJECTS = [
  {
    name: "inventory_product",
    labels: { singular: "Inventory Product", plural: "Inventory Products" },
    primaryDisplayProperty: "inventory_product_name",
    secondaryDisplayProperties: ["brand", "model", "xupes_reference"],
    searchableProperties: ["xupes_reference", "product_code", "serial_number"],
  },
  {
    name: "customer_product",
    labels: { singular: "Customer Product", plural: "Customer Products" },
    primaryDisplayProperty: "brand",
    secondaryDisplayProperties: ["model", "serial_number"],
    searchableProperties: ["serial_number", "customer_product_sf_id"],
  },
  {
    name: "offer_history",
    labels: { singular: "Offer History", plural: "Offer Histories" },
    primaryDisplayProperty: "offer_type",
    secondaryDisplayProperties: ["offered_price", "status"],
    searchableProperties: ["offer_history_sf_dc"],
  },
  {
    name: "attached_image",
    labels: { singular: "Attached Image", plural: "Attached Images" },
    primaryDisplayProperty: "image_name",
    secondaryDisplayProperties: ["description"],
    searchableProperties: ["attached_image_sf_dc"],
  },
];

async function ensureObjectSchema(def) {
  const existing = await hs("GET", `/crm/v3/schemas/${def.name}`);
  if (existing.ok) {
    summary.skipped.push(`schema:${def.name} (already exists)`);
    return;
  }
  const res = await hs("POST", "/crm/v3/schemas", {
    name: def.name,
    labels: def.labels,
    primaryDisplayProperty: def.primaryDisplayProperty,
    secondaryDisplayProperties: def.secondaryDisplayProperties,
    searchableProperties: def.searchableProperties,
    requiredProperties: [],
    properties: [
      {
        name: def.primaryDisplayProperty,
        label: def.primaryDisplayProperty,
        type: "string",
        fieldType: "text",
      },
    ],
  });
  if (res.ok) {
    summary.created.push(`schema:${def.name}`);
  } else {
    summary.failed.push(`schema:${def.name} -> ${res.status} ${JSON.stringify(res.body)}`);
  }
}

// ---------------------------------------------------------------------------
// 2. Property groups
// ---------------------------------------------------------------------------

const GROUP_NAME = "sf_migration";
const GROUP_LABEL = "SF Migration";

const OBJECTS_WITH_GROUP = [
  "contacts",
  "deals",
  "line_items",
  "commerce_payments",
  "orders",
  "inventory_product",
  "customer_product",
  "offer_history",
  "attached_image",
];

async function ensurePropertyGroup(objectType) {
  const res = await hs("POST", `/crm/v3/properties/${objectType}/groups`, {
    name: GROUP_NAME,
    label: GROUP_LABEL,
  });
  if (res.ok) {
    summary.created.push(`group:${objectType}.${GROUP_NAME}`);
  } else if (res.status === 409) {
    summary.skipped.push(`group:${objectType}.${GROUP_NAME} (already exists)`);
  } else {
    summary.failed.push(`group:${objectType}.${GROUP_NAME} -> ${res.status} ${JSON.stringify(res.body)}`);
  }
}

// ---------------------------------------------------------------------------
// 3. Properties per object
//    name / label / type / fieldType / options — internal names taken verbatim
//    from the mapping sheet. Dropdown option lists marked "PARTIAL" are built
//    from the sample GROUP BY data seen so far, not a confirmed full picklist
//    — extend via HubSpot UI once a full GROUP BY is run against Supabase.
// ---------------------------------------------------------------------------

const TXT = (name, label) => ({ name, label, type: "string", fieldType: "text" });
const NUM = (name, label) => ({ name, label, type: "number", fieldType: "number" });
const BOOL = (name, label) => ({ name, label, type: "bool", fieldType: "booleancheckbox" });
const DATE = (name, label) => ({ name, label, type: "date", fieldType: "date" });
const SELECT = (name, label, labels) => ({
  name, label, type: "enum", fieldType: "select", options: labels.map(opt),
});
const MULTI = (name, label, labels) => ({
  name, label, type: "enum", fieldType: "checkbox", options: labels.map(opt),
});

const CURRENCIES = ["GBP", "EUR", "USD"]; // PARTIAL — only GBP confirmed in samples

const PROPERTIES = {
  contacts: [
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

  deals: [
    SELECT("department", "Department", ["Watches"]), // PARTIAL — only value seen in Supabase to date
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
    SELECT("lead_source_detail", "Lead Source Detail", ["Chrono24 Offer", "Direct Sale"]), // PARTIAL
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

  line_items: [
    TXT("pricebook_entry_id", "Pricebook Entry ID"),
    TXT("tc_number", "TC Number"),
    TXT("opportunity_line_item_sf_id", "Opportunity Line Item SF ID"),
  ],

  inventory_product: [
    // inventory_product_name created inline with the schema
    TXT("product_code", "Product Code"),
    TXT("xupes_reference", "Xupes reference"),
    TXT("brand", "Brand"),
    TXT("model", "Model"),
    TXT("serial_number", "Serial Number"),
    SELECT("status", "Status", ["Sold", "In Stock", "Sold By Partner"]), // PARTIAL
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

  customer_product: [
    // brand created inline with the schema (primary display)
    SELECT("record_type", "Record Type", ["0121t0000000ljSAAQ"]), // PARTIAL — only 1 RecordTypeId confirmed so far, open question in field-mapping.md re: unused Xupes/Restore Handbag variants
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

  offer_history: [
    // offer_type created inline with the schema (primary display)
    NUM("offered_price", "Offered Price"),
    DATE("offer_date", "Offer Date"),
    SELECT("currency", "Currency", CURRENCIES),
    BOOL("is_customer_offer", "Is Customer Offer"),
    SELECT("status", "Status", ["Pending", "Declined", "Accepted"]),
    TXT("response_url", "Response URL"),
    TXT("offer_history_sf_dc", "Offer History SF ID"),
  ],

  commerce_payments: [
    // Not on the sheet, but flagged as needed in field-mapping.md since
    // hs_payment_method_type is a fixed 9-value enum that our 13 real values
    // don't map to 1:1 — remove if you decide not to keep the raw value.
    SELECT("xupes_payment_method_detail", "Xupes Payment Method Detail", [
      "Other Cards Online", "Bank Transfer", "Third Party Platform", "Paypal",
      "Other Cards Chip n Pin", "Amex Online", "Legacy", "Cash", "Amex Chip n Pin",
      "Credit on Account", "Cheque", "Splitit", "Finance Options",
    ]),
    TXT("payment_sf_dc", "Payment SF ID"),
  ],

  orders: [
    TXT("product_tracking_url", "Product Tracking URL"),
    TXT("courier", "Courier"),
    TXT("order_sf_dc", "Order SF ID"),
    // dispatch_courier intentionally skipped — sheet: never observed populated,
    // recommend skipping unless the developer confirms it's used.
    // courier_link intentionally skipped — static per-courier URL, adds nothing beyond `courier`.
  ],

  attached_image: [
    // image_name created inline with the schema (primary display)
    TXT("original_image_url", "Original Image URL"),
    TXT("resized_image_url", "Resized Image URL"),
    TXT("description", "Description"),
    TXT("sf_content_version_id", "SF Content Version ID"),
    TXT("attached_image_sf_dc", "Attached Image SF ID"),
  ],
};

async function ensureProperty(objectType, def) {
  const existing = await hs("GET", `/crm/v3/properties/${objectType}/${def.name}`);
  if (existing.ok) {
    summary.skipped.push(`property:${objectType}.${def.name} (already exists)`);
    return;
  }
  const payload = { ...def, groupName: GROUP_NAME };
  const res = await hs("POST", `/crm/v3/properties/${objectType}`, payload);
  if (res.ok) {
    summary.created.push(`property:${objectType}.${def.name}`);
  } else {
    summary.failed.push(`property:${objectType}.${def.name} -> ${res.status} ${JSON.stringify(res.body)}`);
  }
}

// ---------------------------------------------------------------------------
// 4. Custom associations
//    Native/HubSpot-defined associations (Deal<->Payment typeId 391,
//    Order<->Payment 523/524, Order<->Deal 512, Order<->Line Item 513,
//    Deal<->Line Item, Deal<->Contact, Company<->Contact, Note<->Deal) already
//    exist out of the box and are NOT created here.
// ---------------------------------------------------------------------------

const ASSOCIATIONS = [
  { from: "deals", to: "customer_product", name: "deal_to_customer_product", label: "Customer Product" },
  { from: "deals", to: "offer_history", name: "deal_to_offer_history", label: "Offer History" },
  { from: "deals", to: "attached_image", name: "deal_to_attached_image", label: "Attached Image" },
  { from: "customer_product", to: "inventory_product", name: "customer_product_to_inventory_product", label: "Linked Inventory Product" },
  { from: "line_items", to: "inventory_product", name: "line_item_to_inventory_product", label: "Inventory Product" },
];

async function ensureAssociationLabel(def) {
  const existing = await hs("GET", `/crm/v4/associations/${def.from}/${def.to}/labels`);
  if (existing.ok && Array.isArray(existing.body.results)) {
    const found = existing.body.results.find((r) => r.label === def.label);
    if (found) {
      summary.skipped.push(`association:${def.from}->${def.to}:${def.label} (already exists)`);
      return;
    }
  }
  const res = await hs("POST", `/crm/v4/associations/${def.from}/${def.to}/labels`, {
    label: def.label,
    name: def.name,
  });
  if (res.ok) {
    summary.created.push(`association:${def.from}->${def.to}:${def.label}`);
  } else {
    summary.failed.push(`association:${def.from}->${def.to}:${def.label} -> ${res.status} ${JSON.stringify(res.body)}`);
  }
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

async function main() {
  console.log("== 1. Custom object schemas ==");
  for (const def of CUSTOM_OBJECTS) await ensureObjectSchema(def);

  console.log("== 2. Property groups ==");
  for (const obj of OBJECTS_WITH_GROUP) await ensurePropertyGroup(obj);

  console.log("== 3. Properties ==");
  for (const [objectType, props] of Object.entries(PROPERTIES)) {
    for (const def of props) await ensureProperty(objectType, def);
  }

  console.log("== 4. Custom associations ==");
  for (const def of ASSOCIATIONS) await ensureAssociationLabel(def);

  console.log("\n=== SUMMARY ===");
  console.log(`Created: ${summary.created.length}`);
  summary.created.forEach((x) => console.log("  +", x));
  console.log(`Skipped (already existed): ${summary.skipped.length}`);
  console.log(`Failed: ${summary.failed.length}`);
  summary.failed.forEach((x) => console.log("  !", x));

  const fs = await import("node:fs");
  fs.writeFileSync(
    new URL("./setup-result.json", import.meta.url),
    JSON.stringify(summary, null, 2)
  );
  console.log("\nFull result written to scripts/hubspot-setup/setup-result.json");

  if (summary.failed.length > 0) process.exitCode = 1;
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
