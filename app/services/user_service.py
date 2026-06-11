import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import UserModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class UserService:
    """用户服务类, 提供用户信息查询和更新功能"""

    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id) -> Optional[UserModel]:
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_profile(self, username: str, data: dict) -> UserModel:
        """更新用户资料字段."""
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found")

            # # 如果请求修改用户名，则检查用户名是否唯一
            new_username = data.get("username")
            if new_username and new_username != user.username:
                # 检查新用户名是否已存在
                stmt2 = select(UserModel).where(UserModel.username == new_username)
                res2 = await session.execute(stmt2)
                if res2.scalar_one_or_none():
                    raise ValueError("Username already exists")
                user.username = new_username

            if "occupation" in data:
                user.occupation = data.get("occupation")
            if "bio" in data:
                user.bio = data.get("bio")
            if "profile" in data:
                user.profile = data.get("profile")
            if "user_instruction" in data:
                user.user_instruction = data.get("user_instruction")

            try:
                await session.flush()
            except IntegrityError as exc:
                logger.warning("Integrity error updating profile: %s", exc)
                raise ValueError("Failed to update profile")

            return user


user_service = UserService()
