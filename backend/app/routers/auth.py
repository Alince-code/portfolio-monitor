"""用户认证相关API端点 —— 注册、登录、密码管理等。"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.hash import pbkdf2_sha256
from pydantic import EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRegister, UserLogin, AuthResponse, ChangePassword, UserInfo

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# JWT配置
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希后的密码是否匹配。"""
    if hashed_password.startswith("$pbkdf2-sha256$"):
        return pbkdf2_sha256.verify(plain_password, hashed_password)

    if hashed_password.startswith("$2"):
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    return False


def get_password_hash(password: str) -> str:
    """生成密码的安全哈希值。

    使用 pbkdf2_sha256 避免 passlib+bcrypt 在部分环境下的兼容问题。
    """
    return pbkdf2_sha256.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT访问令牌。"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user_from_token(token: str, db: Session) -> Optional[User]:
    """根据JWT令牌获取用户对象，无效时返回None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            return None
    except JWTError:
        return None

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None
    return user


def ensure_default_admin(db: Session) -> None:
    """确保系统存在默认管理员账户。"""
    existing_user = db.query(User).filter(User.username == "admin").first()
    if existing_user:
        return

    db.add(User(
        username="admin",
        email="admin@portfolio-monitor.local",
        hashed_password=get_password_hash("admin123"),
        full_name="Administrator",
        is_active=True,
    ))
    db.commit()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """从JWT令牌中提取并验证当前用户。"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的身份验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = get_user_from_token(token, db)
    if user is None:
        raise credentials_exception
    return user


@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """注册新用户账号。"""
    # 检查用户名是否已存在
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被占用"
        )
    
    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册"
        )
    
    # 创建新用户
    hashed_pw = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pw,
        full_name=user_data.full_name,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user


@router.post("/login", response_model=AuthResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """用户登录并返回访问令牌。"""
    user = db.query(User).filter(User.username == credentials.username).first()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账号已被禁用"
        )
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserInfo)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户的个人信息。"""
    return current_user


@router.post("/change-password")
def change_password(
    password_data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改当前用户的登录密码。"""
    # 验证旧密码
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码输入错误"
        )
    
    # 新密码不能与旧密码相同
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与旧密码相同"
        )
    
    # 更新密码
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "密码修改成功"}


@router.post("/logout")
def logout():
    """登出当前用户（客户端应丢弃令牌）。"""
    return {"message": "退出登录成功"}
