"""Firebase Authentication over its REST API (LAN worlds). The game signs in with e-mail and
password, keeps the refresh token in session.json so the next start needs no typing, and
hands a fresh ID token to each world it joins (POST /auth/firebase on that world).

Every call goes through the game's non-blocking Api (absolute URLs), so the window never freezes.
"""
from __future__ import annotations

import os
import time

_EMU = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()   # Firebase Auth Emulator, for testing
IDT = (f"http://{_EMU}/identitytoolkit.googleapis.com/v1/accounts:" if _EMU
       else "https://identitytoolkit.googleapis.com/v1/accounts:")
TOKEN_URL = f"http://{_EMU}/securetoken.googleapis.com/v1/token" if _EMU else "https://securetoken.googleapis.com/v1/token"

MESSAGES = {
    "EMAIL_EXISTS": "Email này đã có tài khoản. Hãy đăng nhập.",
    "EMAIL_NOT_FOUND": "Sai email hoặc mật khẩu.",
    "INVALID_PASSWORD": "Sai email hoặc mật khẩu.",
    "INVALID_LOGIN_CREDENTIALS": "Sai email hoặc mật khẩu.",
    "INVALID_EMAIL": "Email không hợp lệ.",
    "MISSING_EMAIL": "Hãy nhập email.",
    "MISSING_PASSWORD": "Hãy nhập mật khẩu.",
    "WEAK_PASSWORD": "Mật khẩu cần ít nhất 6 ký tự.",
    "USER_DISABLED": "Tài khoản này đã bị khóa.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Thử quá nhiều lần, chờ một lúc rồi thử lại nhé.",
    "TOKEN_EXPIRED": "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.",
    "INVALID_REFRESH_TOKEN": "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.",
    "USER_NOT_FOUND": "Tài khoản không còn tồn tại, hãy đăng ký lại.",
    "OPERATION_NOT_ALLOWED": "Dự án Firebase chưa bật đăng nhập bằng Email/Password.",
    "PASSWORD_LOGIN_DISABLED": "Dự án Firebase chưa bật đăng nhập bằng Email/Password.",
    "CONFIGURATION_NOT_FOUND": "Dự án Firebase chưa bật Authentication (vào Firebase Console → Authentication "
                               "→ Get started → bật Email/Password).",
    "API_KEY_INVALID": "API key Firebase không đúng (xem firebase_api_key trong config.json).",
    "network": "Không kết nối được Firebase. Cần Internet để đăng nhập.",
}


def message_vi(err) -> str:
    code = getattr(err, "code", "")
    if code in MESSAGES:
        return MESSAGES[code]
    if code == "API" or str(code).startswith("API_KEY"):   # "API key not valid. Please pass a valid API key."
        return MESSAGES["API_KEY_INVALID"]
    return getattr(err, "message_vi", "") or "Đăng nhập Firebase thất bại."


class FirebaseAuth:
    def __init__(self, api, session, api_key: str):
        self.api, self.session, self.key = api, session, api_key

    # ------------------------------------------------------------ state
    @property
    def data(self) -> dict:
        return self.session.data.get("firebase") or {}

    @property
    def signed_in(self) -> bool:
        return bool(self.data.get("refresh_token"))

    @property
    def email(self) -> str:
        return self.data.get("email", "")

    @property
    def uid(self) -> str:
        return self.data.get("uid", "")

    def _store(self, uid: str, email: str, id_token: str, refresh: str, expires_in) -> None:
        self.session.save(firebase={"uid": uid, "email": email, "id_token": id_token, "refresh_token": refresh,
                                    "expires_at": time.time() + int(expires_in or 3600)})

    def sign_out(self) -> None:
        self.session.data.pop("firebase", None)
        self.session.save()

    # ------------------------------------------------------------ calls
    def _signed(self, ok, err):
        def done(r):
            self._store(r["localId"], r.get("email", ""), r["idToken"], r["refreshToken"], r.get("expiresIn"))
            ok(r)
        return done, lambda e: err(message_vi(e))

    def sign_in(self, email: str, password: str, ok, err) -> None:
        done, fail = self._signed(ok, err)
        self.api.post(f"{IDT}signInWithPassword?key={self.key}",
                      {"email": email, "password": password, "returnSecureToken": True}, done, fail, retries=1)

    def sign_up(self, email: str, password: str, ok, err) -> None:
        done, fail = self._signed(ok, err)
        self.api.post(f"{IDT}signUp?key={self.key}",
                      {"email": email, "password": password, "returnSecureToken": True}, done, fail, retries=1)

    def send_reset(self, email: str, ok, err) -> None:
        self.api.post(f"{IDT}sendOobCode?key={self.key}", {"requestType": "PASSWORD_RESET", "email": email},
                      lambda r: ok(), lambda e: err(message_vi(e)), retries=1)

    def id_token(self, ok, err) -> None:
        """A valid ID token: the saved one if it has 5 more minutes, else a refreshed one."""
        d = self.data
        if not d.get("refresh_token"):
            err(MESSAGES["TOKEN_EXPIRED"])
            return
        if d.get("id_token") and d.get("expires_at", 0) - time.time() > 300:
            ok(d["id_token"])
            return

        def done(r):
            self._store(r.get("user_id", d.get("uid", "")), d.get("email", ""), r["id_token"], r["refresh_token"],
                        r.get("expires_in"))
            ok(r["id_token"])

        def fail(e):
            if getattr(e, "code", "") in ("TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_NOT_FOUND", "USER_DISABLED"):
                self.sign_out()
            err(message_vi(e))
        self.api.post(f"{TOKEN_URL}?key={self.key}", {"grant_type": "refresh_token", "refresh_token": d["refresh_token"]},
                      done, fail, retries=1)
