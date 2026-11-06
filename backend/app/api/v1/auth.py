from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    create_refresh_token,
    create_refresh_token_record,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    validate_refresh_token,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import Device, RefreshToken, User
from app.schemas import (
    DeviceAccess,
    DeviceBinding,
    LoginRequest,
    PlaylistAccess,
    RefreshRequest,
    RevokeResponse,
    TokenPair,
    UserCreate,
    UserResponse,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)
settings = get_settings()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload.get("sub", 0))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def get_current_device_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    # Extract device_id from X-Device-Id header if needed, for now return empty
    # The Android app sends X-Device-Id header, but we can also get from token
    return ""


@router.post("/auth/login", response_model=TokenPair)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User disabled")

    access_token = create_access_token(user.id)
    refresh_token, refresh_expires = create_refresh_token(user.id)
    token_hash = decode_token(refresh_token)["jti"]
    await create_refresh_token_record(db, user.id, token_hash, None, refresh_expires)
    await db.commit()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    rt = await validate_refresh_token(db, request.refresh_token)
    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await get_user_by_id(db, rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Revoke old refresh token
    from datetime import datetime, timezone
    rt.revoked_at = datetime.now(timezone.utc)

    # Create new tokens
    access_token = create_access_token(user.id)
    new_refresh_token, refresh_expires = create_refresh_token(user.id, rt.device_id)
    new_token_hash = decode_token(new_refresh_token)["jti"]
    await create_refresh_token_record(db, user.id, new_token_hash, rt.device_id, refresh_expires)
    await db.commit()

    return TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/player/playlist", response_model=PlaylistAccess)
async def get_playlist(
    current_user: User = Depends(get_current_user),
):
    # Verifica assinatura
    if current_user.subscription_status != "active":
        raise HTTPException(
            status_code=403,
            detail={"code": "subscription_inactive", "message": "Assinatura inativa"},
        )

    return PlaylistAccess(
        playlist_url=settings.authorized_playlist_url,
        user_agent=settings.authorized_playlist_user_agent,
        referer=settings.authorized_playlist_referer or None,
        refresh_in=300,
        offline_grace_seconds=0,
        subscription_status=current_user.subscription_status.value
        if hasattr(current_user.subscription_status, "value")
        else str(current_user.subscription_status),
        days_remaining=30,  # TODO: calcular baseado em subscription_expires_at
    )


@router.get("/player/device", response_model=DeviceAccess)
async def get_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.user_id == current_user.id).order_by(Device.created_at.desc())
    )
    devices = result.scalars().all()

    return DeviceAccess(
        limit=settings.max_devices_per_user,
        bound=len(devices),
        devices=[
            DeviceBinding(
                device_id=d.device_id,
                device_name=d.device_name,
                current=bool(d.is_current),
            )
            for d in devices
        ],
    )


@router.post("/player/device/revoke", response_model=RevokeResponse)
async def revoke_device(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Revoga o dispositivo atual (o que fez a requisição)
    # Como não temos o device_id no token, revogamos todos ou o marcado como current
    result = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_current == 1)
    )
    current_device = result.scalar_one_or_none()

    if current_device:
        current_device.is_current = 0
        await db.commit()
        return RevokeResponse(message="Device revoked successfully")

    raise HTTPException(status_code=404, detail="No current device found")