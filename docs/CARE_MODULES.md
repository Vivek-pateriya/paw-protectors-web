# Partial-module implementation — 31 October 2026

The six existing business modules have been extended in this order: authentication, pet profiles, veterinary appointments, medication/reminders, administration, and notifications/reports. Adoption and Pet Shop/Orders have not been implemented; those require the owner's next decision.

## Authentication

- My account → Edit my profile changes the user's name and normalized login email after verifying the current password. Users cannot change their own role or activation status.
- My account → Change password checks the current password and confirms the new password in the client. Existing sessions are invalidated; the current device receives a replacement session.
- Forgot password accepts an account email and always returns the same eligibility message. Each code has 256 bits of randomness, expires after 15 minutes, and can be used once. The database stores only its SHA-256 hash. Resetting the password invalidates existing sessions, including background-worker sessions.
- Recovery requests have an IP-based limit of ten per hour and an account cooldown of one minute. The API never returns recovery codes or reveals whether an email exists. Inactive accounts cannot recover.
- Changing a login email invalidates outstanding recovery codes and other sessions. Unchanged-name/email profile updates preserve session compatibility.

### Local recovery mailbox and real email

The local academic setup uses `RECOVERY_DELIVERY=local`. Messages are `.eml` files in `artifacts/private-mailbox/`, outside the public website and excluded from Git. The laptop operator opens the newest message addressed to the account and supplies its recovery code to the account owner. Paste the code into Enter recovery code and choose a new password. This is a private development mailbox, not external email delivery. Do not publish or share the mailbox or backups containing account information.

For real delivery, set `RECOVERY_DELIVERY=smtp`, `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_FROM`, and, when needed, `SMTP_USER`/`SMTP_PASSWORD` in the private `.env`. SMTP requires STARTTLS and certificate validation. No external email was sent as part of implementation. Delivery failures are logged without tokens, addresses, or SMTP credentials; the public response stays generic. Real SMTP delivery needs the owner's configured service and a delivery check.

## Pet profiles

Add/edit/view now includes nullable `weight_kg` (greater than zero and at most 2000 kg, stored to three decimal places) and separate `allergies` text. Omitting these fields from older client requests preserves their existing values; explicitly supplying null/empty clears them. Existing profiles start with no recorded weight or allergies. They are never inferred from notes.

## Appointments and medication

Booking creates an immediate booking notification and a reminder 24 hours before the visit, or immediately when booked inside that window. Cancellation/completion creates its own status notification and cancels the pending visit reminder. Database triggers run in the booking transaction, so failed bookings do not leave notifications behind. Existing future bookings receive a reminder during migration, without fabricated historical booking events.

Pet profile → Medication schedules records the medication name, prescribed dose, instructions, first/last dose timestamps and hours between doses. Schedules are finite (up to 366 days, interval 1–720 hours) and create one reminder per occurrence. Timestamps must include a timezone in mobile/Java forms; websites convert the local datetime picker values to timezone-aware timestamps. Stop reminders cancels outstanding reminders and retains the schedule and acknowledged history. Owners, administrators and veterinarians with an assigned-pet relationship have the same scope enforced by the existing clinical-access checks.

## Notification centre and reports

The notification centre displays vaccination, medication and appointment notifications, including planned future entries, with separate read and acknowledged states. It supports unread filtering and pages of 100 records. Mark read preserves the reminder; Mark done acknowledges it. Cancelled reminders are excluded. Access is always scoped to the signed-in recipient, including for administrators.

Activity reports support an inclusive UTC date range of at most 366 days. Owners and veterinarians see only their own recorded activity; administrators see community activity and may filter a specific actor through the API. Reports include registrations, successful logins/logouts, and committed changes grouped by module/action and user, with CSV download on websites and CSV sharing on mobile/Java. CSV values are escaped against spreadsheet formula interpretation. Earlier activity exists only where the earlier project already recorded an audit; historical events are not fabricated. New auditing covers vaccination/clinical records, veterinarians, slots and medication schedules as well as the existing user/pet/appointment audits.

Product/inventory and adoption-request administration and their notifications remain dependent on the two deferred modules. Google Maps, general document/certificate storage, and cloud/server-push synchronization remain separate scope decisions, rather than being silently represented as completed.

## API additions

| Endpoint | Purpose |
|---|---|
| `PUT /auth/profile` | Self-service name/email update with current password |
| `POST /auth/change-password` | Authenticated password change and session replacement |
| `POST /auth/forgot-password` | Generic, throttled recovery request |
| `POST /auth/reset-password` | Consume a single-use recovery code |
| `GET/POST /pets/{id}/medications` | List/create finite medication schedules |
| `POST /pets/{id}/medications/{schedule}/stop` | Stop the schedule's outstanding reminders |
| `GET /notifications?read=false&offset=0` | Recipient-scoped notification history |
| `POST /notifications/{id}/read` | Mark a notification read |
| `GET /reports/activity?start=YYYY-MM-DD&end=YYYY-MM-DD` | Permission-scoped activity report |
| `GET /reports/activity?format=csv` | CSV export with the same scope/date rules |

## Running and validation

Run the normal setup/migration scripts before restarting an older backend. Migrations 003 and 004 preserve accounts, password hashes, pets, bookings and history. On the original laptop, an application backup was saved as `artifacts/before-partial-modules-20261031.dump` before these migrations were applied.

The active React Native client, plain shared-backend website, separate React website and preserved Java Android clients expose the additions. Both exported backend folders carry the same models, security logic, routes and migrations while retaining their original frontend separation.

The React Native Android build helper now targets `arm64-v8a` by default; use `-Architectures 'armeabi-v7a,arm64-v8a,x86,x86_64'` for additional ABIs. It preserves native edits, uses two Gradle workers, aligns the stale wrapper with the installed AGP 8.12/Kotlin 2.1 toolchain, and stages generated C++ objects in a shorter project-local path. These choices follow [AGP 8.12 compatibility](https://developer.android.com/build/releases/agp-8-12-0-release-notes), [Android CMake staging](https://developer.android.com/reference/tools/gradle-api/8.12/com/android/build/api/dsl/Cmake), and [CMake object-path handling](https://cmake.org/cmake/help/latest/variable/CMAKE_OBJECT_PATH_MAX.html).

Background workers deliver due vaccination, medication and appointment reminders instead of sending scheduled doses early. They require API reachability, notification permission and a custom Android build. Android controls execution timing; this is not an exact alarm or FCM/cloud-push implementation. The phone became available near the end of the session and the standalone APK was installed successfully. The owner then explicitly chose to leave device checks pending, so real-device gallery, native bridge runtime and background-notification acceptance must not be described as verified.

### Recorded verification

Latest phone update: basic login/navigation, pet weight/allergy display and the native OS bridge now passed on the I2221. Remaining phone workflows were paused by the user. See [phone acceptance details](PHONE_ACCEPTANCE.md); the earlier pending-device statement above describes the initial implementation checkpoint.

- Shared backend: 25 tests passed; separate web and Android backend deliveries: 26 each, no failures or skips. These include a populated version-2 migration test and the existing 100-client booking race.
- React Native: TypeScript and all 15 client tests passed; Android production bundling and the standalone ARM64 release build passed. The OS module's optimized class is present in the packaged DEX, verified using the R8 mapping.
- Both Java Android deliveries: APK builds, JVM tests and lint passed, with zero lint errors. Legacy dependency metadata/deprecation warnings remain in the build logs.
- Backup/restore: source/restored row counts matched for all 14 public tables.
- Browser: synthetic owner login, name editing with current-password verification, recovery request/forms, medication schedule creation, notification read persistence, activity report rendering and CSV download passed. No browser warning/error logs were observed. The disposable preview schema was removed afterward.
- Shared local API restarted with the final routes and returned healthy PostgreSQL status.

Evidence: `artifacts/partial-modules-verification.json`, the corresponding JUnit XML/build logs, and `artifacts/partial-modules-ui/` in the shared workspace. Standalone APK: `github-ready/paw-protectors-react-native/artifacts/PawProtectors-RN.apk`. This remains a local demonstration build; publishing requires a private release key.

Regression coverage includes a populated version-2 database upgrade, credential/session protections and concurrent recovery-code consumption, medication occurrences/cancellation, notification ownership/read status, date/report access controls and CSV safety, in addition to the original booking/concurrency suite. From the shared PET-SHOP workspace, browser checks use `python -m scripts.preview_modules`, which creates a disposable schema and synthetic accounts rather than editing application records. Stop it with Ctrl+C to remove that schema.
