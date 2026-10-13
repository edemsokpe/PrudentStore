import uuid
import boto3
from botocore.config import Config
from fastapi import HTTPException, UploadFile
from .config import settings

ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 5 * 1024 * 1024

_s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name="auto",
    config=Config(signature_version="s3v4"),
)


def upload_image(file: UploadFile, folder: str = "products") -> tuple[str, str]:
    """Upload to R2. Returns (object_key, public_url)."""
    ext = ALLOWED.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Only JPEG, PNG or WEBP images are allowed")
    data = file.file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Image must be 5 MB or smaller")
    key = f"{folder}/{uuid.uuid4().hex}.{ext}"
    _s3.put_object(
        Bucket=settings.R2_BUCKET,
        Key=key,
        Body=data,
        ContentType=file.content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    return key, f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def delete_image(key: str) -> None:
    _s3.delete_object(Bucket=settings.R2_BUCKET, Key=key)
