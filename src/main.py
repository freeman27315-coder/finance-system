#!/usr/bin/env python3
"""Finance system API with authentication and role-based access control."""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Literal, Optional

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field


Role = Literal["admin", "accountant", "auditor"]

DATABASE_PATH = os.environ.get("FINANCE_DB_PATH", "finance.db")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 8 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Finance System API", lifespan=lifespan)
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    token: str
    role: Role
    expires_in: int
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    role: Role


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    is_locked: bool
    failed_attempts: int
    locked_until: Optional[str]
    created_at: str


class CurrentUser(BaseModel):
    id: int
    username: str
    role: Role


class StatusResponse(BaseModel):
    status: str


class BillCreate(BaseModel):
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field("general", min_length=1, max_length=80)
    occurred_at: Optional[str] = None


class BillOut(BaseModel):
    id: int
    amount: float
    description: str
    category: str
    occurred_at: str
    created_by: int
    created_at: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def row_to_user(row: sqlite3.Row) -> UserOut:
    return UserOut(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        is_locked=bool(row["is_locked"]),
        failed_attempts=row["failed_attempts"],
        locked_until=row["locked_until"],
        created_at=row["created_at"],
    )


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY,
              username TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('admin','accountant','auditor')),
              is_locked INTEGER DEFAULT 0,
              failed_attempts INTEGER DEFAULT 0,
              locked_until TIMESTAMP,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS revoked_tokens (
              jti TEXT PRIMARY KEY,
              expires_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bills (
              id INTEGER PRIMARY KEY,
              amount REAL NOT NULL CHECK(amount > 0),
              description TEXT NOT NULL,
              category TEXT NOT NULL,
              occurred_at TIMESTAMP NOT NULL,
              created_by INTEGER NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(created_by) REFERENCES users(id)
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if count == 0:
            username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
            password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123456")
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, 'admin')
                """,
                (username, hash_password(password)),
            )


def create_token(user: sqlite3.Row) -> str:
    now = utc_now()
    expires_at = now + timedelta(seconds=TOKEN_TTL_SECONDS)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        ) from exc
    required = {"sub", "username", "role", "jti", "exp"}
    if not required.issubset(payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 信息不完整")
    return payload


def get_current_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")

    payload = decode_token(credentials.credentials)
    with db() as conn:
        revoked = conn.execute(
            "SELECT 1 FROM revoked_tokens WHERE jti = ?",
            (payload["jti"],),
        ).fetchone()
        if revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已登出")

        user = conn.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    return {"payload": payload, "user": user, "token": credentials.credentials}


def require_roles(*allowed_roles: Role):
    def dependency(session: Dict[str, Any] = Depends(get_current_session)) -> sqlite3.Row:
        role = session["user"]["role"]
        if role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行该操作")
        return session["user"]

    return dependency


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest) -> TokenResponse:
    now = utc_now()
    with db() as conn:
        user = get_user_by_username(conn, request.username)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        locked_until = parse_dt(user["locked_until"])
        if user["is_locked"] and locked_until and locked_until <= now:
            conn.execute(
                """
                UPDATE users
                SET is_locked = 0, failed_attempts = 0, locked_until = NULL
                WHERE id = ?
                """,
                (user["id"],),
            )
            user = get_user_by_username(conn, request.username)

        if user["is_locked"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已锁定，请 30 分钟后再试",
            )

        if not verify_password(request.password, user["password_hash"]):
            failed_attempts = user["failed_attempts"] + 1
            if failed_attempts >= MAX_FAILED_ATTEMPTS:
                conn.execute(
                    """
                    UPDATE users
                    SET failed_attempts = ?, is_locked = 1, locked_until = ?
                    WHERE id = ?
                    """,
                    (
                        failed_attempts,
                        as_iso(now + timedelta(minutes=LOCKOUT_MINUTES)),
                        user["id"],
                    ),
                )
                conn.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="登录失败次数过多，账号已锁定 30 分钟",
                )
            conn.execute(
                "UPDATE users SET failed_attempts = ? WHERE id = ?",
                (failed_attempts, user["id"]),
            )
            conn.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        conn.execute(
            """
            UPDATE users
            SET failed_attempts = 0, is_locked = 0, locked_until = NULL
            WHERE id = ?
            """,
            (user["id"],),
        )
        user = get_user_by_username(conn, request.username)
        token = create_token(user)

    return TokenResponse(token=token, role=user["role"], expires_in=TOKEN_TTL_SECONDS)


@app.post("/auth/logout", response_model=StatusResponse)
def logout(session: Dict[str, Any] = Depends(get_current_session)) -> StatusResponse:
    payload = session["payload"]
    expires_at = datetime.fromtimestamp(payload["exp"], timezone.utc)
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO revoked_tokens (jti, expires_at) VALUES (?, ?)",
            (payload["jti"], as_iso(expires_at)),
        )
    return StatusResponse(status="ok")


@app.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(session: Dict[str, Any] = Depends(get_current_session)) -> TokenResponse:
    user = session["user"]
    token = create_token(user)
    return TokenResponse(token=token, role=user["role"], expires_in=TOKEN_TTL_SECONDS)


@app.get("/auth/me", response_model=CurrentUser)
def me(session: Dict[str, Any] = Depends(get_current_session)) -> CurrentUser:
    user = session["user"]
    return CurrentUser(id=user["id"], username=user["username"], role=user["role"])


@app.get("/users", response_model=list[UserOut])
def list_users(_: sqlite3.Row = Depends(require_roles("admin"))) -> list[UserOut]:
    with db() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [row_to_user(user) for user in users]


@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreate,
    _: sqlite3.Row = Depends(require_roles("admin")),
) -> UserOut:
    with db() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, ?)
                """,
                (request.username, hash_password(request.password), request.role),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在") from exc
        user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_user(user)


@app.get("/bills", response_model=list[BillOut])
def list_bills(_: sqlite3.Row = Depends(require_roles("admin", "accountant", "auditor"))) -> list[BillOut]:
    with db() as conn:
        bills = conn.execute("SELECT * FROM bills ORDER BY id DESC").fetchall()
    return [BillOut(**dict(bill)) for bill in bills]


@app.post("/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED)
def create_bill(
    request: BillCreate,
    current_user: sqlite3.Row = Depends(require_roles("admin", "accountant")),
) -> BillOut:
    occurred_at = request.occurred_at or as_iso(utc_now())
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bills (amount, description, category, occurred_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request.amount,
                request.description,
                request.category,
                occurred_at,
                current_user["id"],
            ),
        )
        bill = conn.execute("SELECT * FROM bills WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return BillOut(**dict(bill))


@app.get("/health")
def health() -> StatusResponse:
    return StatusResponse(status="ok")
