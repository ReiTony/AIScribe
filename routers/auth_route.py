import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

# Local imports
from db.connection import get_db
from models.auth_schema import (
    RegisterRequest, 
    LoginRequest, 
    MessageResponse, 
    TokenResponse, 
    AuthenticatedUserResponse,
    UserResponse,
    RefreshTokenRequest,
    TokenValidationResponse
)
from utils.encryption import hash_password, verify_password, get_current_user
from utils.jwt_handler import create_access_token, create_refresh_token, verify_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()
logger = logging.getLogger("AuthRouter")

def get_user_collection(db: AsyncIOMotorClient):
    return db["users"]

@router.post("/register", response_model=MessageResponse)
async def register_user(request: RegisterRequest, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        user_collection = get_user_collection(db)
        existing_user = await user_collection.find_one({"username": request.username})
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        hashed_password = hash_password(request.password)
        user_data = {
            "username": request.username, 
            "password": hashed_password,
            "created_at": datetime.now(timezone.utc)
        }
        await user_collection.insert_one(user_data)
        return {"message": "User registered successfully"}
    except Exception as e:
        logger.error(f"Error in User Registration: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/login", response_model=AuthenticatedUserResponse)
async def login_user(request: LoginRequest, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        user_collection = get_user_collection(db)
        user = await user_collection.find_one({"username": request.username})
        if not user or not verify_password(request.password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user["username"]})
        refresh_token = create_refresh_token(data={"sub": user["username"]})
        
        user_response = UserResponse(
            username=user["username"],
            created_at=user.get("created_at")
        )
        
        return AuthenticatedUserResponse(
            user=user_response,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  
        )
    except Exception as e:
        logger.error(f"Error in Login: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(request: RefreshTokenRequest):
    try:
        payload = verify_token(request.refresh_token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if it's actually a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create new tokens
        new_access_token = create_access_token(data={"sub": username})
        new_refresh_token = create_refresh_token(data={"sub": username})
        
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    except Exception as e:
        logger.error(f"Error in refresh_access_token: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/validate", response_model=TokenValidationResponse)
async def validate_token(current_user: dict = Depends(get_current_user)):
    try:
        payload = current_user["payload"]
        exp_timestamp = payload.get("exp")
        expires_at = None
        if exp_timestamp:
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        
        return TokenValidationResponse(
            valid=True,
            username=current_user["username"],
            expires_at=expires_at
        )
    except Exception as e:
        logger.error(f"Error in validate_token: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user), db: AsyncIOMotorClient = Depends(get_db)):
    try:
        user_collection = get_user_collection(db)
        user = await user_collection.find_one({"username": current_user["username"]})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(
            username=user["username"],
            created_at=user.get("created_at")
        )
    except Exception as e:
        logger.error(f"Error in get_current_user_info: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/logout", response_model=MessageResponse)
async def logout_user():
    try:
        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Error in logout_user: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
