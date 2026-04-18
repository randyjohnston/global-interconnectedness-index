"""Country endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gii.api.dependencies import get_db, get_repo
from gii.api.schemas import CountryResponse

router = APIRouter(prefix="/api/countries", tags=["countries"])


@router.get("", response_model=list[CountryResponse])
def list_countries(session: Session = Depends(get_db)):
    repo = get_repo(session)
    rows = repo.list_countries()
    return [
        CountryResponse(iso3=r.iso3, iso2=r.iso2, name=r.name, region=r.region)
        for r in rows
    ]
