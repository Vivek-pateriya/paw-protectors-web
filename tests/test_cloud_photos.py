import httpx
import pytest
from fastapi import HTTPException
from backend import photos


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv('PHOTO_STORAGE', 'cloudinary')
    monkeypatch.setenv('CLOUDINARY_URL', 'cloudinary://test-key:test-private-secret@photo-test')


def test_cloud_delivery_is_signed_and_proxied_without_public_redirect(cloud, monkeypatch):
    image = b'\x89PNG\r\n\x1a\nexample'
    def handle(request):
        assert request.url.host == 'res.cloudinary.com'
        assert '/image/authenticated/s--' in request.url.path
        assert 'test-private-secret' not in str(request.url)
        return httpx.Response(200, content=image)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(photos.httpx, 'stream', client.stream)
        response = photos.image_response('stored-photo.png')
    assert response.body == image
    assert response.media_type == 'image/png'
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'location' not in response.headers


def test_cloud_upload_errors_do_not_leak_secrets_or_fall_back_to_ephemeral_disk(cloud, monkeypatch, tmp_path):
    import cloudinary.uploader
    def fail(*args, **kwargs):
        assert kwargs['type'] == 'authenticated'
        raise RuntimeError('provider response includes test-private-secret')
    monkeypatch.setattr(cloudinary.uploader, 'upload', fail)
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path))
    with pytest.raises(HTTPException) as error:
        photos.save_image(b'photo', '.jpg')
    assert error.value.status_code == 502
    assert 'test-private-secret' not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_photo_names_cannot_escape_the_storage_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('PHOTO_STORAGE', 'local')
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path))
    for name in ('../secret.jpg', 'https://example.test/photo.jpg', None):
        with pytest.raises(HTTPException):
            photos.image_response(name)
