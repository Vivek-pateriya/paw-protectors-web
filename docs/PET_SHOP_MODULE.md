# Pet Shop — implementation and verification

Approved and implemented on 2 November 2026. React JS and React Native use the same workspace-root FastAPI service and PostgreSQL database. Legacy `android/` and `github-ready/paw-protectors-android/` are unchanged. Shop buyer phone checks passed on 3 November 2026; admin forms/picker and vet-specific UI acceptance remain pending. See PHONE_ACCEPTANCE_2026-11-03.md.

## Access and scope

| Role | Access |
| --- | --- |
| Owner | Browse published products, manage own shared cart, place orders, view own order details/history, cancel own placed orders |
| Veterinarian | Same purchasing access as an owner |
| Administrator | Manage categories/products/photos/publication and stock, review all orders, confirm/ship/deliver orders, cancel placed or confirmed orders |

Only administrators sell products. Owners cannot publish shop listings. Adoption remains a separate module with owner submissions and admin approval.

Products have a category, unique SKU, name, description, integer-paise INR price, stock, low-stock threshold, publication flag and authenticated JPEG/PNG photo (maximum 5 MB). Archiving a category hides its products from buyers. Product and category edits use revision checks; stock adjustments require a recorded reason. Administrators can filter products at or below their stock threshold.

Checkout supports **INR, cash on delivery and free delivery**. Online payments, coupons, returns and seller accounts are outside this implementation. There is no courier integration; the admin may record a tracking reference when marking an order shipped.

## Buyer and admin workflow

1. Admin opens Pet Shop → Categories, creates an active category, then Inventory → Add product. Save the product before adding its photo. Set publication to published and provide stock.
2. Owner or vet opens Pet Shop, filters/browses products and adds products to the cart. The cart belongs to the account and is shared between the website and mobile client. Refresh after changes made in the other client.
3. Checkout displays the current total and collects recipient, phone, address, city, state and six-digit PIN code. A cart supports up to 50 different products, with 1–99 units of each. Adding to the cart does not reserve stock.
4. Successful checkout reserves stock atomically and stores immutable product names, SKUs, quantities and prices in the order. Admin processes **placed → confirmed → shipped → delivered**. Marking delivered explicitly confirms delivery and cash collection; payment becomes collected only at that point.
5. Buyers may cancel while placed. Admin may cancel while placed or confirmed. A reason is required, stock is restored once, and the order/history remain available. Orders cannot be cancelled after shipment in this version.

Buyers and active administrators receive order notifications through the existing notification centre. List responses omit delivery addresses and phone numbers; authorized order detail is available only to the buyer and administrators.

## Transactions and integrity

- Migration `database/006_shop.sql` adds eight shop tables and extends existing notifications. There are now 25 public tables, with migrations 1–6 applied.
- Backend prices are integer paise; product prices range from ₹0.01 to ₹10,00,000. Totals are calculated by the server and compared against the reviewed checkout total. Price changes require a refresh and review.
- Cart and order rows are locked before mutation. Checkout locks products in ascending ID order, rechecks publication/category availability and stock, and decrements inventory inside one transaction. Competing buyers cannot reserve the same final unit.
- A per-user UUID and request hash make retries of the same checkout return the existing order. Reusing that UUID for another payload returns a conflict. Changed cart/product/order versions return a conflict instead of overwriting another client's work.
- Orders, stock movements, item snapshots, history and notifications commit together. A notification failure rolls back the checkout. Cancellation status/version checks and a unique stock-movement index prevent duplicate restoration.
- Product/category/order changes appear in the existing admin audit. Customer contact details are included in authorized order records and admin audit data; protect database backups accordingly. Uploaded files need a separate backup from PostgreSQL.

## Common backend and clients

Start the shared backend from the workspace root with `powershell -ExecutionPolicy Bypass -File scripts/run.ps1`. Startup applies missing migrations without replacing existing accounts or seeding new records. The client launchers also use the root backend.

- React JS: `http://127.0.0.1:8000/app` → Pet Shop. Admin dashboard includes shop counters and a management shortcut.
- React Native: Home or Account → Pet Shop; administrators also have a Shop management entry. The built ARM64 APK is `github-ready/paw-protectors-react-native/artifacts/PawProtectors-RN.apk`. It was built during implementation and installed with data preserved for phone acceptance on 3 November.
- Common API: `/shop/categories`, `/shop/products`, `/shop/products/{id}`, `/shop/products/{id}/stock`, `/shop/products/{id}/image`, `/shop/cart`, `/shop/cart/items/{id}`, `/shop/checkout`, `/shop/orders`, `/shop/orders/{id}`, `/shop/orders/{id}/decision`. See `/docs` for request schemas and methods.
- Source: `backend/shop.py`, `backend/shop_models.py`, React JS `website/src/ShopPage.jsx` in the web client, and React Native `src/ShopScreen.tsx` / `src/shop.ts`.

No sample shop orders or catalogue products were inserted into the application database. Acceptance records were created only in disposable test schemas. An admin must create the real catalogue.

## Verification

- **42 backend tests passed**, including eight Shop tests: permissions, protected photos, publication, stale versions, shared carts, changing prices, private order details, immutable snapshots, duplicate checkout/cancellation, concurrent final-unit purchases, COD transitions, stock audit and transaction rollback. Existing authentication, adoption, care and booking checks also passed. Evidence: `artifacts/shop-full-tests.xml`.
- **22 React Native client tests passed**, plus TypeScript checking. Real TypeScript API integration passed against isolated PostgreSQL, including catalogue/photo/cart/checkout/orders/notifications and the existing 100-way booking race (one success, 99 conflicts). Evidence: React Native `artifacts/backend-integration.json`.
- React JS production build and React Native ARM64 APK build passed. Mobile native build evidence: React Native `artifacts/shop-native-build.log`.
- Browser acceptance passed with synthetic admin/owner accounts: category/product publication, ₹123.45 pricing, product photo upload/display, quantity-two checkout at ₹246.90, confirmation/shipping/delivery/cash collection, buyer cancellation and stock restoration. Neither browser recorded warnings or errors during these flows. Screenshots: `artifacts/shop-ui/`.
- The existing application database was backed up before migration. Original-column row fingerprints match the restored pre-migration backup for all 16 preexisting data tables (schema version metadata excluded). Backup/restore passed for all 25 current public tables. Evidence: `artifacts/shop-migration-verification.json` and `artifacts/backup-restore.json`.
- **Phone, 3 November:** actual buyer catalogue/photo display, cart quantity, COD checkout, cancellation/reason validation, order history/status refresh, saved session and notification Mark read passed. Admin setup and delivery transitions were API-assisted. Shop admin forms, picker/upload and vet-specific UI remain pending. Evidence: `artifacts/shop-phone-20261103/verification.json`.

The report and presentation dated 3 November include Pet Shop and the actual phone evidence: `docs/reports/Paw_Protectors_Project_Report_2026-11-03.pdf` and `docs/presentations/Paw_Protectors_Project_Presentation_2026-11-03.pptx`. The earlier dated files remain historical checkpoints.
