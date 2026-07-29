# Full Migration Plan — SFDC → HubSpot (Chrono24 / Watches)

Builds on the POC (`field-mapping.md`, data model diagram) once the 3-flow architecture
test is validated. Scope here: everything the POC didn't cover — the rest of the SFDC
Apex layer — triaged into in-scope / needs-own-workstream / out-of-scope, plus corrections
to POC assumptions that this Apex documentation surfaced.

## Documents processed

| # | Document | Covers |
|---|---|---|
| 1 | Confluence doc, shared 2026-07-29 | Apex Classes master index + 8 Trigger Handler/Helper deep-dives (Account, Attachment, ContentDocumentLink ×2, DocumentLinkUploadEvent, InterestedProduct, Lead, OpportunityProduct, Opportunity ×2, OppStatusChange, SystemLog ×2, WhatsappChat) |

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

### Who populates Payment.Order_Payment__c (open question #2) — partially answered
`OpportunityTriggerHandler` §5c (Part Exchange → Closed Won) explicitly stamps
`Payment__c.Order_Payment__c` with the new Order's Id, in the same transaction that builds
out the Order. **This only covers the Part Exchange path** — Outright Sale (§5a) links
Agreement_Item__c to the Order but the visible logic doesn't show it touching
`Order_Payment__c`. Need to find where (if anywhere) Outright Sale/Purchase Payments get
their `Order_Payment__c` set — likely a different trigger/flow not yet reviewed.

### Invoice fields on Order (open question #4) — partially answered
`ContentDocumentLinkTriggerHelper.updateOrderStatus`: when a PDF titled with `INV-` or
`PRO-` gets linked to an Order or Opportunity, it sets `Order.Status` from Draft →
"To Be Dispatched" and stamps `Order.Invoice_Date__c` (today) + the parent
`Opportunity.Invoice_Date__c`. Still open: where `Invoice_Number__c` itself gets set —
likely in the Document Generation Apex (`DocumentPayloadBuilder` builds "invoices" payloads)
— need that doc next.

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

---

## 🗺️ Full Apex inventory — triage

Categorized from the master index. This is the working checklist for what still needs
review as more Confluence docs arrive — not yet deep-dived beyond what's summarized here.

| Category | Count | Watches/Chrono24 relevance |
|---|---|---|
| Trigger Handlers & Helpers | 17 | **Reviewed in this pass** (8 of 17 deep-dived above); remaining: OpportunityProductTriggerHandler ✅ reviewed, PartExchangeTriggerHandler/Helper (empty stubs, skip) |
| REST Endpoints | 13 | Mostly website form intake (enquiry/appointment/contact/sell-exchange/sourcing) — need triage per form; `REST_onlineCheckout` worth checking against the Order-creation-direction question above |
| Batch Classes | 9 | Mostly S3 upload batches (already covered via trigger docs) + Google Analytics — GA batches are candidates to drop (native HubSpot analytics instead) pending her confirmation |
| Document Generation (Xupes & Document) | 19 | Split Chrono24-branded (`DocumentGeneratorService` etc., in scope) vs **Xupes-branded** (`XupesDocumentGeneratorService`, `XupesPartExchange*`, in scope only if Xupes Watches business is in scope — needs confirmation, likely mostly out of scope per "Chrono24 only" framing) |
| eBay Integration (EC_\*) | 10 | Separate marketplace channel; **touches Offer_History\_\_c** (one of our 4 custom objects) — means Offer History records can originate from eBay sync too, not just the Chrono24 SMS flow. Otherwise likely out of scope for this migration. |
| Outbound Integrations (OUTBOUND_\*, JWT_\*, UTIL_\*) | 14 | Core SMS-facing integration layer — `OUTBOUND_CreateWatch`, `OUTBOUND_UpdateOrder`, `OUTBOUND_UpdateProductStatus`, `UTIL_Integration` (auth) directly relevant, needs full review next |
| DAL / BLL / DTO Classes | 17 | Supporting query/business-logic/data-transfer layer for the above — review alongside their callers, not standalone |
| Controllers | 14 | Mostly Lightning/Visualforce UI controllers (community portal, password reset, document preview) — likely **out of scope** (UI layer being replaced, not migrated) |
| Utility / Other | 10 | Mixed — inbound email parsers (1stDibs, Chrono24, live chat leads) relevant if those channels stay; `CurrencyUpdateHelper`/`Scheduler` (exchange rates) worth checking against `deal_currency_code`/`currency` properties |
| WhatsApp/Periskope (System Log, Whatsapp Chat handlers) | — | **Confirmed out of scope** per her team's own FAQ answers — Periskope has a native WhatsApp integration, no need to migrate |

**Scale note for planning:** the POC covered 3 narrow flows. This index alone lists ~120
Apex classes. Most will triage to out-of-scope (Xupes-only, UI controllers, already-native
integrations like WhatsApp) or "just a workflow email," but the Order-creation logic,
document/agreement automation, and outbound stock-system integration layer are substantial
and belong in the full plan's effort estimate, not treated as an extension of the POC.
