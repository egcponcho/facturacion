# Supplier workspace: PO → invoice → packing list → cartons → transport

A system where each supplier (and the internal team) builds its invoices from purchase orders, distributes them into packing lists and cartons, and the imports team assigns them to load units and tracks the shipment to the warehouse.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite for quick development).
- **Frontend:** Vue 3 + Vite, no component or chart libraries (own SVG icons and charts).
- **Language:** the whole interface, messages, documents (PDF/Excel) and upload templates are in English. Code identifiers and comments are in Spanish.
- **Tested:** 26 end-to-end tests on PostgreSQL (25 on SQLite, the row-locking test needs PostgreSQL).

## Getting started

### Quick option (SQLite, no database to install)

```bash
# Terminal 1: API at http://localhost:8000 (docs at /docs)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Terminal 2: UI at http://localhost:5173
cd frontend
npm install
npm run dev
```

On first start demo data is created (TNF and Vans, POs with sizes, templates and a shipment with a 40HC).

### Docker and PostgreSQL

```bash
docker compose up --build
```

Everything runs at http://localhost:8000 (the API also serves the built frontend).

### In the cloud (Render, free)

The repository includes `render.yaml`, which creates the PostgreSQL database and the web service from the `Dockerfile`.

1. Go to https://dashboard.render.com/blueprints and click **New Blueprint Instance**.
2. Connect GitHub and choose this repository (branch `main`).
3. Click **Apply**. In a few minutes it is live at `https://facturacion-XXXX.onrender.com`.

`SECRET_KEY` is generated automatically and demo data loads on first start (`SEED_DEMO=1`; set it to `0` for real data). `COOKIE_SEGURA=1` is already set because Render serves over HTTPS.
Free plan limits: the service sleeps after 15 minutes idle (first request takes ~1 minute), the free database expires after 30 days and attachments live on temporary disk.

The same image runs on Railway, Fly.io or Google Cloud Run: set `DATABASE_URL` (`postgres://` and `postgresql://` are accepted) and `SECRET_KEY`; the port comes from `PORT`.

### Demo users (password `Supplier2026`)

| Email | Role | Registered mobile |
|---|---|---|
| tnf@demo.com | Supplier The North Face | +84 28 3770 001 |
| vans@demo.com | Supplier Vans | +86 755 2660 001 |
| interno@demo.com | Imports team | +503 7000 0002 |
| admin@demo.com | Administrator | +503 7000 0001 |

The demo does not send real SMS: the sign-in screen shows the verification code (see *Secure access*).

## Secure access

- **Two-step sign-in:** email and password, then a **6-digit code sent by SMS to the user's registered mobile**. The code expires in 5 minutes, allows 5 attempts, can be resent after 30 seconds (up to 5 sends) and is stored only as a keyed hash.
- **Server-side sessions** in an `httpOnly`, `SameSite=Strict` cookie (`Secure` behind HTTPS). They expire after 12 hours or 30 minutes of inactivity, and are revoked on sign-out, password change, mobile change, deactivation or when two-step verification is turned off. The browser never sees a token.
- **Lockout:** 5 wrong passwords lock the account for 15 minutes; the same message is returned for an unknown email or a wrong password. Requests are rate limited per network.
- **Passwords:** at least 10 characters with letters and numbers, not containing the user name; users change their own from the top bar. An administrator resetting a password also unlocks the account.
- **Restricted routes:** every API route requires a session and checks the role's permissions (suppliers only see their own documents and get 404 for anyone else's). The UI hides and blocks the pages a role cannot use. Changes with the cookie require the `X-Requested-With` header (CSRF protection).
- **Security headers:** CSP, `X-Frame-Options: DENY`, `nosniff`, strict referrer policy and HSTS behind HTTPS.
- **Users** (*Users and access*, administrator): each user has a role, a registered mobile in international format (`+50370001234`) and two-step verification on or off.
- **Roles and access:** roles are free: the administrator creates each one with a **name, a description and the permissions** ticked module by module (see, create, edit, delete and each module's own actions: import POs, finalize or reopen invoices and packing lists, classify and approve sheets, manage shipments, see tracking, edit the tariff schedule, master data, administration…), edits them at any time and assigns them to users. There are no fixed role types: three starter roles (Administrator, Internal team, Supplier) are created as a starting point and can be edited or deleted like any other. **What data a user sees depends on the user, not the role:** a user with a supplier assigned only sees that supplier's documents, and the role's permissions over global data or administration do not apply to them (the role form marks them *Internal users only*). Changes apply at once; the menu and the buttons follow the permissions and the server enforces them. A role with users cannot be deleted, and the system never lets the last active administrator lose the administration permission.

To send real SMS set `SMS_PROVEEDOR=twilio` with `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM`. With the default `consola` provider the message goes to the server log, and only in demo mode (`SEED_DEMO=1`) is the code also shown on screen.

## 5-minute tour

The demo data already has history: invoices from past months, a received container, another in transit and an invoice ready to ship.

1. Sign in as **tnf@demo.com** (one click on “The North Face”, then enter the code shown). **Home** shows what is left to invoice, pack and finalize, where the goods are and the shipments on the way.
2. In *Purchase orders*, on PO 4400003845 click **Invoice** (or open it and change “To invoice” to take only part; several POs can be combined). Review and click **Create invoice**.
3. In the invoice, the steps at the top say what is missing. Click **Pack pending**: it creates the packing list with everything and opens it.
4. In *To pack*, click **Auto-pack**. Lines with a casepack are packed with that exact quantity per carton, lines with an inner pack in whole inner packs, and the rest with the suggested template. The remainder that does not fill a carton goes to a partial carton with estimated weight (or stays unpacked).
5. In *Review*, check the contents **by destination** and the **suggested load units**, **Confirm estimates** and **Finalize packing list**. Back in the invoice, enter number and date and click **Finalize**.
6. Sign in as **interno@demo.com**, open *Shipments* → EMB-0003, choose 40HC #1 and click **Assign cargo**: the panel suggests the load units for the selected volume and weight. Only finalized invoices and packing lists are offered. Then **Record departure**.
7. Open **Products** (as interno@demo.com). *Ready to approve* has the Vans Authentic White: the classification panel shows the suggested HS code 6404.19, why, and the national code for each destination country. Click **Approve**. From then on its PO lines show 6404.19.90.00 (El Salvador) and invoices take it automatically. As tnf@demo.com, the *Summit blue* jacket was returned with notes: fill in the outer fabric composition and save it; it goes back to review.
8. *Tracking* shows each PO (and, when opened, each SKU by stage), and each shipment with its units, with the margin against the in-store date. Everything downloads as PDF or Excel. *Master data* holds all catalogs.

## Item data vs. PO line data

| Item (master data, *Master data → Items*) | PO line (purchase data, comes in the PO file) |
|---|---|
| SKU, style, color, size / prepack ID, description | PO number and line, company, plant, storage location |
| Brand, group (category → packing rule), supplier | Destination center (country), port of loading, countries of origin and shipment |
| Type (solid or prepack), unit of measure (PAR, UN, CJ) | Quantity, unit price, currency, incoterm |
| Item code (free alphanumeric) and supplier SKU | XF dates, in-store date, commercial and logistics release |
| UPC | |
| Prepack breakdown (size run per master carton) | **Casepack** for solids (optional; the inner pack is usually defined later, in the packing list) |

The item has no casepack: it is set on each PO line, because the same item can be bought in different packs. In *Purchase orders* the line table groups the columns as “Item · master data” and “PO line · purchase data”, and the internal team can edit a line's casepack and inner pack while it is not invoiced.

The HS code, the country of origin, the product type and the description are not typed on the item: they come from the **product's technical sheet** (next section), shared by all its sizes. The item group sets the packing rule; it does not define the product type.

## Products: technical sheet and tariff classification

The **item code** is free: any numeric or alphanumeric code of up to 40 characters (letters, digits, `.`, `_`, `-`, `/`), with no fixed length or prefix. Each item belongs to a **generic** (the style-color, up to 40 characters); when the file or form does not bring it, it is derived as `STYLE-COLOR`. A **product** is a generic: its sizes and prepacks share one technical sheet and one classification. A generic is created once with its master data (*Master data → Items → New generic*) and then only sizes are added, each with its own item code (typed in full, or generic + size code), UPC and supplier SKU. Sizes can be entered as ranges with gaps (e.g. `7-10, 12, 14`). *Master data → Items* shows one row per generic by default (**Compact**), expandable to its sizes and prepacks; **List** shows one row per item code. A prepack has its own code and keeps the generic of its solids.

- **Technical sheet**: product type, gender, who it is for, use, size range, country of origin, composition by part (outer fabric, lining, upper, sole…), the features that change the code (only those are asked), photos and the customs description in Spanish (built from the sheet, or written by hand): complete — what the product is, its parts (upper and sole), height, fabric, fill, use and who it is for — but with each material said only by its category: **CUERO, TEXTIL or SINTÉTICO** (rubber, plastics and artificial leather), without percentages or fibers and without the brand (it has its own field), e.g. *TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, PARA DEPORTE O ENTRENAMIENTO, UNISEX*.
- **Classification engine**: runs in the browser while the sheet is edited. It applies the Harmonized System 2022 rules (GRI, section and chapter notes) for clothing, footwear, bags and accessories, learns from what was already approved and returns the 6-digit SAC subheading, its confidence, the reasoning, alternatives and inconsistencies to check.
- **National codes by destination**: only lines published by an official source exist (with source, version and validity); the company never creates them. GT, SV and HN apply the regional SAC at 10 digits, so their lines are the official ACI lines. NI, CR and PA show *Official national tariff data not available* until their national tariff is loaded with its source and version. The company's past classifications (`historial_clasificacion`) only help choose among official lines (*preferred by your company history*). When a country splits the subheading further, the sheet asks only for that data. The internal team types the national code directly in the *By destination* table (it applies when leaving the field, checking the digits and the subheading), can go back to the automatic code and **remember** it for similar products. Similar products show their generic. The sheet no longer asks for the size range: it comes from the generic's sizes. Each material typed in the composition shows how it counts for the tariff (leather, textile, rubber or plastics, synthetic): trade names such as synthetic suede, PU leather, leatherette, cowhide, nubuk, phylon, flyknit or corduroy are recognized, and unknown words can be taught. The classification panel shows the 6-digit SAC subheading and the **SAC legal notes** that apply (general rules, section, chapter and subheading notes); they are edited in *Tariff schedule → SAC legal notes* and the specialist opinion reads them too. The base is the **official text of the SAC** taken from SIECA's Arancel Centroamericano de Importación (VII Amendment, version 6, August 2025): 518 notes (the six General Rules, section notes, chapter notes, subheading notes and the Central American complementary notes of every chapter). The panel lists first the notes cited by the engine and those that touch the sheet (baby, unisex, coated, leather, sport…). Notes can be edited, loaded from Excel and exported. When a national code is added or edited, the form shows only the conditions that split its subheading: the ones that country already uses there, the ones other countries use and the ones that open national codes in its chapter, plus how that country splits the subheading today (all of them can still be shown). Guatemala, El Salvador and Honduras (10 digits) come with the official tariff lines of the ACI (SIECA, VII Amendment, version 6) for the chapters the engine classifies, with their DAI; the conditions the classifier deduces from their text (metal toe cap, covering the ankle or the knee, overshoe, for men/women/babies, hats) are engine rules, never part of the official line. The full list of SAC headings and subheadings (6,607) is loaded with its official text. Nicaragua, Costa Rica (12 digits) and Panama (own tariff) have no national lines until their official tariffs are loaded with *Upload codes* (source and version required). See `docs/arquitectura_clasificacion.md` for the three layers (official data, classification engine, company knowledge). `backend/scripts/sieca` rebuilds these files from a new ACI version.
- **Any product**: chemicals, raw materials or anything else uses the same sheet with the generic categories (*Chemical*, *Raw material*, *Other*) or any category created in the configuration. Candidates come from the official tariff text of the enabled chapters, and the result stays a suggestion that a specialist confirms.
- **Legal basis**: each destination country has its legal basis (the Central American Import Tariff for the MCCA countries, with the 12-digit national openings of Nicaragua and Costa Rica; Panama's National Import Tariff). It is edited in *Tariff schedule → Countries* and shown under the national codes of each sheet.
- **Explanatory notes**: the notes panel also lists the explanatory notes of the heading. It comes with short summaries of our own for the headings of chapters 42, 61, 62, 64 and 65, marked as such; the official text of the WCO Explanatory Notes is copyrighted and not included, but it can be loaded (kind *Explanatory note (HS)*, heading code) with *Upload notes*.
- **Trade agreements by origin**: the *Trade agreements* tab of each product shows, for every destination country and according to its country of origin, whether a trade agreement covers that origin and which proof of origin (certificate of origin, EUR.1, FAUCA…) must be presented to get the preference; without one, the full DAI applies. It comes with a reference base of the agreements in force for Central America and Panama (MCCA, DR-CAFTA, EU and UK association agreements, Mexico, Korea, China–Costa Rica, China–Nicaragua, Taiwan–Guatemala, Colombia, Chile, Peru, Canada, Singapore, Dominican Republic, EFTA, Israel–Panama), maintained in *Master data → Trade agreements* (origin and destination ISO codes, proof of origin, notes). Check it against the official sources before relying on it.
- **Flow**: a sheet is a **draft** that anyone with access (the supplier or the internal team) can edit and save as many times as needed. When it is complete, it is **sent to review** (one by one or in bulk from the list); from then on the supplier cannot change it unless it takes it back to draft. The internal team **approves** it (or chooses another code) or **returns** it with notes, and it goes back to draft. Approved sheets are locked; a change opens a **new version**, and the previous ones stay in the *Versions* tab, where each can be viewed as it was (data, composition, customs description, HS code and national codes) and downloaded as PDF or Excel.
- **Where it is used**: each PO line shows the code for its destination country; invoice lines take the code, origin and customs description from the approved sheet (they are not typed on the invoice). An invoice cannot be finalized while a product is not classified; the message links to its sheet.
- **Specialist opinion (optional)**: with `ANTHROPIC_API_KEY`, the internal team can ask Claude for a second opinion with the sheet and up to two photos. It never approves anything.
- **Two descriptions**, both built from the sheet and editable: the customs one in Spanish, and a simple commercial one — product type and brand, e.g. *CALZADO VANS* or *CHAQUETA THE NORTH FACE* — used on the invoice and the packing list.
- **Prepacks are not classified**: they are built from solids and take the product and HS code of their solids.
- The sheet downloads as **PDF or Excel** (the Excel adds a sheet for the composition, the national codes and the sizes). The product list report downloads as Excel or PDF with the composition, the customs description and the saved national code for each destination country; the Excel also has one row per part of the composition and one per country code.

**Classification support.** The product page has a *Classification support* panel tied to the sheet's subheading and the destination national codes: **Legal notes** (SAC rules and notes that apply), **Explanatory notes** and **Legal basis** (the national tariff lines with their conditions). It is reference material for the classification and the review, not an automatic adaptation of the sheet to the whole SAC.

## Tariff schedule

*Products → Tariff schedule* (internal team) has a side menu in four groups. Official data, the engine's configuration and each country's requirements are kept apart:

**Tariff**
- **Three layers** (see `docs/arquitectura_clasificacion.md`): *Tariff schedule* is split into **Official data** (sources and versions, tariff tree, countries, national codes, legal notes, taxes, regulations, data import, *Tariff data integrity*), **Classification engine** (domains and categories, chapters, attributes with options and scopes, rules — configuration, not official data, also under `/api/clasificacion/configuracion/…`) and **Company knowledge** (classification history, manual decisions and corrections, learned keywords and synonyms, under `/api/conocimiento/…`). The engine returns `legal_confidence` (rules and official text only) and `historical_confidence` (company history only); history only orders the candidates official data allows.
- **One engine for every domain**: `POST /api/clasificacion/sesion` classifies footwear, apparel, chemicals and raw materials alike (texto, dominio, categoria, ficha, respuestas, paises, version). Footwear, apparel, accessories, chemicals and raw materials are written from the HS Explanatory Notes in `data/motor/familias/*.json` (generated by `scripts/familias/construir.py`, which checks every rule and test case against the official tree): categories, questions with the note that justifies them, `R-NE-*` rules and test cases. Products can attach **SDS / TDS / COA** documents (*Technical documents* tab): their data (CAS, composition, physical state, density, pH…) fill empty facts of the sheet and are never a tariff source.
- **Tariff tree**: the official SAC 2025 v6 (99 chapters, 1,012 headings, 5,595 subheadings, 7,517 tariff lines with their DAI; the 519 lines whose DAI the ACI sends to Part II, which differs by country, keep no single rate), versioned with source and checksum. Search by code or words; each node shows its legal notes and, per country, the national codes, taxes and regulations.
- **Chapters**: which chapters the classifier uses (active, enabled, automatic candidate, manual only, archived), in bulk.
- **National codes** of every country with their duty, version, source and validity. The code length is configurable per country (8 to 14 digits when no schema is set).
- **SAC headings and subheadings** and **Legal notes**, editable.

**Requirements by country**
- **Regulations**: permits, licenses, registrations, labeling… for a code or a pattern (e.g. `3304`).
- **Taxes**: VAT/ITBMS/ISV, excise… with rate, basis, thresholds and legal basis. The most specific pattern of each type wins.
- **Countries**: the code schema and the source of each kind of data.

**Classification engine**
- **Domains** (chemicals, raw materials, footwear, apparel, accessories) and their chapters. A domain only orders questions and candidates; it never forces or excludes a chapter.
- **Attributes**: what the product sheet asks, with its options (synonyms, order, active) and where (system, domain, chapter, heading, subheading or product category; ask, required or do not ask). The sheet takes labels, disabled options and switched-off questions from here.
- **Classification rules**: the system rules (only enabled chapters, legal notes over text similarity, ask only what distinguishes, specialist review when ambiguous…) and the national selection rules. These are the product conditions that pick each national code, kept apart from the official code.

**Data**
- **Sources and versions** of every dataset.
- **Data import**: the three official packages (01 catalogs, 02 dynamic engine, 03 national codes, regulations and taxes) are loaded by stages:
  1. Upload the file to a preview. It validates the file and shows each new, changed or replaced record (before → after), the errors and the warnings.
  2. Publish to apply it, or discard it. If the data changed since the preview, you are asked to review it again.

  Loads never delete what is published.

### One classification engine (server)

There is **a single classification engine**, in Python (`backend/app/services/motor_clasificacion.py`). The product sheet, saving, bulk classification, uploads, approval and the specialist opinion all call it; the browser only shows and edits (it has no classification logic).

- **Natural sheet → facts.** The UI sends the sheet as typed (category, composition by part, gender, age, use…). The server normalizes it (`ficha.py`): reads compositions (`composicion.py`), derives facts (predominant fiber, upper/sole material…), applies implications and option blocks, detects what the name and use say, and keeps what the person chose.
- **Every category works the same way**, footwear and apparel included. Categories (`CategoriaProducto`), attributes, options, dependencies and scopes are data. Create a domain, a category, its attributes, options, scopes, rules and national codes in *Tariff schedule*, and its products are classified without code changes.
- **Scopes (SHOW / REQUIRE / HIDE).** The most specific scope wins: category > domain > subheading > heading > chapter > system. Ties go to priority, then HIDE > REQUIRE > SHOW, then the newest.
- **Rules.** A higher number means higher precedence. There are three layers: legal (legal notes, national tariff), system and company. A company rule never breaks a legal restriction (`blocked_by_legal`). A rule that collides with a higher one is `overridden_by`.
  - RESTRICT and EXCLUDE narrow the allowed codes.
  - BOOST only raises allowed codes.
  - ASK asks for data.
  - REVIEW and WARN send the product to review.

  Every rule has a revision number and a signature. A legal rule must reference its legal note, and the UI shows *Legal evidence* apart from *System rule* and *Company rule*. Rule codes are checked against the tree of the version in force.
- **Versions.** The version in force is resolved by date and scope (regional or per country). The same entry with the same date reproduces a past classification. National lines come only from the country's version in force and within their own validity; official lines are never edited, and company changes are overrides with a reason.
- **National codes.** Each country has its valid lengths (`10, 12`…). A code is validated against them and never truncated. A company code is accepted only with a valid length and inside the subheading.
- **Evidence.** Each answer carries the version, inputs, derived facts, rules (evaluated, applied, overridden), legal notes, HS6, SAC, national codes, confidence, alternatives, review reasons and overrides. Approval stores it in the product and in each version.
- **History** only boosts codes the rules allow.

A code from a chapter that is not enabled cannot be approved.

The database schema is managed with Alembic (`backend/alembic`). Pending migrations run at start-up (demo and production alike). A test checks that the migrations match the models.

## Bulk uploads and exports

- **Items by generic, with their technical sheet** (*Master data → Items* or *Products*): an Excel template with two sheets. *Generics*: one row per generic with its master data (style, color, brand, group, supplier, unit) and the sheet columns (category, gender, age, use, sizes, origin, composition by part and the features that change the code). *Sizes*: one row per size with its size code (or the next free one), UPC and supplier SKU. After the upload, the engine completes each generic and suggests its HS code automatically. A single sheet with one row per item code is also accepted. Every upload window has a **Preview** of the template (sheets, columns, required ones, example rows and what goes in each column) besides the Excel download.
- **Every master-data catalog** (brands, groups, suppliers, companies, plants, contacts, warehouses, carriers, unit types, countries, ports) has its own Excel template, upload (creates or updates by code) and Excel/PDF export with the filters of the screen.
- **Reports** follow the filters selected on screen; the dimension filters accept one or several values.

## Dashboard periods

The dashboard shows *In the period* (invoiced value, packing lists finalized, shipments arriving, products classified) and the invoiced chart for the selected period — this month by default — with quick choices (this week, this month, last month, this quarter, this year, 12 months, custom). The chart groups by day, week or month depending on the length, and it can be filtered by brand.

## Packing rules

Every packing option the supplier needs is available and enforced on the server:

- **Solid with casepack:** each carton carries exactly the casepack, same style, color and size; sizes are never mixed. Only the last carton may be partial, and it is flagged to confirm with the Commercial Brand Manager.
- **Prepack:** one assortment per master carton, fixed size distribution; the prepack is already a defined carton, so it takes neither casepack nor inner pack.
- **Solid without casepack (apparel, accessories):** the quantity per carton comes from a template or is entered freely, and cartons can be mixed.
- **Inner packs:** when the PO line has an inner pack, all its inner packs hold the same quantity of units or pairs, and every quantity (PO line, invoice line, packing list move, carton contents, templates used by auto-pack) must be a whole number of inner packs. With a casepack, the casepack must be a multiple of the inner pack (e.g. casepack 20 = 4 inner packs of 5); without a casepack, cartons are packed in multiples of the inner pack. Each inner pack carries a label identifying the product and the total quantity inside, and each unit or pair inside keeps its individual label; the packing list shows the inner packs per carton.
- **By destination country:** a carton never mixes goods for different destination centers. The packing list shows what goes to each destination (quantities and cartons) so the supplier packs and labels each one separately; the document shows the final destination, or “per carton” when there are several.
- **Label:** *standard* if the carton holds a single PO, style, color and size; *consolidated* otherwise.
- **Pallets:** cartons can be palletized (pallet dimensions and tare); volume uses the pallet dimensions and gross weight adds the tare.

### Load unit suggestions

From the packing list volume (m³) and gross weight the system suggests load units using the *Unit types* catalog:

- **Ocean:** full containers at about 85 % usable volume (cartons never fill 100 %), LCL when the volume does not justify a container, or full containers plus a smaller one or LCL for the remainder.
- **Air:** one air waybill by chargeable weight (the greater of actual weight and 167 kg per m³).
- **Road:** full trucks (FTL) or partial load (LTL).

The recommended option (fewest full units, then least spare capacity) is shown in the packing list and when assigning cargo to a shipment.

## Master data

One place with create, edit, delete and searchable filters for: **companies**, their **plants**, **contacts**, **storage locations**, **countries**, **ports**, **brands**, **item groups**, **suppliers**, **items**, **prepacks**, **carriers** and **unit types**. Records in use cannot be deleted.

- **Suppliers:** code, name, legal name, tax ID, country, address and contact (they appear as exporter on the invoice and packing list). Each supplier has **its brands**, **the companies it works with** and its own **items**; an item's brand must be one of its supplier's.
- **Carriers:** code (SCAC or IATA), name, type (ocean, air, road or multimodal) and the companies they work with.
- **Unit types:** mode, **service** (FCL, LCL, air, FTL, LTL), capacity in m³ and kg and whether a seal is required.
- **Ports:** sea port, airport or land border. A **plant** has a main arrival port and other arrival ports.
- **Companies and plants:** the PO company is **billed**; its plant is the **notify party** with its country and arrival port. The PO **destination center** (e.g. 2220) says which country the goods finally reach.
- **Items:** item code (numeric or alphanumeric), generic (optional), style, color and size (optional), brand, group and **unit of measure**. Solids are created here, manually or with `plantilla_articulos.csv`.
- **Prepacks:** an item with its own product code, a **prepack ID** (its size, e.g. `AB12`) and a fixed **breakdown** built only from solids of the same style and color. The breakdown can be viewed everywhere but never changed. Bulk load with `plantilla_prepacks.csv`.

## Purchase orders

- Free PO number (up to 40 characters) and free line number (alphanumeric, up to 10).
- **Required vs optional:** only supplier, PO number, line, item and quantity are required. Company (bill to), currency and price can be completed later; they are required **to invoice**, and value calculations show them as pending meanwhile. A price requires a currency; a quantity must be greater than 0.
- **Packing on the PO:** a prepack brings its size run; a solid may bring its casepack. The inner pack is usually defined later in the packing list (*Per inner pack* column, editable while the line has no cartons and the PO did not define it).
- Each line's **SKU** must exist in the item master, belong to the PO supplier, and the supplier must work with the PO company.
- **Storage location per line:** the same PO can send each line to a different storage location of the same company.
- **Releases (two teams):** **commercial** is `P` (pending) or `C` (released; empty means C). **Logistics** is **304** not released, **300** released or **301** released with later changes. Only **C and 300/301** can be invoiced.
- **Release dates:** each release keeps its date (from the file's `commercial_release_date` / `logistics_release_date`, or the day it became released) to measure lead times. Logistics must release a PO a number of days **before its XF**: 21 for Asia and 15 for other origins by default (*Master data → Lead time targets*).

### Creating and importing POs

*Load purchase orders* has two modes with the **same structure and validations**: **Form** (header plus line cards; the item list is filtered by supplier and the unit adapts to the item) and **File**. In *Import POs* (internal team) upload the SAP Excel or CSV. A preview shows what is new, changed, unchanged, conflicts and errors; nothing is saved until confirmed. Conflicts (e.g. a quantity below what is invoiced, or a casepack/inner pack change on an invoiced line) are not applied and appear as alerts.

Required columns: `supplier, po, po_line, sku, quantity`. Optional: `unit_price, currency, company, plant, destination, storage_location, incoterm, po_date, port_of_loading, country_of_origin, country_of_shipment, xf_date_original, xf_date, in_store_date, commercial_release, logistics_release, commercial_release_date, logistics_release_date, uom, casepack, inner_pack`. The previous Spanish column names and common aliases (`vendor`, `material`, `qty`…) are still accepted. **Sample template** downloads an Excel template generated for the user, with its sample dates in the user's date format.

Codes are kept as text to preserve leading zeros; format those columns as text in Excel before exporting.

## Data consistency

Master data and documents stay chained, both in the PO file and in the PO form:

- A supplier only works with **its companies** (*Master data → Suppliers*): a PO for another company is rejected, and the form only offers those companies and, from them, their plants, storage locations and destination centers. Without a company, the PO takes the one of its plant, storage location or destination center.
- Plant, storage location and destination center must belong to the PO company; the item must belong to the PO supplier and its brand must be one of the supplier's brands; inactive suppliers and items are rejected.
- An item's brand must be one of its supplier's brands; an item on POs cannot change supplier; a supplier cannot lose a company or a brand it already uses; a plant or storage location used on POs cannot change company; a contact's plant must belong to its company.
- An invoice only takes lines of one supplier (and of compatible POs); a shipment arrives at one plant and its carrier must work with that company.

## Packing list number

Each packing list gets `PL-001`, `PL-002`… by default, and the supplier can type **its own number** (up to 40 characters: letters, numbers and `. _ - / #`) in the packing list header while it is in draft or under correction. It must be unique among the supplier's active packing lists.

## Shipments

**Status against the in-store date.** Each load unit and shipment estimates its in-store date from the actual arrival, or the ETA, or the departure (actual or ETD) plus the transit time, plus the post-arrival lead times of the destination and the extra days of the product group (*Master data → Item groups → Extra days*, e.g. for products that need labeling or inspection). It is compared with the earliest in-store date of its POs: **On time**, **At risk** (slack below `DIAS_MARGEN_RIESGO`, 7 days by default) or **Late**. A shipment takes the worst status of its units.

- **Everything follows the mode:** an ocean shipment only offers sea ports, shipping lines and containers; air, airports, airlines and air waybills; road, borders, road carriers and trucks. The **service belongs to each unit**, so an ocean shipment can be FCL, LCL or mixed.
- **Only finalized documents travel:** a load unit only accepts packing lists that are finalized and whose invoice is finalized; the assignment panel lists only those. Reopening an invoice or a packing list that is on a planned unit takes it off the unit (it is added again once finalized); after departure they can no longer be reopened.
- While **planned**, units and cargo can be added, moved or removed. At **departure** the load is closed.
- Events follow the status order (pickup → departure → transit → arrival → release → delivery → receipt); no future dates or dates before the last event.
- Cargo cannot exceed a unit's nominal capacity. Each shipment arrives at a single plant.

## Tracking

For the internal team: the supplier role does not include it (it can be granted in its role).

Four boards. The first two share filters (brand, group, style, color, size, SKU, storage location, stage, load unit, BL/AWB, shipment, supplier, company, plant, late-arrival risk and ETA, XF and in-store date ranges), each downloadable as **PDF or Excel**:

- **Purchase orders:** releases, status, progress, XF overdue and margin against the port deadline; each PO opens into its **detail by SKU**.
- **Shipments and load units:** one row per shipment and transport document, opening into units and what each unit carries per PO.
- **Invoicing and packing lists:** which step each document is at and what is missing.
- **Estimated in-store date:** each PO, tracking row and lead-time row shows when the goods would be in store with the lead times of its origin: the actual arrival, the ETA or, without a shipment, the XF (or today, if it passed) plus the standard transit; then the port-to-warehouse, warehouse-entry and re-export days of its region. Next to it, how many days early or late it is against the requested in-store date. For a PO it is the date of the last goods still to arrive.
- **Lead times:** average days of each stage **by country of origin** (PO created → commercial release → logistics release → production and pickup → departure → transit to the destination port → port to warehouse → warehouse entry), the share of logistics releases on time against their target before the XF, pickup against XF and the slack at port. Each PO opens into its **milestones**, each with its target, its actual or estimated date and how many days early or late it is. Filters: period (POs created; last 12 months by default), origin, region and supplier.

**Early or late.** The in-store date is not compared with the port arrival: after the port the goods still have to reach the warehouse, be entered and be re-exported to the store. So each PO has a **port deadline** = in-store date − (port to warehouse + warehouse entry + re-export) days of its origin region, and the arrival (actual, the shipment ETA, or without shipment the XF plus the standard transit) is compared with it: late if after it, tight if less than 7 days to spare. Re-export is not recorded in the system yet; only its days are reserved. The targets per region (release before XF, XF to port arrival, port to warehouse, entry, re-export) are edited in *Master data → Lead time targets*, and each country is assigned a region in *Countries*.

## Commercial invoice and packing list (PDF and Excel)

Each invoice and packing list downloads as **PDF** (ready to print and sign) or **Excel**, following Central American customs requirements (CAUCA/RECAUCA and DUCA):

- **Parties:** exporter/seller, importer/bill to (company with tax ID) and consignee/notify party.
- **Terms:** number and date, incoterm, currency, payment terms, countries of origin and shipment, transport, ports, carrier and BL/AWB, containers and seals. Headers do not list purchase orders or destination centers (they would grow too long); **each line shows its PO and line**.
- **Detail:** PO and line, code and UPC, commercial description, **HS code (SAC)**, origin, quantity, unit, price and total. In the packing list, per carton group: range and number of cartons, contents per carton, **inner packs**, dimensions, net and gross weights, m³, pallet and label type.
- **Totals:** quantity per unit, packages, weights, volume, value, **amount in words** (“SAY: FOUR THOUSAND … US DOLLARS AND 00/100”), shipping marks and the signed exporter declaration.
- Until finalized, the PDF carries a **DRAFT · NOT OFFICIAL** watermark; every page shows “Page X of Y”.

## Main rules

**Everything is managed by quantities, with the same formula at each level:** available = quantity of the level above − what is assigned in active documents.

| Level | Assigned | Released by |
|---|---|---|
| PO line → invoice | partial or full quantity | removing the line, reducing the quantity or cancelling the invoice |
| Invoice line → packing list | partial or full, in one or several PLs | removing from the PL, reducing on the invoice or cancelling the PL |
| PL row → cartons | full, partial or mixed cartons | unpacking |

- **Reducing on the invoice** something already in a PL: the system shows which PLs hold it and releases what is not in cartons. Packed goods are never touched automatically.
- **Auto-pack:** one step for the whole PL, each row with its own template, following the casepack and inner pack rules.
- **Templates** only fill in data; each carton keeps its own values.
- **Partial cartons:** template dimensions, proportional net weight and gross = net + tare, flagged as estimated until confirmed.
- **Bulk changes** are all or nothing: if one row fails, none is applied and the failing row is explained.
- **Statuses:** Draft → Finalized; reopening moves to “Under correction” and asks for a reason.
- **Concurrency:** row locking when taking balance, a version per document (a stale edit is rejected), idempotency keys, and a history of every change with user, before/after and reason.

## Configurable rules

Environment variables (see `backend/app/config.py`):

| Variable | Default | What it does |
|---|---|---|
| `POSICION_EN_VARIAS_FACTURAS` | `0` | With `0`, a PO line lives in **one active invoice**; with `1` the balance can go to another invoice. |
| `FACTURA_EN_UNA_SOLA_UNIDAD` | `0` | With `1`, all PLs of an invoice must go on the same load unit. |
| `PROVEEDOR_PUEDE_FINALIZAR` | `1` | Whether suppliers can finalize their invoices and PLs. Reopening is always internal. |
| `REQUERIR_DATOS_ADUANA` | `1` | Requires country of origin and HS code per line to finalize. |
| `DIAS_ALERTA_BORRADOR` | `7` | Days after which a draft shows as an alert. |
| `DOS_PASOS` | `1` | Two-step verification by SMS for users that have it on. |
| `SESION_HORAS` / `SESION_INACTIVIDAD_MIN` | `12` / `30` | Session lifetime and inactivity timeout. |
| `INTENTOS_MAX` / `BLOQUEO_MIN` | `5` / `15` | Failed attempts before lockout and lockout minutes. |
| `CODIGO_VALIDEZ_MIN` / `CODIGO_REENVIO_SEG` | `5` / `30` | Code validity and wait before resending. |
| `SMS_PROVEEDOR` | `consola` | `consola` (server log) or `twilio` (with `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`). |
| `COOKIE_SEGURA` | `0` | Set to `1` behind HTTPS (Secure cookie and HSTS). |
| `PAIS_BASE_CLASIF` | `SV` | Country whose national code completes the suggested HS code. |
| `ANTHROPIC_API_KEY` / `CLAUDE_MODELO` | — | Enables the optional specialist opinion in *Products*. |

Other variables: `DATABASE_URL`, `SECRET_KEY` (change it in production), `SEED_DEMO`, `UPLOAD_DIR`, `CORS_ORIGINS`.

**Database:** demo and production run the same Alembic migrations at start-up and nothing is ever deleted. `SEED_DEMO=1` only adds sample data to an empty database; `SEED_DEMO=1 python -m app.seed` resets the demo. Production checklist: `docs/PRODUCCION.md`.

## Responsive layout

The interface adapts to large monitors, laptops, tablets and phones instead of only shrinking:

- **Filters:** on phones the search stays visible and the other filters and secondary actions open from a **Filters** button that shows how many are active (`v-filtros`).
- **Tables:** on tablets, columns marked secondary (`<th class="col-sec">`) are hidden; on phones each row becomes a **card** with the column name next to each value (`v-tarjetas`).
- **Header:** on phones the language, theme, password and sign-out move into the menu.
- **More options:** on phones, secondary actions (PDF and Excel downloads, uploads, reopen, cancel…) go into a **More options** menu, leaving the main action visible. *Master data* replaces its 16 tabs with a catalog selector.
- **Contextual:** filters with a single possible value (one company, one brand…) are not shown.

## My profile and preferences

Each user opens *My profile* from their name in the header (or the menu on phones) to:

- **Basic data:** edit their name; see their email, role, supplier and registered mobile (the administrator changes the mobile).
- **Password:** change it (their other sessions are closed).
- **Preferences**, saved in the profile and applied on every device:
  - **Language** (default English).
  - **Date format** (default **MM/DD/YYYY**; also DD/MM/YYYY, YYYY-MM-DD, DD-MMM-YYYY, MMM DD, YYYY). It is used **everywhere**: lists and documents on screen, the **date fields** (typed in that format or chosen in the calendar), the **PDF and Excel** files the server generates for the user, the **PO upload template** (its sample dates come in that format) and the **reading of uploaded files** (a date like 05/10/2026 is read with the user's day/month order; ISO dates and Excel date cells are always accepted).
  - **Time format** (12 or 24 hours) and **number format** (1,234.56 · 1.234,56 · 1 234,56 · 1'234.56).
  - **Theme** (light, dark or system), **rows per page** in the tables and **start page** after signing in.

## Languages

The interface is available in English, Spanish, Simplified Chinese, Hindi and Arabic (right-to-left). **English is the default for everyone**; each user picks a language in *My profile* (or with the globe selector in the header) and it is kept in their profile, so it follows them to any device.

- English text is the key; each language has its own dictionary in `frontend/src/i18n/` (`es.json`, `zh.json`, `hi.json`, `ar.json`). Translations are adapted to the business, not literal: `glosario.json` fixes the approved term for each concept (e.g. *Type* → *Tipo*, never *Chico*) and lists the literal translations that are not accepted.
- `backend/tests/test_i18n.py` checks every language: all texts present, the same `{0}` placeholders, written in the language's own script, glossary terms respected, and `claves.json` up to date with the code.
- After changing interface texts run `node frontend/scripts/i18n-extraer.mjs` (and `python backend/scripts/i18n_extraer.py` for server messages), then add the new translations.
- Official texts stay as published: SAC descriptions and the customs description are in Spanish, and trade documents (invoice, packing list) are in English.

## Tests

```bash
cd backend
pytest                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/tests pytest   # PostgreSQL (includes concurrency)
```

## Structure

```
backend/app/
  config.py          configurable rules and security settings
  models.py          data model
  services/          business logic (quantities, invoices, packing, transport, import, access, SMS, suggestions,
                     products and classification, specialist opinion)
  data/              base of national tariff codes, SAC texts and the seed catalog of the engine (categories, attributes, sheet rules)
  routers/           REST endpoints under /api
backend/tests/       full flow, classification engine (end to end, parity fixtures in tests/paridad), packing rules, secure access and concurrency
frontend/src/
  views/             Home, Orders, Invoices, Invoice, Packing list, Shipments, Shipment, Products, Product, Tracking,
                     and under Settings: Master data, Templates, Import, Users
  clasificacion/     calls to the classification engine (/clasificacion/sesion) and code formatting (no classification logic)
  components/        icons, steps, SVG charts, bulk action bar, modals, statuses, destinations and load units
  stores/            session, invoicing selection, notices
```

## Before going to production

See **[docs/PRODUCCION.md](docs/PRODUCCION.md)**: required variables (`SECRET_KEY`, `DATABASE_URL`, SMS, first administrator), what is configured inside the app, first start, updates and backups.
