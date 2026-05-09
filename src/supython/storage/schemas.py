from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateBucketRequest(BaseModel):
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")
    public: bool = False
    file_size_limit: int | None = Field(default=None, ge=1)
    allowed_mime_types: list[str] | None = None


class BucketResponse(BaseModel):
    id: UUID
    name: str
    owner: UUID | None
    public: bool
    file_size_limit: int | None
    allowed_mime_types: list[str] | None
    created_at: datetime
    updated_at: datetime


class ObjectResponse(BaseModel):
    id: UUID
    bucket_id: UUID
    bucket: str
    name: str
    owner: UUID
    size: int
    mime_type: str | None
    etag: str | None
    created_at: datetime
    updated_at: datetime


class SignedUrlRequest(BaseModel):
    expires_in: int | None = Field(
        default=None,
        ge=1,
        description="Lifetime of the signed URL in seconds. Defaults to settings.",
    )


class SignedUrlResponse(BaseModel):
    signed_url: str
    token: str
    expires_at: datetime
    expires_in: int
