import logging

from fastapi import APIRouter, Depends 
from motor.motor_asyncio import AsyncIOMotorClient
from db.connection import get_db

router = APIRouter()
logger = logging.getLogger("AuthRouter")

def get_user_collection(db: AsyncIOMotorClient):
    return db["users"]

@router.post("/register")
async def register_user(username: str, password: str, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        user_collection = get_user_collection(db)
        existing_user = await user_collection.find_one({"username": username})
        if existing_user:
            return {"error": "Username already exists"}
        await user_collection.insert_one({"username": username, "password": password})
        return {"message": "User registered successfully"}
    except Exception as e:
        logger.error(f"Error in User Registration: {e}")
        return {"error": "Internal Server Error"}
    
@router.post("/login")
async def login_user(username: str, password: str, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        user_collection = get_user_collection(db)
        user = await user_collection.find_one({"username": username, "password": password})
        if not user:
            return {"error": "Invalid username or password"}
        return {"message": "Login successful"}
    except Exception as e:
        logger.error(f"Error in login_user: {e}")
        return {"error": "Internal Server Error"}
    
@router.post("/logout")
async def logout_user():
    try:
        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Error in logout_user: {e}")
        return {"error": "Internal Server Error"}
    
