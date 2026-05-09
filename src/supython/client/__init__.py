from ._auth import (
    SIGNED_IN,
    SIGNED_OUT,
    TOKEN_REFRESHED,
    USER_UPDATED,
    AuthChangeCallback,
    AuthError,
    Session,
    SupythonResponse,
    TokenResponse,
    UserResponse,
)
from ._client import Client
from ._config import (
    AuthOptions,
    AuthStorageBackend,
    ClientOptions,
    FileAuthStorage,
    MemoryAuthStorage,
)
from ._functions import FunctionsClient, FunctionsError
from ._storage import (
    BucketResponse,
    ObjectResponse,
    SignedUrlResponse,
    StorageBucket,
    StorageClient,
    StorageError,
)


def create_client(
    supython_url: str,
    anon_key: str = "",
    *,
    options: ClientOptions | None = None,
) -> Client:
    return Client(supython_url, anon_key, options=options)


__all__ = [
    "create_client",
    "Client",
    "ClientOptions",
    "AuthOptions",
    "AuthError",
    "AuthChangeCallback",
    "Session",
    "SupythonResponse",
    "TokenResponse",
    "UserResponse",
    "SIGNED_IN",
    "SIGNED_OUT",
    "TOKEN_REFRESHED",
    "USER_UPDATED",
    "StorageClient",
    "StorageBucket",
    "StorageError",
    "BucketResponse",
    "ObjectResponse",
    "SignedUrlResponse",
    "FunctionsClient",
    "FunctionsError",
    "AuthStorageBackend",
    "MemoryAuthStorage",
    "FileAuthStorage",
]
