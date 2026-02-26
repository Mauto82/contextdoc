from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
import models
from database import Base, engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/register", response_model=models.UserOut, status_code=201)
async def register(data: models.UserCreate, db: AsyncSession = Depends(get_session)):
    existing = await db.execute(
        select(models.User).where(models.User.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(
        email=data.email,
        hashed_password=auth.hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post("/login", response_model=models.TokenOut)
async def login(data: models.UserCreate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(models.User).where(models.User.email == data.email)
    )
    user = result.scalar_one_or_none()
    if not user or not auth.verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account not active")
    return {"access_token": auth.create_access_token({"sub": str(user.id)})}


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_deleted = True
    await db.commit()
