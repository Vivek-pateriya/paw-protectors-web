# One-day demo: Render Free + Cloudinary Free

Both React clients use one Render web service and one PostgreSQL database. Only `free` plans are authorized. Do not attach a paid disk, enable database autoscaling, or add paid services.

## Deployment configuration

- Source: `https://github.com/Vivek-pateriya/paw-protectors-web`, branch `main`.
- Web runtime: Docker, repository-root `Dockerfile`, context `.`.
- Web compute plan: **Free**. Region: **Singapore**, matching the database.
- PostgreSQL: **Free**, PostgreSQL **17**, default free storage. No replicas or high availability.
- Health path: `/health`.
- Website: `/app` or `/`; the Docker build includes the React website.
- No additional Node/Metro service is needed for the installed Android app.

Set private service environment variables:

| Key | Value/source |
| --- | --- |
| `DATABASE_URL` | Database **Internal Database URL**, same workspace and region |
| `TOKEN_SECRET` | New random secret, at least 32 characters; keep private |
| `PHOTO_STORAGE` | `cloudinary` |
| `CLOUDINARY_URL` | Cloudinary API environment variable; keep private |
| `CLOUDINARY_FOLDER` | `paw-protectors` |
| `RECOVERY_DELIVERY` | `local` for this demo; email delivery is not configured |

Startup applies missing migrations without seeding accounts. Restore existing records before starting the service. Existing account password hashes and photo filenames are preserved; log in again because cloud sessions use a new secret.

## Existing-data migration

Back up the local database and all referenced files to a private directory. The migration helper expects `database.dump` (pg_dump custom format), `photos.tar.gz`, and `manifest.json` with table row counts and photo SHA-256 hashes. This directory and credential files must never be committed.

In a separate private credentials file, configure `CLOUDINARY_URL` and `DEST_DATABASE_URL` (the database's **External Database URL**). Use that external URL only from your laptop; the deployed application uses the internal URL.

```powershell
python -m scripts.migrate_hosting photos --backup-dir PRIVATE_BACKUP --credentials PRIVATE_ENV
python -m scripts.migrate_hosting database --backup-dir PRIVATE_BACKUP --credentials PRIVATE_ENV --postgres-bin PATH_TO_POSTGRES_BIN
python -m scripts.migrate_hosting verify --backup-dir PRIVATE_BACKUP --credentials PRIVATE_ENV
```

Run photos first. It uploads authenticated assets, verifies downloaded bytes against the backup, and checkpoints progress. Database restore accepts only an empty Render destination, requires a completed photo migration, and verifies all table counts. It never clears an existing database or changes the local source. Do not rerun `database` after successful restore; use `verify`.

All photos remain behind the same API authorization checks. The server fetches signed authenticated Cloudinary assets and returns image bytes; clients never receive the Cloudinary API secret or signed delivery URL. Local development continues using `PHOTO_STORAGE=local`.

## Phone and demo

Enter the Render service's HTTPS base URL in **Account → Server connection**. Check `/health`, log in, and check pet/adoption/shop photos. Disable Wi-Fi and USB on the phone to test using mobile data. The laptop can be switched off once cloud migration and deployment are verified.

Render Free sleeps after 15 minutes without requests; the first request may take about a minute. Open `/health` in a browser before the demonstration, wait for success, then use the app. Free PostgreSQL expires after 30 days. Free services have quotas and can be suspended when exhausted. Uploaded files survive Render restarts because Cloudinary stores them. Password-recovery email is not configured for this one-day demo.

After the demo, export any new cloud records before removing cloud resources. Deletion must be explicitly requested; this setup does not delete anything automatically.
