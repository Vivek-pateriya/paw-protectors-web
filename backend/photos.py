"""Local development or authenticated Cloudinary storage, behind existing API checks."""
import io
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

LIMIT = 5 * 1024 * 1024


def cloud_enabled():
    mode = os.getenv('PHOTO_STORAGE', 'local')
    if mode not in ('local', 'cloudinary'):
        raise RuntimeError('PHOTO_STORAGE must be local or cloudinary')
    return mode == 'cloudinary'


def cloud_options():
    parsed = urlparse(os.getenv('CLOUDINARY_URL', ''))
    if parsed.scheme != 'cloudinary' or not parsed.hostname or not parsed.username or not parsed.password:
        raise RuntimeError('Configure a private CLOUDINARY_URL for cloud photo storage')
    return dict(cloud_name=parsed.hostname, api_key=unquote(parsed.username), api_secret=unquote(parsed.password), secure=True)


def valid_name(name):
    if not name or not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:jpg|png)', name):
        raise HTTPException(404, 'No image')
    return name


def public_id(name):
    folder = os.getenv('CLOUDINARY_FOLDER', 'paw-protectors')
    if not re.fullmatch(r'[A-Za-z0-9_/-]+', folder):
        raise RuntimeError('Invalid Cloudinary folder')
    return folder.strip('/') + '/' + Path(valid_name(name)).stem


def save_image(content, extension, filename=None):
    filename = valid_name(filename or uuid4().hex + extension)
    if cloud_enabled():
        import cloudinary.uploader
        try:
            result = cloudinary.uploader.upload(io.BytesIO(content), public_id=public_id(filename),
                resource_type='image', type='authenticated', overwrite=False, unique_filename=False,
                format=Path(filename).suffix[1:], timeout=30, **cloud_options())
            if result.get('type') != 'authenticated':
                raise RuntimeError('Unexpected photo access type')
        except Exception:
            raise HTTPException(502, 'Photo storage unavailable; please retry') from None
    else:
        directory = Path(os.getenv('UPLOAD_DIR', 'uploads'))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_bytes(content)
    return filename


def delete_image(filename):
    if cloud_enabled():
        import cloudinary.uploader
        try:
            cloudinary.uploader.destroy(public_id(filename), resource_type='image', type='authenticated', **cloud_options())
        except Exception:
            pass  # Preserve the original transaction error; never expose provider credentials.
    else:
        (Path(os.getenv('UPLOAD_DIR', 'uploads')) / valid_name(filename)).unlink(missing_ok=True)


def image_response(filename):
    filename = valid_name(filename)
    if not cloud_enabled():
        path = Path(os.getenv('UPLOAD_DIR', 'uploads')) / filename
        if not path.is_file():
            raise HTTPException(404, 'No image')
        return FileResponse(path)
    return Response(cloud_image_bytes(filename), media_type='image/png' if filename.endswith('.png') else 'image/jpeg',
                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


def cloud_image_bytes(filename):
    import cloudinary.utils
    url, _ = cloudinary.utils.cloudinary_url(public_id(filename), resource_type='image',
        type='authenticated', sign_url=True, format=Path(filename).suffix[1:], **cloud_options())
    try:
        with httpx.stream('GET', url, timeout=30) as response:
            if response.status_code == 404:
                raise HTTPException(404, 'No image')
            response.raise_for_status()
            parts, size = [], 0
            for part in response.iter_bytes():
                size += len(part)
                if size > LIMIT:
                    raise HTTPException(502, 'Stored photo exceeds image limit')
                parts.append(part)
            return b''.join(parts)
    except httpx.HTTPError:
        raise HTTPException(502, 'Photo storage unavailable; please retry') from None
