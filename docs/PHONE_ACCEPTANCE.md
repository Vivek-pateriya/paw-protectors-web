# React Native phone acceptance — 31 October 2026

Status: **paused at the user's explicit request**. Resume only when requested. Testing concerns the React Native app and common backend; no legacy Java project files were changed.

Device: I2221 over USB. App: `org.pawprotectors.reactnative`, version 1.0.0, standalone ARM64 APK. Common FastAPI backend: localhost port 8000, reached from the phone through ADB reverse forwarding.

## Passed on the phone

- App launch and welcome-screen rendering.
- Login: the user manually signed in with a dedicated temporary owner account. The dashboard then loaded the test pet and four reminders from the common backend.
- Navigation between Home, Account, My pets, pet detail and the OS demonstration.
- Pet detail displayed the seeded weight and separate allergy field.
- The native OS module executed through the React Native bridge: **80 admitted, 40 completed, 40 duplicate IDs, zero failures, zero queued tasks**, and all three workers reported **TERMINATED**. This verifies runtime execution beyond compilation/autolinking. Observed producer waits: 79; cumulative resource wait: 2844 ms. These timings/counters vary with scheduling.
- No AndroidRuntime/ReactNativeJS error was present in the app-specific log sample collected before these UI checks. This is a bounded log observation, not a guarantee covering every workflow.

OS evidence: `artifacts/phone-acceptance/os-complete.png`.

## Not yet tested

- Medication screens and creation/stopping through the phone UI.
- Notification-centre read/acknowledgement interactions on the phone.
- Notification permission, background task registration and actual delivery.
- Gallery selection, upload and authenticated image display through the phone UI.
- Profile/password forms and their submission on the phone.
- Saved-session restoration after a phone-app restart.
- Appointment booking/cancellation through the phone UI.
- Native worker cancellation during an active run.

The notification permission was not granted at the time it was inspected. No claim of background-notification acceptance is made.

## Test data and pause

The saved original sample owner/admin passwords were not accepted by the local API. They were not reset or changed. A dedicated temporary owner and a clearly named `Phone QA Pet` were created for this test, with a vaccination reminder and finite demonstration medication schedule. Existing pet records were not edited.

Private login details and fixture IDs are in `artifacts/private-mailbox/phone-test-login.txt` and `phone-test-fixture.json`; both are excluded from Git. They are retained for resuming the same test. Do not include them in a public repository or report.

When the phone moved to another app, input was paused. The user then explicitly chose **Pause phone testing for now**. No further phone interactions were performed. An incidental screenshot outside Paw Protectors was removed and is not part of the evidence.
