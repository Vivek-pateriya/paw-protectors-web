# Optional illustrated demo catalogue

The optional importer adds 10 adoption demo profiles (two cats, three dogs and five different birds) and 10 shop products. It downloads free Unsplash reference photos and records source/license links locally. These are sample profiles/prices/stock, not verified real adoption offers or fulfilment inventory.

Start the backend first. From the backend repository, use your own local admin password:

```powershell
.\.venv\Scripts\python.exe scripts/populate_demo_catalogue.py prepare
$pawCredential = Get-Credential -UserName 'admin@paw.local' -Message 'Local Paw Protectors admin login'
$env:PAW_ADMIN_PASSWORD = $pawCredential.GetNetworkCredential().Password
try {
    .\.venv\Scripts\python.exe scripts/populate_demo_catalogue.py import
} finally {
    Remove-Item Env:PAW_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}
```

The script uses the common API and saves downloaded photos, their source/license manifest and resumable record IDs in gitignored `artifacts/catalogue-20261103/`. It preserves unrelated records. Keep the checkpoint when rerunning: deleting it can duplicate adoption listings.

Admin-created adoption listings are published directly. Shop products are active, stocked and visible to owner/vet accounts. No orders or adoption applications are created. Both clients load the same records and authenticated uploaded photos. Review/edit/archive the sample content through the admin screens as needed.
