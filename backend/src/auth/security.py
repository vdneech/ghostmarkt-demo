from typing import Optional
from fastapi import HTTPException, status
from fastapi.openapi.models import APIKey, APIKeyIn
from fastapi.security.base import SecurityBase
from starlette.requests import Request


class CookieAuth(SecurityBase):
    """
    Cookie-based Authentication Scheme.

    Extracts the JWT token from the specified HttpOnly cookie.
    If the cookie is missing, an HTTPException (401) is raised.

    Args:
        cookie_name (str): The name of the cookie containing the authentication token.
    """

    def __init__(self, cookie_name: str, auto_error: bool = True):
        self.model: APIKey = APIKey(**{"in": APIKeyIn.cookie}, name=cookie_name)
        self.scheme_name: str = "CookieAuth"
        self.cookie_name = cookie_name
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> Optional[str]:
        token = request.cookies.get(self.cookie_name)

        if not token:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing cookie: {}. Please authorize via /auth/login".format(self.cookie_name),
                )
            return None

        return token
