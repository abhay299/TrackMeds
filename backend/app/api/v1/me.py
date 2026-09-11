from fastapi import APIRouter

from app.api.deps import Me
from app.core.db import DbSession
from app.schemas import ProfileOut, ProfilePatch

router = APIRouter(tags=["me"])


@router.get("/me", response_model=ProfileOut)
async def read_me(profile: Me) -> ProfileOut:
    return ProfileOut.model_validate(profile)


@router.patch("/me", response_model=ProfileOut)
async def update_me(patch: ProfilePatch, profile: Me, db: DbSession) -> ProfileOut:
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    return ProfileOut.model_validate(profile)
