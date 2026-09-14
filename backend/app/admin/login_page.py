"""Página HTML de login para admins.

Herramienta interna: sirve un formulario simple que hace POST al endpoint
/api/v1/auth/login con `credentials: include` y, si va bien, redirige al
dashboard. El navegador guarda la cookie httpOnly y a partir de ahí el
panel funciona.

Cuando llegue Fase 8 (UI moderna), esta página se reemplaza por el login
real del frontend.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["admin-login"])


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ELI — Acceso admin</title>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, sans-serif; background: #0f1117; color: #e5e7eb;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 20px;
  }
  .card {
    width: 100%; max-width: 380px;
    background: #161b22; border: 1px solid #1f2937; border-radius: 12px;
    padding: 32px 28px;
  }
  h1 { margin: 0 0 4px; font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
  h1 span { color: #6b7280; font-weight: 400; margin-left: 6px; }
  p.sub { color: #9ca3af; font-size: 13px; margin: 0 0 24px; }
  label { display: block; margin: 14px 0 6px; font-size: 13px; color: #d1d5db; }
  input {
    width: 100%; padding: 10px 12px; border: 1px solid #30363d;
    background: #0d1117; color: #e5e7eb; border-radius: 6px;
    font-size: 14px; font-family: inherit; outline: none;
    transition: border-color .15s;
  }
  input:focus { border-color: #58a6ff; }
  button {
    width: 100%; margin-top: 22px; padding: 11px;
    background: #238636; color: white; border: 0; border-radius: 6px;
    font-size: 14px; font-weight: 500; cursor: pointer;
    font-family: inherit; transition: background .15s;
  }
  button:hover { background: #2ea043; }
  button:disabled { background: #30363d; cursor: not-allowed; }
  .msg { margin-top: 16px; padding: 10px 12px; border-radius: 6px;
    font-size: 13px; display: none; }
  .msg.error { background: #7f1d1d; color: #fca5a5; display: block; }
  .msg.ok { background: #064e3b; color: #6ee7b7; display: block; }
  .hint { margin-top: 20px; color: #6b7280; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<form class="card" id="login-form" autocomplete="off">
  <h1>ELI<span>· Admin</span></h1>
  <p class="sub">Acceso al panel administrativo</p>

  <label for="email">Email</label>
  <input id="email" name="email" type="email" required autofocus>

  <label for="password">Contraseña</label>
  <input id="password" name="password" type="password" required>

  <button type="submit" id="submit">Entrar</button>
  <div class="msg" id="msg"></div>
  <div class="hint">Sesión cookie httpOnly · caduca en 30 días</div>
</form>

<script>
const form = document.getElementById("login-form");
const msg = document.getElementById("msg");
const submit = document.getElementById("submit");

function show(text, cls) {
  msg.textContent = text;
  msg.className = "msg " + cls;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  submit.disabled = true;
  msg.className = "msg";
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  try {
    const r = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (r.status === 200) {
      const user = await r.json();
      show("Bienvenido, " + user.name + ". Redirigiendo…", "ok");
      setTimeout(() => { window.location.href = "/api/v1/admin/dashboard"; }, 600);
      return;
    }
    if (r.status === 401) {
      show("Credenciales incorrectas.", "error");
    } else if (r.status === 429) {
      show("Demasiados intentos. Espera un minuto.", "error");
    } else {
      const body = await r.json().catch(() => ({}));
      show(body.detail || ("Error HTTP " + r.status), "error");
    }
  } catch (err) {
    show("Error de red: " + err.message, "error");
  } finally {
    submit.disabled = false;
  }
});
</script>
</body>
</html>
"""


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def admin_login_page() -> HTMLResponse:
    """Página HTML de login para admins. El JS hace el POST real a /auth/login."""
    return HTMLResponse(content=_LOGIN_HTML)