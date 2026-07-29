# Full Migration Plan — SFDC → HubSpot (Chrono24 / Watches)

Builds on the POC (`field-mapping.md`, data model diagram) once the 3-flow architecture
test is validated. Scope here: everything the POC didn't cover — the rest of the SFDC
Apex layer — triaged into in-scope / needs-own-workstream / out-of-scope, plus corrections
to POC assumptions that this Apex documentation surfaced.

## Documents processed

| # | Document | Covers |
|---|---|---|
| 1 | Confluence doc, shared 2026-07-29 | Apex Classes master index + 8 Trigger Handler/Helper deep-dives (Account, Attachment, ContentDocumentLink ×2, DocumentLinkUploadEvent, InterestedProduct, Lead, OpportunityProduct, Opportunity ×2, OppStatusChange, SystemLog ×2, WhatsappChat) |
| 2 | Google Doc, shared 2026-07-29 | All 13 REST Endpoints (UploadEnquiryForm, FetchOutstandingBalance, OnlineCheckout, UploadAppointmentForm, UploadContactUsForm, UploadProductImages, UploadSellOrExchange ×3, UploadSourcing ×3, LeadConvert) |
| 3 | Google Doc, shared 2026-07-29 | All 9 Batch Classes (GoogleAnalytics ×3, LeadAttachmentBatch, LeadContentDocBatch, OpportunityAttachmentBatch, OpportunityContentDocumentBatch, S3AttachmentUploadHandler, S3UploadHandler) |
| 4 | Google Doc, shared 2026-07-29 | Document Generation (Xupes & Document) — AWSDocumentService, DocumentDataRetriever, DocumentGeneratorService/Controller, DocumentPayloadBuilder, DocumentValidator, and the Xupes-branded equivalents |
| 5 | Google Doc, shared 2026-07-29 | eBay Integration (EC_\*) — all 10 classes (CreateEbayInboundLead, DebugMessaging, EbayQueueableApex, LeadEbayProcess, LeadLineItemUtility, LeadUtility, OfferHistoryHandler, Product2Utility, RestCallouts, EbayOffer) |
| 6 | Google Doc, shared 2026-07-29 | Outbound Integrations + JWT + UTIL + Website Flow Actions — OUTBOUND_CreateWatch, OUTBOUND_GetChat, OUTBOUND_MarkProductAsSold, OUTBOUND_UpdateOrder, OUTBOUND_UpdateProductStatus, JWT_service ×3, UTIL_Integration, UTIL_Logger, UTIL_System, WebsiteInStockAction, WebsiteOnHoldAction, WebsiteSoldAction |

---

## 🔴 Correction candidates — check with developer before the full plan locks in

### 1. Order creation direction contradicts the POC's "/api/createWatch inbound" assumption

The original POC context states Order arrives via "a separate inbound `/api/createWatch` flow"
(SMS → SFDC). This Apex doc shows the opposite for two different things with confusingly
similar names:

- **`OUTBOUND_CreateWatch`** — Apex class that sends an HTTP request **from SFDC to the
  Stock Management System** to create a watch, triggered by `BLL_CustomerProduct`
  ("triggers the 'create watch' integration on the Stock Management System"). This is
  **SFDC → SMS**, outbound, about the *watch/Inventory Product*, not the Order.
- **Order creation itself** happens **inside SFDC**, in `OpportunityTriggerHandler.afterUpdate`,
  triggered by **Opportunity stage changes** (Outright Sale/Part Exchange → "Package Waiting
  for Dispatch" creates/updates an Order; Part Exchange → "Closed Won" does a fuller Order
  build-out). No external inbound call is shown creating the Order — it's a same-transaction
  Apex side effect of a stage update.

**Open question to raise:** is there a genuinely separate inbound endpoint that creates Orders
(matching the original "/api/createWatch" description), or was that description actually
referring to `OUTBOUND_CreateWatch` (SFDC→SMS, about the watch) and the Order itself is purely
internal stage-triggered logic? This changes the HubSpot design meaningfully — internal
stage-triggered creation maps to a HubSpot workflow on Deal stage change, not an inbound API
handler.

**Update from the REST Endpoints doc:** `REST_onlineCheckout` (`/onlineCheckout`) *does*
create/update Opportunities directly from an inbound call — but it creates them with
RecordType `Outright_Purchase_Xupes`, a **Xupes-branded** record type, not the Watches
`Outright Purchase` (`0121t0000000n8cAAA`) our pipeline routing table uses. So this endpoint
does **not** resolve the question above — it's a different (out-of-scope) checkout flow, not
the Chrono24/Watches one. The real inbound Order-creation endpoint, if one exists, is still
unaccounted for. Worth naming this specifically when asking the developer: "not
onlineCheckout — is there another one?"

### 2. Part Exchange scope — diagram says out of scope, this doc says otherwise

The data model diagram lists "Part Exchange" under "Out of scope." But:
- `OpportunityTriggerHandler`'s qualifying-types list includes `Part Exchange` alongside
  Outright Purchase/Sourcing/Available to Order.
- Section 5b/5c is a dedicated, non-trivial Order-creation branch specifically for Part
  Exchange (own Order record type, own Closed-Won build-out with Agreement_Item, cloned
  OrderItems, and Payment linking).
- The pipeline routing table (field-mapping.md) already has a live "Part Exchange pipeline"
  (`RecordTypeId 0121t0000000n6lAAA`).

**Open question to raise:** does "Part Exchange" in the diagram's out-of-scope list refer to
a *different* thing (e.g. a standalone Parts Exchange object/RecordType variant used only by
Handbags), distinct from the Watches "Part Exchange" Opportunity type this trigger handles?
As it stands, Part Exchange looks like real in-scope Watches business logic that needs its
own HubSpot workflow, not something to skip.

### 3. "Attached Image" custom object — real name and shape differ from the POC model

The POC's field-mapping.md models "Attached Image" with fields `Opportunity__c`, `Name`,
`Original_Image_URL__c`, `Resized_Image_URL__c`, `Description__c`, `ContentVersionId__c` —
built from the Ian Fry sample. The Batch Classes doc shows the actual object is
**`Lead_Attached_Image__c`**, populated by four different batches:

- `LeadAttachmentBatch` / `LeadContentDocBatch` — set **`Lead__c`** as parent (legacy
  `Attachment` object and `ContentDocument` respectively, both Lead-sourced)
- `OpportunityContentDocumentBatch` — sets **`Opportunity__c`** as parent instead (the one
  our POC sample actually exercised, since Watches doesn't use Leads)
- `OpportunityAttachmentBatch` — **confirmed dead code**, empty stub, unused (per the doc's
  own FAQ)

So the object has **two mutually-exclusive parent lookups** (`Lead__c` OR `Opportunity__c`
per record, never both), not just the single `Opportunity__c` our POC modeled — harmless for
Watches specifically (since Watches records always go through the Opportunity side), but
worth knowing if any tooling assumes `Opportunity__c` is the only parent field.

**Also found, not yet in our property list:** `Image_RTF__c` — a pre-built HTML snippet
(anchor-wrapped `<img>` tag pointing at the original image, displaying the resized one),
generated at upload time for embedding directly into a rich-text field. Candidate to add to
the Attached Image property list (or deliberately decide it's presentation-layer cruft with
no HubSpot use, since the equivalent in our model is "append the link into `hs_note_body`").

**Scale note:** `Lead_Attached_Image__c` currently holds **197,068 records** — worth knowing
for migration volume/performance planning, even though most of that is Xupes/Lead-sourced,
not Watches.

**Also confirmed dead code, safe to skip entirely:** `S3AttachmentUploadHandler` and
`S3UploadHandler` — both stub batches with a constructor bug (the incoming Id list is never
assigned to the field the query filters on), empty `execute()`/`finish()`. Never do anything
even if invoked.

### 4. `customer_product.record_type` — sheet value was for the wrong SFDC object, not a sandbox artifact

**Correction to this section's own earlier version** — it originally claimed
`0121t0000000ljSAAQ` was a sandbox-only Id that doesn't exist in production. That was wrong,
and the sample sheet (Buchanan/Fry raw export, reviewed while building
`buchanan-fry-poc-data.md`) proves it: `0121t0000000ljSAAQ` **is** a real production Id — it's
just the "Watch" RecordType on **Product2**, not on **Agreement_Item__c** (Customer Product).
Both Buchanan's and Fry's Product2 rows show `RecordTypeId = 0121t0000000ljSAAQ` with
`Record_Type_Name__c = Watch`. So the original sheet didn't pull a sandbox value — it pulled
the right-shaped value from the wrong object (Product2 instead of Agreement_Item__c), both of
which happen to have their own separate "Watch" RecordType record with its own separate Id
(RecordType is scoped per SObjectType, so "Watch" the concept has two different Ids
depending on which object it's attached to).

Live Supabase query (`GROUP BY RecordTypeId` on Agreement_Item__c) came back with two
production IDs, neither matching `0121t0000000ljSAAQ` — because that Id genuinely belongs to
a different object, not because it's environment-specific. Resolved both real
Agreement_Item__c values via `SELECT Id, Name, DeveloperName, SobjectType FROM RecordType
WHERE Id IN (...)` in the production Developer Console:

| Id | Name | Count in Supabase | Meaning |
|---|---|---|---|
| `0124J000000MWTTQA4` | Watch | 18,156 | The real Agreement_Item\_\_c Watches value — use this in `customer_product.record_type` |
| `0124J000000MWTSQA4` | Jewellery | 1 | **Not noise** — a genuine Jewellery-RecordType record present in what was assumed to be a Watches-only dataset |
| *(null)* | — | 8,130 (31%) | Still open — need to ask the developer whether these predate RecordType being made mandatory, or something else |

**Actions:**
1. `customer_product.record_type` (HubSpot + `scripts/hubspot-setup/setup.py`) uses
   `0124J000000MWTTQA4` ("Watch" on Agreement_Item\_\_c) — already fixed.
2. If Inventory Product (Product2) ever gets its own record-type-like property, its "Watch"
   value is the *other* one: `0121t0000000ljSAAQ`. Not currently mapped as a property (not in
   the original sheet), noting here so it isn't confused with Customer Product's value later.
3. **Scoping implication for history migration:** the Agreement_Item__c dataset used for this
   check was not purely Watches — at least one non-Watches (Jewellery) record leaked in. Any
   query built for the real historical migration must explicitly filter
   `RecordTypeId = '0124J000000MWTTQA4'`, not assume the source dataset is already
   Watches-only. Worth spot-checking other objects for the same kind of leakage before trusting
   row counts elsewhere in this plan.
4. **Process note:** verify object attribution before trusting an ID's meaning, even when the
   query result "looks" reasonable — this one passed a plausibility check (shape, prefix) but
   was still wrong. The sample sheet's real per-object data caught it; a shape-only check
   wouldn't have.

### 5. `OUTBOUND_CreateWatch` may not create inventory at all — reframes the Order-creation-direction question

The Outbound Integrations doc's own description of `OUTBOUND_CreateWatch` hedges: "sending an
outbound HTTP request to the Stock Management System to create a 'watch' record — **likely
tracking customer interest in a product for restock/availability alerts**." The confirmed
payload backs that reading, not "create an inventory item": it sends exactly **3 fields** —
`opportunityId`, `customerProductId`, `productType` — no watch reference, serial number,
brand, or model. That's not enough data to create a physical inventory record; it fits a
"notify me when available" / waitlist signup instead.

**This matters a lot for correction candidate #1.** We already confirmed Order creation is
internal/stage-triggered Apex, not an inbound call. This finding suggests the "watch" in
`OUTBOUND_CreateWatch` (and possibly in the original "/api/createWatch" description from the
POC's starting context) may never have meant "wristwatch inventory" or "Order" at all — it may
be an unrelated availability-alert feature that happens to share the word "watch" as a pun.
**Sharpen the question for the developer:** ask specifically "what does `OUTBOUND_CreateWatch`
actually create — an alert subscription, or something else?" rather than assuming it's
Order/inventory-related.

**Also resolved in this doc — `OUTBOUND_UpdateOrder` confirms the real Order data flow is
SFDC → SMS, not the other way:** it sends two payload types ("sell" and "updateOrder") pushing
existing Order/Opportunity/OrderItem data *out* to the Stock Management System after the Order
already exists in SFDC:

| SFDC field | Object | Sent as |
|---|---|---|
| Id | Order | `salesforce_order_id` (updateOrder) / `orderId` (sell) |
| Status | Order | `status` |
| Courier\_\_c | Order | `dispatch_courier` |
| Tracking\_URL\_\_c | Order | `dispatch_tracking_url` |
| Product\_Tracking\_URL\_\_c | Order | `packing_tracking_url` |
| Dispatch\_Courier\_\_c | Order | `packing_courier` |
| Description | Order | `delivery_notes` |
| OpportunityId | Order | `outrightPurchaseOpportunityId` (sell) |
| CurrencyIsoCode | Opportunity | `soldCurrency` (sell) |
| Total\_Sold\_Price\_\_c | Opportunity | `soldPrice` (sell) |
| Invoice\_Number\_\_c | Opportunity | `invoiceReference` (sell) — **formula field**, see below |
| LeadSource | Opportunity | `salesChannel` (sell) |
| Product2Id (each item) | OrderItem | `salesforce_product_ids` list (updateOrder) |
| Product2.ProductCode (first item) | OrderItem/Product2 | `barcode` (sell) |

This is a clean, complete reference for what the *existing* SFDC→SMS Order sync sends —
useful directly as a checklist when designing the equivalent HubSpot→SMS push later.

### Invoice_Number__c source — resolved (open question #4 from the POC, closed)

The Document Generation doc confirms `Invoice_Number__c` on Opportunity is a **formula
field** (stated explicitly in the `OUTBOUND_UpdateOrder` field table: "Formula field; sent as
invoiceReference"). It's computed within SFDC itself, not written by the SMS or any external
process — nothing to replicate as an inbound integration, just a value HubSpot needs to
either compute the same way (if the formula logic matters) or accept as historical data only.
`Invoice_Date__c` remains separately explained (set by `ContentDocumentLinkTriggerHelper`
when an invoice PDF gets linked — see the S3/Attachment findings above). The actual PDF itself
is generated by an external AWS Lambda process, orchestrated by
`AWSDocumentService`/`DocumentGeneratorService`/`DocumentPayloadBuilder` — confirmed via this
doc's `buildInvoicePayload`/`buildInvoiceRecordData` methods, which construct the invoice
`recordData` (including the invoice number) sent to Lambda for PDF rendering.

### Periskope/WhatsApp — explicit confirmation to skip, from her own team

The Outbound Integrations doc has an inline note on `OUTBOUND_GetChat`: *"We will have direct
integration with Hubspot and Periskope, can skip these Apex Classes related to Periskope."*
Matches the earlier finding (System Log / Whatsapp Chat trigger handlers) — now confirmed from
two independent places in the documentation, not just an assumption.

---

## ✅ Open questions this document answers

### Who writes to S3 for Attached Images (open question #1)
Confirmed chain, SFDC-side, not the SMS:
1. `ContentDocumentLinkTriggerHandler.afterInsert` classifies the uploaded document, then
   publishes a `Document_Link_Upload_Event__e` platform event per file/parent pair.
2. `DocumentLinkUploadEventTriggerHandler` consumes that event and calls
   `AWSUtils.uploadDocument(parentId, fileId)` — the actual S3 upload.
3. Separately, `AttachmentTriggerHandler` (legacy `Attachment` object, Lead-only) kicks off
   `LeadAttachmentBatch` which also uploads to S3 and stamps an RTF field on the Lead.

**Implication for HubSpot:** this upload step is Apex automation that needs a real
replacement (e.g. a webhook/serverless function on file upload), not something that
disappears on its own — there's no "SMS already does this" shortcut.

**Update from the REST Endpoints doc — a second image intake path exists:**
`REST_uploadProductImages` (`/uploadProductImages/*`) accepts a raw image body plus a
`parentId` (Opportunity or Lead) directly, and creates the ContentVersion/ContentDocumentLink
itself — no SMS or Attachment object involved. This feeds into the *same*
`ContentDocumentLinkTriggerHandler` → S3 pipeline above once the link is created. So there
are two independent ways images enter the system (this direct REST upload, and whatever
creates ContentVersions via the documented SMS flow), both converging on the same S3 export
logic. Worth confirming with the developer which path Chrono24/Watches images actually use in
practice — matters for what the HubSpot-side upload trigger needs to listen for.

### Who populates Payment.Order_Payment__c (open question #2) — partially answered
`OpportunityTriggerHandler` §5c (Part Exchange → Closed Won) explicitly stamps
`Payment__c.Order_Payment__c` with the new Order's Id, in the same transaction that builds
out the Order. **This only covers the Part Exchange path** — Outright Sale (§5a) links
Agreement_Item__c to the Order but the visible logic doesn't show it touching
`Order_Payment__c`. Need to find where (if anywhere) Outright Sale/Purchase Payments get
their `Order_Payment__c` set — likely a different trigger/flow not yet reviewed.

### Invoice fields on Order (open question #4) — now fully answered
`ContentDocumentLinkTriggerHelper.updateOrderStatus`: when a PDF titled with `INV-` or
`PRO-` gets linked to an Order or Opportunity, it sets `Order.Status` from Draft →
"To Be Dispatched" and stamps `Order.Invoice_Date__c` (today) + the parent
`Opportunity.Invoice_Date__c`. `Invoice_Number__c` itself is a **formula field** on
Opportunity (confirmed via the Document Generation + Outbound Integrations docs — see
correction #5's "Invoice_Number__c source" note) — computed in SFDC, not written by any
external process.

### "Agreement" object relationship to Customer Product (open question #6) — answered
`Agreement_Item__c` **is** the Customer Product custom object (confirms the existing model).
It carries an `Order__c` lookup that gets stamped when an Order is created/updated
(§5a, §5c step 1). **This is a third association on Customer Product we hadn't captured** —
alongside `Opportunity__c` (→ Deal) and `Product__c` (soft link → Inventory Product, update-only).

**Action:** add a custom association **Customer Product ↔ Order** to the data model and to
`scripts/hubspot-setup/setup.py` (currently missing).

---

## 📋 New findings to fold into field-mapping.md

- **`Phone_Rollup__c` is 100% derived** — `OpportunityTriggerHandler.beforeUpdate` always
  overwrites it with the current `Phone__c` value, unconditionally, on every update. Same
  pattern as `AccountReference__c` = email: redundant with an existing field. Candidate to
  drop as a separate HubSpot property and just use Deal/Contact phone directly — flag for
  her decision, not a unilateral change.
- **`Owner_Automation__c`** — kept in lockstep with `OwnerId` bidirectionally (whichever
  changes, the other is synced to match). Looks like a legacy SFDC-only sync artifact with
  no HubSpot equivalent need, since we already map `OwnerId` → native HubSpot owner directly.
  Candidate to skip; noting it here so it's a deliberate decision, not an oversight.
- **`validateProductSold`** — blocks closing an Opportunity Won if any linked line item's
  Product is already `Sold`/`Sold By Partner`. This is a **validation rule**, not a field
  mapping — needs a HubSpot equivalent (workflow/validation before Deal → Closed Won),
  goes in the "additional integration work" bucket below, not field-mapping.md.
- **Enquiry__c** — created automatically for every direct (non-Lead-sourced) Opportunity on
  insert (`Name`, `Lead_Source_Text__c`, `Lead_Created_Date_Time__c`, `OwnerId`,
  `Department__c`, `Opportunity__c` lookup). Diagram lists Enquiries as out of scope; this
  looks like derived/bookkeeping data with no obvious HubSpot analogue needed — recommend
  explicitly deciding "don't replicate" rather than leaving it unaddressed.
- **Lead / Lead\_\_c confirmed Xupes-only, not used by Chrono24 Watches** — per the doc's own
  FAQ answer ("As far as my knowledge goes they don't use Leads. Xupes uses Leads."). Good
  confirmation that our POC's "Flow 1 (Lead)" name is a Chrono24/SMS naming convention
  mapping to HubSpot **Contact**, unrelated to the actual SFDC `Lead__c` object — worth a
  one-line clarification in field-mapping.md so this terminology collision doesn't confuse
  anyone reading both docs later.

---

## 🧱 Additional integration work (not data migration — logic that needs a HubSpot-side equivalent)

Beyond copying field values, these SFDC Apex behaviors are business logic that need their
own design decision + build in HubSpot (workflows, custom code actions, or deliberately
dropped with sign-off):

1. **Order creation/update on Deal stage change** (Outright Sale & Part Exchange →
   "Package Waiting for Dispatch"; Part Exchange → "Closed Won" full build-out). Core
   business logic, not optional.
2. **Order ↔ Customer Product / Line Item / Payment linking** at Order creation time —
   needs the new Customer Product↔Order association (see above) plus equivalent linking
   logic in whatever creates Orders in HubSpot.
3. **Email notifications on stage change** — Closed Won, Closed Rejected, Payment Approved
   (Watches dept), Negotiation/Closed Refunded team alerts, signed-agreement delivery to
   client + internal notice. Maps to HubSpot workflow emails; needs template-by-template
   triage (~6+ distinct templates referenced).
3a. Hardcoded recipient emails (e.g. `jodie.freestone@xupes.com`) flagged by her own team as
    needing domain updates — operational cleanup, parallel workstream, not ours to fix but
    worth tracking as a dependency.
4. **Country whitelist validation on Company/Contact** (`AccountTriggerHandler`) — blocks
   save if billing country isn't in an admin-editable list. Needs a HubSpot equivalent
   (property validation or workflow) plus a decision on where the editable list lives and
   how validation failures surface to users — both explicitly still open per the source doc's
   own FAQ.
5. **Document classification + agreement stage automation**
   (`ContentDocumentLinkTriggerHandler`) — file uploaded → classify by filename keywords
   (Final Watch Sales/Consignment Agreement, Part Exchange Agreement, Provisional Watch
   Agreement) → bump Deal stage → notify. Real workflow to design in HubSpot (file upload
   trigger → property/stage automation → workflow email), flagged in the source doc itself
   as needing more scoping.
6. **Sold-product validation** — see `validateProductSold` above.
7. **Live outstanding-balance lookup** (`REST_fetchOutstandingBalance`) — the website portal
   calls this in real time to show a customer `Total_Sold_Price__c - Total_Payment__c` for an
   Opportunity. Department-agnostic (not Xupes-hardcoded), so plausibly still needed for
   Chrono24/Watches customers too. HubSpot equivalent would be a live API read (Deal amount
   minus associated Payment totals) exposed to whatever the website calls — needs a decision
   on whether the portal keeps calling a custom endpoint or this becomes a HubSpot API read.

---

## 🗺️ Full Apex inventory — triage

Categorized from the master index. This is the working checklist for what still needs
review as more Confluence docs arrive — not yet deep-dived beyond what's summarized here.

| Category | Count | Watches/Chrono24 relevance |
|---|---|---|
| Trigger Handlers & Helpers | 17 | **Reviewed in this pass** (8 of 17 deep-dived above); remaining: OpportunityProductTriggerHandler ✅ reviewed, PartExchangeTriggerHandler/Helper (empty stubs, skip) |
| REST Endpoints | 13 | **Reviewed.** 9 of 13 are Xupes-branded Lead intake with hardcoded department (Handbags/Jewellery/Accessories) — **out of scope**: UploadEnquiryForm, UploadContactUsForm, UploadSellOrExchange ×3, UploadSourcing ×3. `REST_onlineCheckout` also out of scope (Xupes RecordType, see correction #1 update above) but does NOT explain Watches Order creation. Genuinely relevant/needs-review: `REST_fetchOutstandingBalance` (department-agnostic, live balance — see Additional Integration Work #7), `REST_uploadProductImages` (second image-intake path, see S3 answer above), `REST_uploadAppointmentForm` (department comes from payload, not hardcoded — could include Watches, needs confirming), `REST_LeadConvert` (generic Lead→Opportunity conversion via email-matched Account, low priority given Watches barely uses Leads) |
| Batch Classes | 9 | **Reviewed.** 3 Google Analytics batches — hardcoded to a **Universal Analytics** tracking ID (`UA-126246953-1`), which Google sunset in July 2023, so this is already dead/broken tracking, not just a migration candidate — strong case to drop rather than replicate. `LeadAttachmentBatch`/`LeadContentDocBatch`/`OpportunityContentDocumentBatch` = the real S3 upload logic (see correction #3 above). `OpportunityAttachmentBatch`, `S3AttachmentUploadHandler`, `S3UploadHandler` = confirmed dead stub code, skip entirely. |
| Document Generation (Xupes & Document) | 19 | **Reviewed (Chrono24 side).** `AWSDocumentService`/`DocumentGeneratorService`/`DocumentDataRetriever`/`DocumentPayloadBuilder`/`DocumentValidator` confirmed as the real invoice/agreement PDF generation pipeline (AWS Lambda-based) — resolves `Invoice_Number__c` (formula field, see correction #5 above). Xupes-branded twins (`XupesDocumentGeneratorService`, `XupesPartExchange*`) not deep-dived — still presumed out of scope per "Chrono24 only" framing, low priority to review further. |
| eBay Integration (EC_\*) | 10 | **Reviewed.** Confirmed fully out of scope for Chrono24/Watches — creates `Lead__c` records (which Watches doesn't use at all, confirmed separately) from eBay buyer messages/offers. Does touch `Offer_History__c` (one of our 4 custom objects) via `EC_OfferHistoryHandler`/`EC_EbayQueueableApex`, confirming Offer History records can originate from eBay sync too — historical-data awareness only, not a live integration to build. |
| Outbound Integrations (OUTBOUND_\*, JWT_\*, UTIL_\*) | 14 | **Reviewed.** `OUTBOUND_UpdateOrder` = full confirmed SFDC→SMS Order field mapping (see correction #5 above) — the real "existing sync" reference. `OUTBOUND_CreateWatch` reinterpreted — likely a restock/availability-alert subscription, not inventory/Order creation (see correction #5). `OUTBOUND_GetChat`/Periskope explicitly confirmed skippable by her team. `OUTBOUND_MarkProductAsSold`/`OUTBOUND_UpdateProductStatus`/`WebsiteInStockAction`/`WebsiteOnHoldAction`/`WebsiteSoldAction` all push product status to Magento/website — SFDC-and-Magento-side concern, not currently modeled in our HubSpot Inventory Product object; flag for a decision on whether HubSpot needs an equivalent outbound hook later. `JWT_service*` ×3 = signed-link email delivery for agreements/invoices, maps to a "generate secure link + send email" workflow need in HubSpot, not a data field. `UTIL_Logger`/`UTIL_System`/`UTIL_Integration` = shared infra (logging, prod/sandbox detection, auth token fetching), no HubSpot equivalent needed as data, but the auth pattern is relevant if HubSpot ever calls the SMS directly. |
| DAL / BLL / DTO Classes | 17 | Supporting query/business-logic/data-transfer layer for the above — review alongside their callers, not standalone |
| Controllers | 14 | Mostly Lightning/Visualforce UI controllers (community portal, password reset, document preview) — likely **out of scope** (UI layer being replaced, not migrated) |
| Utility / Other | 10 | Mixed — inbound email parsers (1stDibs, Chrono24, live chat leads) relevant if those channels stay; `CurrencyUpdateHelper`/`Scheduler` (exchange rates) worth checking against `deal_currency_code`/`currency` properties |
| WhatsApp/Periskope (System Log, Whatsapp Chat handlers) | — | **Confirmed out of scope** per her team's own FAQ answers — Periskope has a native WhatsApp integration, no need to migrate |

**Scale note for planning:** the POC covered 3 narrow flows. This index alone lists ~120
Apex classes. Most will triage to out-of-scope (Xupes-only, UI controllers, already-native
integrations like WhatsApp) or "just a workflow email," but the Order-creation logic,
document/agreement automation, and outbound stock-system integration layer are substantial
and belong in the full plan's effort estimate, not treated as an extension of the POC.
