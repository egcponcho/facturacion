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
- **Users** (*Users and suppliers*, administrator): each user has a registered mobile in international format (`+50370001234`) and two-step verification on or off.

To send real SMS set `SMS_PROVEEDOR=twilio` with `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM`. With the default `consola` provider the message goes to the server log, and only in demo mode (`SEED_DEMO=1`) is the code also shown on screen.

## 5-minute tour

The demo data already has history: invoices from past months, a received container, another in transit and an invoice ready to ship.

1. Sign in as **tnf@demo.com** (one click on “The North Face”, then enter the code shown). **Home** shows what is left to invoice, pack and finalize, where the goods are and the shipments on the way.
2. In *Purchase orders*, on PO 4400003845 click **Invoice** (or open it and change “To invoice” to take only part; several POs can be combined). Review and click **Create invoice**.
3. In the invoice, the steps at the top say what is missing. Click **Pack pending**: it creates the packing list with everything and opens it.
4. In *To pack*, click **Auto-pack**. Lines with a casepack are packed with that exact quantity per carton, lines with an inner pack in whole inner packs, and the rest with the suggested template. The remainder that does not fill a carton goes to a partial carton with estimated weight (or stays unpacked).
5. In *Review*, check the contents **by destination** and the **suggested load units**, **Confirm estimates** and **Finalize packing list**. Back in the invoice, enter number and date and click **Finalize**.
6. Sign in as **interno@demo.com**, open *Shipments* → EMB-0003, choose 40HC #1 and click **Assign cargo**: the panel suggests the load units for the selected volume and weight. Assign it; what is already finalized is confirmed in the same step. Then **Record departure**.
7. Open **Products** (as interno@demo.com). *Ready to approve* has the Vans Authentic White: the classification panel shows the suggested HS code 6404.19, why, and the national code for each destination country. Click **Approve**. From then on its PO lines show 6404.19.90.00 (El Salvador) and invoices take it automatically. As tnf@demo.com, the *Summit blue* jacket was returned with notes: fill in the outer fabric composition and save it; it goes back to review.
8. *Tracking* shows each PO (and, when opened, each SKU by stage), and each shipment with its units, with the margin against the in-store date. Everything downloads as PDF or Excel. *Master data* holds all catalogs.

## Item data vs. PO line data

| Item (master data, *Master data → Items*) | PO line (purchase data, comes in the PO file) |
|---|---|
| SKU, style, color, size / prepack ID, description | PO number and line, company, plant, storage location |
| Brand, group (category → packing rule), supplier | Destination center (country), port of loading, countries of origin and shipment |
| Type (solid or prepack), unit of measure (PAR, UN, CJ) | Quantity, unit price, currency, incoterm |
| Item code (11 digits starting with 3) and supplier SKU | XF dates, in-store date, commercial and logistics release |
| UPC | |
| Prepack breakdown (sizes per master carton) | **Casepack** and **inner pack** (the purchase packing) |

The item has no casepack: it is set on each PO line, because the same item can be bought in different packs. In *Purchase orders* the line table groups the columns as “Item · master data” and “PO line · purchase data”, and the internal team can edit a line's casepack and inner pack while it is not invoiced.

The HS code, the country of origin, the product type and the description are not typed on the item: they come from the **product's technical sheet** (next section), shared by all its sizes. The item group sets the packing rule; it does not define the product type.

## Products: technical sheet and tariff classification

The **item code** has 11 digits starting with 3: the first 8 are the **generic** (style-color) and the last 3 the size, for solids and prepacks alike (e.g. 30095125001 is size 7 of generic 30095125; 30095125007 is its prepack AB12). A **product** is a generic: its sizes and prepacks share one technical sheet and one classification. A generic is created once with its master data (*Master data → Items → New generic*) and then only sizes are added, each with its own size code (generated as the next free one, or typed), UPC and supplier SKU. Sizes can be entered as ranges with gaps (e.g. `7-10, 12, 14`) and are shown the same way ("7 to 10, 12, 14"). *Master data → Items* shows one row per generic by default (**Compact**), expandable to its sizes and prepacks like the lines of an order, where the generic is edited once for all its sizes; **List** shows one row per item code. A prepack keeps the generic of its solids and only changes the last 3 digits.

- **Technical sheet**: product type, gender, who it is for, use, size range, country of origin, composition by part (outer fabric, lining, upper, sole…), the features that change the code (only those are asked), photos and the customs description in Spanish for the DUCA (built from the sheet, or written by hand).
- **Classification engine**: runs in the browser while the sheet is edited. It applies the Harmonized System 2022 rules (GRI, section and chapter notes) for clothing, footwear, bags and accessories, learns from what was already approved and returns the 6-digit SAC subheading, its confidence, the reasoning, alternatives and inconsistencies to check.
- **National codes by destination**: GT, SV and HN use 10 digits; NI, CR and PA 12. They come from a base of national codes with conditions (gender, age, use, CIF value…). When a country splits the subheading further, the sheet asks only for that data. The internal team can set a code by hand and **remember** it for similar products.
- **Flow**: the supplier completes the sheet → *To review* → the internal team **approves** (or chooses another code) or **returns** it with notes. Approved sheets are locked; a change opens a **new version**, and the previous one stays in the history with its code and dates.
- **Where it is used**: each PO line shows the code for its destination country; invoice lines take the code, origin and customs description from the approved sheet (they are not typed on the invoice). An invoice cannot be finalized while a product is not classified; the message links to its sheet.
- **Specialist opinion (optional)**: with `ANTHROPIC_API_KEY`, the internal team can ask Claude for a second opinion with the sheet and up to two photos. It never approves anything.
- **Two descriptions**, both built from the sheet and editable: the technical one in Spanish for the DUCA, and a simple commercial one — product type and brand, e.g. *CALZADO VANS* or *CHAQUETA THE NORTH FACE* — used on the invoice and the packing list.
- **Prepacks are not classified**: they are built from solids and take the product and HS code of their solids.
- The sheet downloads as **PDF**, and the product list as Excel or PDF.

## Tariff schedule

*Products → Tariff schedule* (internal team) shows and edits everything the engine uses:

- **Countries**: each destination with the digits of its national code (GT/SV/HN 10, NI/CR/PA 12 by default), whether it belongs to the Central American Common Market and its tax. New countries can be added; an inactive country is no longer asked for in the sheets.
- **SAC headings and subheadings** (4 and 6 digits) with their official text, editable.
- **National codes** of every country with their duty and the conditions that select them (gender, age, CIF value, use, footwear style…). Filter by one or several countries, chapters and sources, edit inline, delete in bulk, and export to Excel or PDF with the filters applied.
- **Upload from Excel**: a template per country with the conditions as drop-down columns; a file can update codes or replace a country's whole tariff.

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
- **Items:** numeric SKU (e.g. `30095120001`), style, color, size, brand, group and **unit of measure**. Solids are created here, manually or with `plantilla_articulos.csv`.
- **Prepacks:** an item with its own product code, a **prepack ID** (its size, e.g. `AB12`) and a fixed **breakdown** built only from solids of the same style and color. The breakdown can be viewed everywhere but never changed. Bulk load with `plantilla_prepacks.csv`.

## Purchase orders

- 10-digit number starting with **44**; lines in steps of 10.
- Each line's **SKU** must exist in the item master, belong to the PO supplier, and the supplier must work with the PO company.
- **Storage location per line:** the same PO can send each line to a different storage location of the same company.
- **Releases (two teams):** **commercial** is `P` (pending) or `C` (released; empty means C). **Logistics** is **304** not released, **300** released or **301** released with later changes. Only **C and 300/301** can be invoiced.

### Importing POs

In *Import POs* (internal team) upload the SAP Excel or CSV. A preview shows what is new, changed, unchanged, conflicts and errors; nothing is saved until confirmed. Conflicts (e.g. a quantity below what is invoiced, or a casepack/inner pack change on an invoiced line) are not applied and appear as alerts.

Required columns: `supplier, po, po_line, sku, quantity, unit_price, currency, company, plant, destination`. Optional: `storage_location, incoterm, po_date, port_of_loading, country_of_origin, country_of_shipment, xf_date_original, xf_date, in_store_date, commercial_release, logistics_release, uom, casepack, inner_pack`. The previous Spanish column names and common aliases (`vendor`, `material`, `qty`…) are still accepted. See `plantilla_oc.csv`.

Codes are kept as text to preserve leading zeros; format those columns as text in Excel before exporting.

## Shipments

- **Everything follows the mode:** an ocean shipment only offers sea ports, shipping lines and containers; air, airports, airlines and air waybills; road, borders, road carriers and trucks. The **service belongs to each unit**, so an ocean shipment can be FCL, LCL or mixed.
- While **planned**, units and cargo can be added, confirmed, moved or removed. At **departure** the load is closed.
- Events follow the status order (pickup → departure → transit → arrival → release → delivery → receipt); no future dates or dates before the last event.
- Cargo cannot exceed a unit's nominal capacity. Each shipment arrives at a single plant.

## Tracking

Three boards with shared filters (brand, group, style, color, size, SKU, storage location, stage, load unit, BL/AWB, shipment, supplier, company, plant, late-arrival risk and ETA, XF and in-store date ranges), each downloadable as **PDF or Excel**:

- **Purchase orders:** releases, status, progress, XF overdue and margin against the in-store date; each PO opens into its **detail by SKU**.
- **Shipments and load units:** one row per shipment and transport document, opening into units and what each unit carries per PO.
- **Invoicing and packing lists:** which step each document is at and what is missing.

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

**Database reset:** in demo mode (`SEED_DEMO=1`) the database is wiped and re-seeded when the schema version changes (`ESQUEMA_VERSION` in `config.py`). In production (`SEED_DEMO=0`) nothing is ever deleted.

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
  data/              base of national tariff codes, SAC texts and the engine vocabulary
  routers/           REST endpoints under /api
backend/tests/       full flow, packing rules, secure access and concurrency
frontend/src/
  views/             Home, Orders, Invoices, Invoice, Packing list, Shipments, Shipment, Products, Product, Tracking,
                     and under Settings: Master data, Templates, Import, Users
  clasificacion/     tariff classification engine (pure logic) and its bridge to the API
  components/        icons, steps, SVG charts, bulk action bar, modals, statuses, destinations and load units
  stores/            session, invoicing selection, notices
```

## Before going to production

- Use **Alembic** migrations instead of `create_all` and set `SEED_DEMO=0`.
- Change `SECRET_KEY`, set `COOKIE_SEGURA=1` and configure a real SMS provider.
- Serve attachments from object storage instead of local disk.
