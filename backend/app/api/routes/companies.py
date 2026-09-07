import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.company import Company
from app.schemas.company import CompanyRead

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
async def list_companies(db: AsyncSession = Depends(get_db)) -> list[CompanyRead]:
    result = await db.execute(select(Company).order_by(Company.name))
    return [CompanyRead.model_validate(c) for c in result.scalars().all()]


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CompanyRead:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return CompanyRead.model_validate(company)
