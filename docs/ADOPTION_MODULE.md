# Adoption module — 2 November 2026

Implemented in the **React JS client, React Native client and common FastAPI/PostgreSQL backend**. Legacy Java folders were not changed. Phone testing and installation of this updated APK are deferred at the owner's request.

## Using it

Open the React JS website at **http://127.0.0.1:8000/app** with the common backend running. React Native uses the same API address and database. Adoption is available from the React JS navigation and from React Native Home/Account; administrators also have an adoption-management entry.

From the shared workspace, `powershell -ExecutionPolicy Bypass -File github-ready/paw-protectors-web/scripts/run.ps1` starts/reuses the common backend. It does not start the old copied web backend or a separate database. If an older API is already running, stop that instance and rerun the command. Build the website with `npm run build` in `github-ready/paw-protectors-web/website/`; development/preview requests proxy to the common service on port 8000.

The React Native APK for later device testing is `github-ready/paw-protectors-react-native/artifacts/PawProtectors-RN.apk`. This is a local demonstration build, not a privately release-signed distribution.

## Permissions

| Action | Owner | Admin | Vet |
|---|---|---|---|
| Browse published animals and photos | Yes | Yes | Yes |
| Submit an animal | Yes, pending review | Yes, published directly | No |
| Edit/manage own eligible listing | Yes | All listings | No |
| Approve/reject publication | No | Yes | No |
| Apply to adopt | Yes, except own listings | No | No |
| Read application answers/contact details | Own applications | All applications | No |
| Approve/reject applications and confirm handover | No | Yes | No |
| Withdraw an application | Own active applications | Only if the admin is its applicant; admins cannot impersonate applicants | No |

An owner account does not need an existing pet to apply. Listing submitters receive status notifications and application counts; being the submitter does not reveal other applicants' private answers or contact details.

## Listing workflow

1. An owner selects **List an animal**, enters name/species/breed/age/gender, location, description and optional health summary, weight/allergies, then submits.
2. The listing is **pending review**, visible to its submitter and administrators. It is absent from other users' browse results and its photo cannot be retrieved by them.
3. An administrator selects **Listing approvals**, inspects the submission and publishes or rejects it with a reason.
4. A rejected listing may be edited and resubmitted. Editing a published owner listing or changing its photo also returns it to review.
5. Edits are blocked while active applications exist. Reserved/adopted/archived listings cannot be edited. Archiving an eligible listing closes pending applications and preserves history. Resolve a reservation before archiving.

Listings support JPEG/PNG photos up to 5 MB, authenticated retrieval, search by name/breed/description, species/location/maximum-age filters, status filters and pagination. Version checks stop an administrator from approving an older revision after its owner changes the submission.

## Application and handover workflow

**Available → application pending → approved/reserved → handover confirmed → adopted/completed.**

Applicants supply their adoption interest, home type, other-pet information, optional care experience and contact phone. They track decisions/history under **My applications** and may withdraw pending or approved applications. Only one active application per person/listing is allowed; past requests remain in history and a new request can be submitted later when the listing is available.

Admin approval reserves the listing for one applicant. Other applications remain pending while handover is arranged. Withdrawal or rejection of the approved application releases the reservation. After physical handover, the administrator explicitly confirms completion. The transaction creates exactly one new pet profile for the adopter, preserves the listing's approved photo/summary/weight/allergies, marks the listing adopted and application completed, and closes the other pending applications.

Adoption listings are separate from existing owned-pet records. The module does not silently transfer or delete existing pet profiles, appointments, vaccinations or clinician-authored records. A new adopted profile starts with the listing's summary, not fabricated clinical history. Completed records are retained; the adoption relationship also guards deletion of the adopted profile.

## Common backend and database

Migration `database/005_adoption.sql` adds:

- `adoption_listings`: submitter, content/photo, publication state, revision, reservation and adopted-profile reference.
- `adoption_applications`: applicant, private form answers, status and decision note.
- `adoption_history`: timestamped listing/application transitions with actor IDs and reasons.
- Recipient-scoped adoption notification references in the existing reminders table.
- Foreign keys, status/source constraints, indexed browse/review/history queries, a unique active-request index and a unique reserved/completed-winner index.

Listing locks are acquired **before** reading application counts, so counts use a fresh database snapshot after any lock wait. All related changes—reservation/handover, pet creation, closing competing requests, history, audit and notification inserts—commit or roll back together. Concurrent approvals cannot select two adopters; concurrent completion cannot create two profiles. Stale reviews, duplicate active requests and attempts to mutate closed records return conflicts.

### Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /adoption/listings` | Published browse, own listings or admin review; filters and pagination |
| `POST /adoption/listings` | Owner submission/admin creation |
| `GET/PUT /adoption/listings/{id}` | Authorized detail and versioned editing |
| `POST /adoption/listings/{id}/review` | Publish, reject or archive with revision checks |
| `GET/POST /adoption/listings/{id}/image` | Authorized photo retrieval/upload |
| `POST /adoption/listings/{id}/applications` | Owner application |
| `GET /adoption/applications` | Personal or admin application review with filters |
| `GET /adoption/applications/{id}` | Applicant/admin detail and history |
| `POST /adoption/applications/{id}/decision` | Approve, reject, withdraw or confirm handover |

Notifications cover submissions, publication/rejection and application decisions. Existing notification read/acknowledgement interfaces and background-worker code consume them. This verifies stored events and web display; actual phone background delivery remains untested. Adoption audit events appear in existing personal/admin activity reports, and the admin dashboard includes adoption counters. No external email/SMS or new cloud service is introduced.

## Verification and deployment

- Backend integration/regression tests run in disposable PostgreSQL schemas, including upgrade preservation, role/privacy enforcement, reapproval, duplicate requests, competing approvals/completions, edit/application races, rollback after a simulated notification failure and safe retries.
- The actual TypeScript API client exercised owner moderation, authenticated adoption-photo transport, application privacy, reservation/handover, inherited pet/photo and notifications/reports against the common backend in an isolated schema. Its existing 100-client booking race still produced one success and 99 conflicts.
- React JS browser checks used synthetic owner/admin/adopter accounts: submission, pending-review visibility, publication, application tracking, reservation, handover, adopted profile, upload, rejection/resubmission and search. The list/detail state transition was corrected and retested in both clients' code.
- React Native TypeScript/client tests, production bundle and APK build passed. No phone was connected, queried, installed to or tested during this implementation.
- Before application migration, a backup was saved to `artifacts/before-adoption-20261102.dump`. Fingerprints confirmed existing users, pets, appointments and clinical/vaccination records were unchanged. Backup/restore matched all **17 public tables**.

Evidence: `artifacts/adoption-tests.xml`, `artifacts/adoption-verification.json`, `artifacts/adoption-ui/`, and React Native `artifacts/backend-integration.json` / `artifacts/adoption-native-build.log`. Upload files need a separate filesystem backup, as with existing pet photos.

The old copied backend under the web delivery is retained as a historical export. The active clients use workspace-root `backend/` and `database/`; the module is not maintained as another independent backend copy. Pet Shop/Orders remains deferred.
