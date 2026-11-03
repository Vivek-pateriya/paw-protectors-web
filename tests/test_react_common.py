import re
from tests.test_integration import client
from backend.main import react_dir


def test_react_client_served_by_common_backend(client):
    response=client.get('/app')
    if not (react_dir / 'index.html').is_file():
        assert response.status_code==503
        return
    assert response.status_code==200
    assets=re.findall(r'(?:src|href)="(/assets/[^"]+)"',response.text)
    assert len(assets)>=2
    for path in assets:assert client.get(path).status_code==200
    assert client.get('/assets/../../.env').status_code==404
