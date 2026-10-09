# Repository verification — 9 October 2026

- React 19.3.0 and Vite 8.3.4; `npm install` generated `website/package-lock.json`. npm reported zero known vulnerabilities in the installed dependency tree.
- `npm run build` passed: React production assets generated in ignored `website/dist`.
- Copied Python/PostgreSQL suite: **15 passed, 0 failures**. Includes real 100-attempt booking race (one success, 99 conflicts), roles, images, rollback and React asset serving. Test report generated at `artifacts/pytest.xml`.
- React browser checks using the existing backend: owner login, existing records, synthetic `React QA` pet creation, profile edit and persisted health profile; no error/warning logs observed. Other React actions are implemented but not all manually acceptance-tested.
- Source-only delivery: no Android tree, secrets, local database, photos, downloaded tools, virtual environment, npm dependencies or generated assets committed.

The source was checked on Windows with Python 3.12.14 and Node 24.19.0. One upstream Starlette/AnyIO deprecation warning remains. The current pre-existing plain-JavaScript website was preserved outside this repository. This repository's frontend is implemented with React components/hooks.

Run instructions are in the root README. PostgreSQL demonstrations and performance scripts are included; new benchmark runs write actual results locally rather than promising fixed timings. GitHub remote: https://github.com/Vivek-pateriya/paw-protectors-web.git. The Android companion remains a separate local repository.
