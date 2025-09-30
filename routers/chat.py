from fastapi import APIRouter, Depends, HTTPException, status
from utils.prompts import system_instruction
router = APIRouter(prefix="/chat", tags=["chat"])
