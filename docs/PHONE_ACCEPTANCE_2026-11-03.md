# Pet Shop phone acceptance — 3 November 2026

Tested the React Native `org.pawprotectors.reactnative` standalone APK on the connected I2221 phone. Both active clients continue using one common FastAPI/PostgreSQL backend, reached over USB reverse port 8000. The current Shop APK installed successfully with `-r`; app data was preserved. Existing synthetic QA credentials were used without changing any user's password or role.

## Passed on the phone

- Login, dashboard and Account → Pet Shop navigation.
- Published catalogue, INR 123.45 unit price, stock display and authenticated product photo rendering. The image was the app-icon fixture, not a personal photo.
- Product detail, Add to cart and quantity increase to two items. The phone displayed INR 246.90, COD and free delivery.
- Checkout form entry, keyboard dismissal/scrolling with values retained, and order placement from the actual phone.
- Cancellation form blocks an empty reason. A synthetic reason allowed cancellation from the phone. The backend confirmed stock changed **5 → 3 → 5**, with one cancellation movement for the two units.
- My orders shows cancelled and delivered orders, their amounts and payment states.
- Delivered-order detail shows tracking and retained placed/confirmed/shipped/delivered history. No cancellation control is offered after delivery.
- Saved login restoration after force-stopping and reopening Paw Protectors.
- Notification centre shows Shop order events. Mark read on the delivered-order notification changed its state to Read.
- Current-process filtered ReactNativeJS/AndroidRuntime error log contained zero error entries. This is a bounded check of those tags, not a claim that all native warnings or workflows are absent.

## API-assisted checks and test data

An administrator created one clearly marked synthetic category/product and uploaded the app-icon photo through the common API. **Order 1** was created and cancelled through the phone UI, at 2 × INR 123.45 = INR 246.90.

**Order 2** was created with the synthetic buyer through the API, then advanced by the admin API through confirm, ship and deliver. The phone refreshed and visibly showed delivered/payment collected, tracking and history. Admin status controls were not exercised on the phone in this run. No actual sale, shipment, delivery or cash collection occurred.

The QA category was archived after testing, removing it from the buyer catalogue. The two synthetic orders and inventory/audit history remain intentionally available as test evidence. Existing real pets, accounts, clinical records and passwords were not changed. Legacy Java source/configuration files remain unchanged.

## Remaining phone acceptance

- Shop admin category/product editing, stock adjustment and product-photo picker/upload on the phone.
- Vet-specific Shop UI acceptance (backend/client API role coverage already passed).
- Full Adoption admin approval, application, reservation and handover; Adoption-specific picker upload.
- Appointment and medication write flows; natural background timing/battery behaviour; cancellation of an active native OS worker run.

Earlier acceptance is retained in `PHONE_ACCEPTANCE.md` and `PHONE_ACCEPTANCE_2026-11-02.md`; those dated records describe earlier checkpoints. Earlier pet photo upload/display and forced reminder delivery remain passed, without implying natural background timing was verified.

Evidence: `artifacts/shop-phone-20261103/verification.json`, `backend-check.json`, `filtered-errors.log`, and the synthetic `catalogue.png`, `cart.png`, `placed-order.png`, `cancelled-order.png`, `order-list.png`, `order-history.png` and `notifications.png` screenshots. The updated academic report includes actual phone catalogue/order-list captures; slide 20 includes the catalogue capture.
