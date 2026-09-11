from fastapi import APIRouter
from pydantic import BaseModel

from app.core.security import CurrentUser

router = APIRouter(tags=["me"])


class Me(BaseModel):
    id: str
    email: str | None


@router.get("/me", response_model=Me)
async def read_me(user: CurrentUser) -> Me:
    # Phase 0: identity straight from the verified token — proves auth end to end.
    # Phase 1: becomes the `profiles` row (timezone, grace), auto-created on first call.
    return Me(id=user.id, email=user.email)
