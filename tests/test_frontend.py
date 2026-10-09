from pathlib import Path
from tests.test_integration import client

def test_react_entrypoint(client):
    built=Path('website/dist/index.html').is_file()
    response=client.get('/')
    if not built:
        assert response.status_code==503
        assert 'npm' in response.json()['detail']
        return
    assert response.status_code==200
    assert 'Paw Protectors' in response.text
    import re
    assets=re.findall(r'(?:src|href)="(/assets/[^"]+)"',response.text)
    assert len(assets)>=2
    for asset in assets:
        assert client.get(asset).status_code==200
    assert client.get('/assets/../../.env').status_code==404
