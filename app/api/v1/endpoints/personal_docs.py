"""个人知识文档相关接口"""
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.personal_document_service import personal_document_service

logger = logging.getLogger(__name__)
router = APIRouter()


class PersonalDocCreateRequest(BaseModel):
    dish_name: str = Field(..., min_length=2, max_length=255)
    category: str = Field(..., min_length=2, max_length=100)
    difficulty: str = Field(..., min_length=1, max_length=50)
    data_source: Literal["recipes", "tips", "personal"] = "personal"
    content: str = Field(..., min_length=1)


class PersonalDocUpdateRequest(BaseModel):
    dish_name: str = Field(..., min_length=2, max_length=255)
    category: str = Field(..., min_length=2, max_length=100)
    difficulty: str = Field(..., min_length=1, max_length=50)
    data_source: Literal["recipes", "tips", "personal"] = "personal"
    content: str = Field(..., min_length=1)


@router.post("/knowledge/personal-docs")
async def create_personal_document(request: Request, payload: PersonalDocCreateRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    try:
        doc = await personal_document_service.create_document(
            user_id=user_id,
            dish_name=payload.dish_name,
            category=payload.category,
            difficulty=payload.difficulty,
            data_source=payload.data_source,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return doc.to_dict()


@router.get("/knowledge/personal-docs")
async def list_personal_documents(request: Request, limit: int = 50, offset: int = 0):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    docs = await personal_document_service.list_documents(user_id, limit=limit, offset=offset)
    return {"items": docs, "limit": limit, "offset": offset}


@router.get("/knowledge/personal-docs/{document_id}")
async def get_personal_document(request: Request, document_id: str):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    doc = await personal_document_service.get_document(user_id, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return doc


@router.put("/knowledge/personal-docs/{document_id}")
async def update_personal_document(request: Request, document_id: str, payload: PersonalDocUpdateRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    try:
        doc = await personal_document_service.update_document(
            user_id=user_id,
            document_id=document_id,
            dish_name=payload.dish_name,
            category=payload.category,
            difficulty=payload.difficulty,
            data_source=payload.data_source,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    return doc.to_dict()


@router.delete("/knowledge/personal-docs/{document_id}")
async def delete_personal_document(request: Request, document_id: str):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    deleted = await personal_document_service.delete_document(user_id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    return {"success": True, "message": "文档已删除"}


@router.get("/knowledge/metadata-options")
async def get_metadata_options(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")

    options = personal_document_service.get_available_options(user_id)
    return options
