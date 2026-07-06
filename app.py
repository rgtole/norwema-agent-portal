import os
import json
import datetime
import secrets
import logging
from typing import Dict, Any, List, Optional
import contextvars

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import google.generativeai as genai

import db_manager
import mcp_server_db

# ─── Logging & Setup ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NorwemaPortal")


def _clean_api_key(key: str) -> str:
    if not key:
        return ""
    # Strip common PowerShell command artefacts
    if "-NoNewline" in key:
        key = key.replace("-NoNewline", "")
    # Remove carriage returns, newlines, and trailing/leading spaces
    return key.replace("\r", "").replace("\n", "").strip()


def _load_gemini_api_key_from_secrets() -> str:
    """
    Attempt to fetch GEMINI_API_KEY from GCP Secret Manager (latest version).
    Falls back to environment variables GEMINI_API_KEY / GOOGLE_API_KEY if unavailable.
    """
    try:
        from google.cloud import secretmanager
        import google.auth

        _, project_id = google.auth.default()
        if not project_id:
            raise RuntimeError("No GCP project detected.")

        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project_id}/secrets/GEMINI_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        key = response.payload.data.decode("UTF-8")
        cleaned = _clean_api_key(key)
        if cleaned:
            logger.info("Loaded Gemini API key from GCP Secret Manager (cleaned).")
            return cleaned
    except Exception as e:
        logger.info(f"Secret Manager not available ({e}); falling back to env vars.")

    raw_env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return _clean_api_key(raw_env_key)

app = FastAPI(
    title="NORWEMA — North West Marathi Association Portal",
    description="Refactored modern SPA portal with Firestore MCP and AI agents integration."
)

# ─── Auth Constants ──────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("NORWEMA_ADMIN_PASSWORD", "norwema_admin")
ADMIN_USERNAME = "admin"

# Detect if running in Google Cloud/Cloud Run vs local launch
is_local = "K_SERVICE" not in os.environ and "GAE_APPLICATION" not in os.environ
api_key = _load_gemini_api_key_from_secrets()

# ─── Configuration State ──────────────────────────────────────────────────────
CONFIG_STATE = {
    "api_key": api_key,
    "selected_model": "models/gemini-2.5-flash",
    "mock_agent": True if is_local else not bool(api_key),
    "stripe_secret_key": os.environ.get("STRIPE_SECRET_KEY") or ""
}

# Pre-configure genai if we already have a key at startup
if CONFIG_STATE["api_key"]:
    try:
        genai.configure(api_key=CONFIG_STATE["api_key"])
        logger.info("Gemini SDK configured with API key from startup.")
    except Exception:
        pass

# Ensure Database is initialized (GCP or local fallback)
is_offline = db_manager.init_db()
logger.info(f"Database initialized. Offline local JSON fallback mode: {is_offline}")

# ─── Pydantic Models for Validation ─────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class ConfigUpdateRequest(BaseModel):
    api_key: Optional[str] = None
    selected_model: Optional[str] = None
    mock_agent: Optional[bool] = None
    stripe_secret_key: Optional[str] = None

class EventCreateRequest(BaseModel):
    title: str
    date: str
    description: Optional[str] = ""
    ticket_fee: Optional[float] = 25.0

class BlogCreateRequest(BaseModel):
    title: str
    author: str
    date: Optional[str] = None
    content: str

class SchemaCreateRequest(BaseModel):
    event_title: str
    fee: float

class RegistrationCreateRequest(BaseModel):
    event: str
    name: str
    email: str
    phone: Optional[str] = ""
    residence: Optional[str] = ""
    adults: int
    children: Optional[int] = 0
    total: float
    cultural_interest: str
    participant_names: Optional[str] = ""
    performance_type: Optional[str] = ""
    comments: Optional[str] = ""
    status: Optional[str] = "Pending Payment"

class RegistrationStatusUpdateRequest(BaseModel):
    status: str

class AgentExecuteRequest(BaseModel):
    agent: str
    command: str

# ─── Auth Verification Dependency ───────────────────────────────────────────
def verify_admin(request: Request):
    if not ADMIN_PASSWORD:
        logger.warning("Admin password environment variable NORWEMA_ADMIN_PASSWORD not configured.")
        raise HTTPException(status_code=500, detail="Admin password not configured on server.")
    
    password = request.headers.get("X-Admin-Password")
    if not password or not secrets.compare_digest(password.strip(), ADMIN_PASSWORD.strip()):
        raise HTTPException(status_code=401, detail="Unauthorized admin access.")
    return True

# ─── Context Logs Manager Middleware ────────────────────────────────────────
@app.middleware("http")
async def context_logs_middleware(request: Request, call_next):
    # Initialize empty request log list in request ContextVar context
    token = db_manager.mcp_logs_var.set([])
    try:
        response = await call_next(request)
        return response
    finally:
        # Reset ContextVar context
        db_manager.mcp_logs_var.reset(token)

# Helper to build API response payload enclosing request context logs
def build_api_response(result: Any) -> JSONResponse:
    logs = db_manager.mcp_logs_var.get() or []
    return JSONResponse({
        "status": "success",
        "result": result,
        "mcp_logs": logs
    })

# ─── Static Files & Image Serving ───────────────────────────────────────────

# Serve UI static asset files from static directory
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve root images directly
@app.get("/norwema_banner_v2.png")
def get_banner_v2():
    if os.path.exists("norwema_banner_v2.png"):
        return FileResponse("norwema_banner_v2.png")
    return FileResponse("norwema_banner.png")

@app.get("/norwema_banner.png")
def get_banner():
    if os.path.exists("norwema_banner.png"):
        return FileResponse("norwema_banner.png")
    raise HTTPException(status_code=404, detail="Banner not found.")

@app.get("/norwema_logo_new.png")
def get_logo_new():
    if os.path.exists("norwema_logo_new.png"):
        return FileResponse("norwema_logo_new.png")
    if os.path.exists("norwema_logo.jpg"):
        return FileResponse("norwema_logo.jpg")
    raise HTTPException(status_code=404, detail="Logo not found.")

@app.get("/norwema_logo.jpg")
def get_logo_jpg():
    if os.path.exists("norwema_logo.jpg"):
        return FileResponse("norwema_logo.jpg")
    raise HTTPException(status_code=404, detail="Logo not found.")

# Serve Skills definition files for view
@app.get("/api/skills/{skill_name}")
def get_skill_file(skill_name: str):
    skill_path = os.path.join("skills", skill_name)
    if os.path.exists(skill_path):
        return FileResponse(skill_path)
    raise HTTPException(status_code=404, detail=f"Skill file {skill_name} not found.")

# ─── Auth Endpoint ──────────────────────────────────────────────────────────
@app.post("/api/login")
def post_login(req: LoginRequest):
    if not ADMIN_PASSWORD:
        return JSONResponse({"status": "error", "message": "Admin password not configured on server."}, status_code=500)
    
    if req.username == ADMIN_USERNAME and secrets.compare_digest(req.password.strip(), ADMIN_PASSWORD.strip()):
        return {"status": "success", "message": "Authenticated successfully"}
    
    return JSONResponse({"status": "error", "message": "Invalid username or password."}, status_code=401)

# ─── Config Endpoints ────────────────────────────────────────────────────────
@app.get("/api/config")
def get_config():
    # Return active configs (hiding complete API Key for safety)
    form_schemas = db_manager.get_form_schemas()
    # Detect local launch
    is_local = "K_SERVICE" not in os.environ and "GAE_APPLICATION" not in os.environ
    return build_api_response({
        "has_key": len(CONFIG_STATE["api_key"]) > 0,
        "selected_model": CONFIG_STATE["selected_model"],
        "mock_agent": CONFIG_STATE["mock_agent"],
        "is_offline": is_offline,
        "is_local": is_local,
        "form_schemas": form_schemas,
        "has_stripe_key": len(CONFIG_STATE["stripe_secret_key"]) > 0
    })

@app.post("/api/config")
def post_config(req: ConfigUpdateRequest, admin_auth = Depends(verify_admin)):
    if req.api_key is not None:
        cleaned_key = _clean_api_key(req.api_key)
        CONFIG_STATE["api_key"] = cleaned_key
        if cleaned_key:
            try:
                genai.configure(api_key=cleaned_key)
            except Exception:
                pass
    if req.selected_model is not None:
        CONFIG_STATE["selected_model"] = req.selected_model
    if req.mock_agent is not None:
        CONFIG_STATE["mock_agent"] = req.mock_agent
    if req.stripe_secret_key is not None:
        CONFIG_STATE["stripe_secret_key"] = req.stripe_secret_key
        
    return build_api_response({"message": "Configuration updated successfully."})

# ─── MCP Tools Endpoint ──────────────────────────────────────────────────────
@app.get("/api/mcp/tools")
def get_mcp_tools(admin_auth = Depends(verify_admin)):
    return build_api_response(mcp_server_db.MCP_TOOLS)

# ─── Database REST Routes ─────────────────────────────────────────────────────

# Events
@app.get("/api/events")
def get_events():
    events = db_manager.get_events()
    return build_api_response(events)

@app.post("/api/events")
def post_event(req: EventCreateRequest, admin_auth = Depends(verify_admin)):
    event = db_manager.add_event(req.title, req.date, req.description)
    # Automatically provision form schema fee
    fee = req.ticket_fee if req.ticket_fee is not None else 25.0
    db_manager.add_form_schema(event["title"], fee)
    return build_api_response(event)

# Blogs/Stories
@app.get("/api/blogs")
def get_blogs():
    blogs = db_manager.get_blogs()
    return build_api_response(blogs)

@app.post("/api/blogs")
def post_blog(req: BlogCreateRequest, admin_auth = Depends(verify_admin)):
    date_val = req.date or datetime.datetime.now().strftime("%B %Y")
    blog = db_manager.add_blog(req.title, req.author, date_val, req.content)
    return build_api_response(blog)

# Registrations
@app.get("/api/registrations")
def get_registrations(admin_auth = Depends(verify_admin)):
    regs = db_manager.get_registrations()
    # Sort by timestamp/ID descending
    try:
        regs = sorted(regs, key=lambda x: int(x.get("id", 0)), reverse=True)
    except Exception:
        pass
    return build_api_response(regs)

@app.post("/api/registrations")
def post_registration(req: RegistrationCreateRequest):
    regs = db_manager.get_registrations()
    next_id = len(regs)
    
    reg_data = req.dict()
    reg_data["id"] = next_id
    
    db_manager.add_registration(reg_data)
    return build_api_response(reg_data)

@app.post("/api/payments/create-checkout-session")
def create_checkout_session(req: RegistrationCreateRequest, request: Request):
    regs = db_manager.get_registrations()
    next_id = len(regs)
    
    reg_data = req.dict()
    reg_data["id"] = next_id
    reg_data["status"] = "Pending Payment"
    
    db_manager.add_registration(reg_data)
    
    stripe_key = CONFIG_STATE.get("stripe_secret_key", "").strip()
    # Use base_url (derived from Host header) — same-origin fetch calls do NOT
    # send an Origin header, so request.headers.get("origin") would return None.
    origin = str(request.base_url).rstrip("/")

    # Stripe rejects unit_amount of 0 — validate total before attempting API call
    if reg_data.get("total", 0) <= 0:
        # For free events/registrations, skip Stripe payment process and complete immediately
        db_manager.update_registration_status(next_id, "Paid")
        free_url = f"{origin}/api/payments/success?session_id=free_{secrets.token_hex(8)}&reg_id={next_id}"
        return build_api_response({"checkout_url": free_url, "mock": True})
    
    if stripe_key and stripe_key.startswith("sk_"):
        try:
            import stripe
            stripe.api_key = stripe_key
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': f"Registration: {reg_data['event']}",
                            'description': f"Attendees: {reg_data['adults']} adults, {reg_data['children']} children. Name: {reg_data['name']}",
                        },
                        'unit_amount': int(reg_data['total'] * 100),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f"{origin}/api/payments/success?session_id={{CHECKOUT_SESSION_ID}}&reg_id={next_id}",
                cancel_url=f"{origin}/?payment=cancelled&reg_id={next_id}",
                metadata={
                    "registration_id": str(next_id),
                    "event": reg_data["event"],
                    "email": reg_data["email"]
                }
            )
            return build_api_response({"checkout_url": session.url, "mock": False})
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session: {e}")
            mock_url = f"{origin}/mock-stripe-checkout?session_id=mock_{secrets.token_hex(8)}&reg_id={next_id}"
            return build_api_response({"checkout_url": mock_url, "mock": True, "error": str(e)})
    else:
        # Fall back to mock Stripe checkout if no key configured
        mock_url = f"{origin}/mock-stripe-checkout?session_id=mock_{secrets.token_hex(8)}&reg_id={next_id}"
        return build_api_response({"checkout_url": mock_url, "mock": True})

@app.get("/api/payments/success")
def payment_success_callback(session_id: str, reg_id: int):
    is_paid = False
    stripe_key = CONFIG_STATE.get("stripe_secret_key", "").strip()
    
    if session_id.startswith("mock_") or session_id.startswith("free_"):
        is_paid = True
    elif stripe_key and stripe_key.startswith("sk_"):
        try:
            import stripe
            stripe.api_key = stripe_key
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == 'paid':
                is_paid = True
        except Exception as e:
            logger.error(f"Error verifying Stripe session: {e}")
            
    if is_paid:
        db_manager.update_registration_status(reg_id, "Paid")
        regs = db_manager.get_registrations()
        reg = next((r for r in regs if str(r.get("id")) == str(reg_id)), None)
        
        event_esc = ""
        name_esc = ""
        email_esc = ""
        total_val = 0.0
        
        if reg:
            import urllib.parse
            event_esc = urllib.parse.quote(reg.get("event", ""))
            name_esc = urllib.parse.quote(reg.get("name", ""))
            email_esc = urllib.parse.quote(reg.get("email", ""))
            total_val = reg.get("total", 0.0)
            
        return HTMLResponse(content=f"""
            <html>
                <head>
                    <script>
                        window.location.href = "/?payment=success&reg_id={reg_id}&event={event_esc}&total={total_val}&name={name_esc}&email={email_esc}";
                    </script>
                </head>
                <body>
                    <p>Payment successful! Redirecting to portal...</p>
                </body>
            </html>
        """)
    else:
        return HTMLResponse(content=f"""
            <html>
                <head>
                    <script>
                        window.location.href = "/?payment=failed&reg_id={reg_id}";
                    </script>
                </head>
                <body>
                    <p>Payment verification failed. Redirecting...</p>
                </body>
            </html>
        """)

@app.get("/mock-stripe-checkout", response_class=HTMLResponse)
def get_mock_stripe_checkout(session_id: str, reg_id: int, request: Request):
    # Fetch the registration details to show on the checkout page
    regs = db_manager.get_registrations()
    reg = next((r for r in regs if str(r.get("id")) == str(reg_id)), None)
    
    if not reg:
        return HTMLResponse(content="<h3>Error: Registration not found</h3>", status_code=404)
        
    event = reg.get("event", "Event Registration")
    total = reg.get("total", 0.0)
    email = reg.get("email", "")
    name = reg.get("name", "")
    adults = reg.get("adults", 1)
    children = reg.get("children", 0)
    
    origin = str(request.base_url).rstrip("/")
    cancel_url = f"{origin}/?payment=cancelled&reg_id={reg_id}"
    success_url = f"/api/payments/success?session_id={session_id}&reg_id={reg_id}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stripe Checkout (Sandbox)</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            body {{
                background-color: #ffffff;
                display: flex;
                min-height: 100vh;
                color: #333333;
            }}
            .container {{
                display: flex;
                width: 100%;
                flex-wrap: wrap;
            }}
            .left-panel {{
                flex: 1.1;
                background-color: #1a1f36;
                color: #ffffff;
                padding: 60px 80px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-width: 320px;
            }}
            .right-panel {{
                flex: 1.2;
                background-color: #ffffff;
                padding: 60px 80px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                min-width: 320px;
            }}
            .back-btn {{
                color: rgba(255, 255, 255, 0.6);
                text-decoration: none;
                font-size: 0.88rem;
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 40px;
                transition: color 0.2s;
            }}
            .back-btn:hover {{
                color: #ffffff;
            }}
            .merchant-name {{
                font-size: 1.1rem;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.9);
                margin-bottom: 8px;
            }}
            .amount {{
                font-size: 3rem;
                font-weight: 700;
                margin-bottom: 24px;
            }}
            .event-details {{
                border-top: 1px solid rgba(255, 255, 255, 0.15);
                padding-top: 24px;
            }}
            .detail-row {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 12px;
                font-size: 0.95rem;
                color: rgba(255, 255, 255, 0.7);
            }}
            .detail-row.total {{
                border-top: 1px solid rgba(255, 255, 255, 0.15);
                padding-top: 12px;
                font-weight: 600;
                color: #ffffff;
            }}
            .badge-sandbox {{
                background-color: #f6a623;
                color: #ffffff;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                display: inline-block;
                margin-top: 20px;
                align-self: flex-start;
            }}
            .form-title {{
                font-size: 1.4rem;
                font-weight: 600;
                color: #1a1f36;
                margin-bottom: 24px;
            }}
            .form-group {{
                margin-bottom: 20px;
            }}
            .form-label {{
                display: block;
                font-size: 0.85rem;
                font-weight: 500;
                color: #4f5b66;
                margin-bottom: 6px;
            }}
            .form-input {{
                width: 100%;
                padding: 12px;
                border: 1px solid #e3e8ee;
                border-radius: 6px;
                font-size: 1rem;
                transition: border-color 0.2s, box-shadow 0.2s;
                background-color: #ffffff;
            }}
            .form-input:focus {{
                outline: none;
                border-color: #635bff;
                box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.15);
            }}
            .card-inputs {{
                display: flex;
                border: 1px solid #e3e8ee;
                border-radius: 6px;
                overflow: hidden;
            }}
            .card-inputs .form-input {{
                border: none;
                border-radius: 0;
            }}
            .card-number-wrapper {{
                flex: 2;
                border-right: 1px solid #e3e8ee;
                position: relative;
            }}
            .card-expiry-wrapper {{
                flex: 1;
                border-right: 1px solid #e3e8ee;
            }}
            .card-cvc-wrapper {{
                flex: 0.8;
            }}
            .btn-pay {{
                width: 100%;
                padding: 14px;
                background-color: #635bff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 1.05rem;
                font-weight: 600;
                cursor: pointer;
                transition: background-color 0.15s, transform 0.1s;
                margin-top: 10px;
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 10px;
            }}
            .btn-pay:hover {{
                background-color: #564ecb;
            }}
            .btn-pay:active {{
                transform: scale(0.99);
            }}
            .btn-pay:disabled {{
                background-color: #a3acb9;
                cursor: not-allowed;
            }}
            .spinner {{
                width: 20px;
                height: 20px;
                border: 3px solid rgba(255,255,255,0.3);
                border-radius: 50%;
                border-top-color: #ffffff;
                animation: spin 0.8s ease-in-out infinite;
                display: none;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            .footer-links {{
                margin-top: 30px;
                font-size: 0.78rem;
                color: #a3acb9;
                display: flex;
                justify-content: center;
                gap: 15px;
            }}
            .footer-links a {{
                color: #a3acb9;
                text-decoration: none;
            }}
            .footer-links a:hover {{
                color: #4f5b66;
            }}
            @media (max-width: 768px) {{
                .container {{
                    flex-direction: column;
                }}
                .left-panel {{
                    padding: 40px;
                }}
                .right-panel {{
                    padding: 40px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="left-panel">
                <div>
                    <a href="{cancel_url}" class="back-btn">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
                        </svg>
                        Back to NORWEMA
                    </a>
                    <div class="merchant-name">NORWEMA</div>
                    <div class="amount">£{total:.2f}</div>
                    
                    <div class="event-details">
                        <div class="detail-row">
                            <span>{event}</span>
                            <span>£{total:.2f}</span>
                        </div>
                        <div class="detail-row">
                            <span>Adults ({adults})</span>
                            <span>Included</span>
                        </div>
                        <div class="detail-row">
                            <span>Children ({children})</span>
                            <span>Free</span>
                        </div>
                        <div class="detail-row total">
                            <span>Total Due</span>
                            <span>£{total:.2f}</span>
                        </div>
                    </div>
                </div>
                
                <div class="badge-sandbox">Stripe Sandbox (Simulated)</div>
            </div>
            
            <div class="right-panel">
                <h3 class="form-title">Pay with card</h3>
                <form id="payment-form" onsubmit="handlePaymentSubmit(event)">
                    <div class="form-group">
                        <label class="form-label" for="email">Email address</label>
                        <input class="form-input" type="email" id="email" value="{email}" readonly style="background-color: #f8f9fa;">
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Card information</label>
                        <div class="card-inputs">
                            <div class="card-number-wrapper">
                                <input class="form-input" type="text" id="card-number" value="4242 4242 4242 4242" placeholder="Card number" required>
                            </div>
                            <div class="card-expiry-wrapper">
                                <input class="form-input" type="text" id="card-expiry" value="12 / 29" placeholder="MM / YY" required>
                            </div>
                            <div class="card-cvc-wrapper">
                                <input class="form-input" type="text" id="card-cvc" value="424" placeholder="CVC" required>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="cardname">Name on card</label>
                        <input class="form-input" type="text" id="cardname" value="{name}" placeholder="Jane Doe" required>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="country">Country or region</label>
                        <select class="form-input" id="country" style="background-color: #f8f9fa;">
                            <option value="GB">United Kingdom</option>
                            <option value="IN">India</option>
                            <option value="US">United States</option>
                        </select>
                    </div>
                    
                    <button class="btn-pay" type="submit" id="btn-pay">
                        <span class="spinner" id="pay-spinner"></span>
                        <span id="btn-text">Pay £{total:.2f}</span>
                    </button>
                </form>
                
                <div class="footer-links">
                    <span>Powered by <strong>stripe</strong></span>
                    <a href="#">Terms</a>
                    <a href="#">Privacy</a>
                </div>
            </div>
        </div>
        
        <script>
            function handlePaymentSubmit(e) {{
                e.preventDefault();
                const btn = document.getElementById('btn-pay');
                const spinner = document.getElementById('pay-spinner');
                const btnText = document.getElementById('btn-text');
                
                btn.disabled = true;
                spinner.style.display = 'block';
                btnText.innerText = 'Processing...';
                
                setTimeout(() => {{
                    window.location.href = "{success_url}";
                }}, 1500);
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.put("/api/registrations/{reg_id}")
def update_registration(reg_id: int, req: RegistrationStatusUpdateRequest, admin_auth = Depends(verify_admin)):
    success = db_manager.update_registration_status(reg_id, req.status)
    if success:
        return build_api_response({"status": "success", "message": f"Registration {reg_id} updated to {req.status}."})
    raise HTTPException(status_code=400, detail="Failed to update registration status.")

# Clean Database
@app.post("/api/admin/reset")
def reset_database(admin_auth = Depends(verify_admin)):
    db_manager.cleanup_db()
    return build_api_response({"message": "Database reset to defaults successfully."})


# ─── Offline/Mock Agent Logic ────────────────────────────────────────────────
def run_offline_agent(agent_name: str, command: str) -> dict:
    agent_name = agent_name.strip(" 📅✍️💾")
    command_lower = command.lower()
    reasoning_logs = []
    
    if agent_name == "Event Architect Agent":
        reasoning_logs.append("1. Reading `skills/EventPlannerSkill.md`...")
        title, date, desc, fee = "Ganesh Utsav", "August 2026", "Cultural planning meeting.", 25.0
        
        # NLP Parsing
        if "titled" in command_lower:
            parts = command.split("titled")
            title = parts[1].split("on")[0].split("with")[0].strip().strip("'\"")
        elif "event" in command_lower and len(command.split("event")) > 1:
            title = command.split("event")[1].split("on")[0].split("with")[0].strip().strip("'\"")
            
        if " on " in command_lower:
            date = command.split(" on ")[1].split("with")[0].split("desc")[0].strip().strip("'\"")
            
        if "description" in command_lower:
            desc = command.split("description")[1].split("fee")[0].strip().strip("'\"")
        elif "desc" in command_lower:
            desc = command.split("desc")[1].split("fee")[0].strip().strip("'\"")
            
        import re
        if "free" in command_lower and not re.search(r'(?:fee|cost|price|ticket)\s*(?:of\s*)?£?\d+', command_lower):
            fee = 0.0
        elif "fee" in command_lower:
            m = re.search(r'£?(\d+)', command.split("fee")[1])
            if m:
                fee = float(m.group(1))
                
        reasoning_logs.append(f"Parsed Parameters:\n   - Event Title: {title}\n   - Event Date: {date}\n   - Description: {desc}\n   - Ticket Fee: £{fee:.2f}")
        reasoning_logs.append("2. Running database conflict query...")
        
        try:
            # Query collection
            mcp_server_db.call_tool_client_side("query_collection", {"collection_name": "events"}, console_log_callback=db_manager.log_mcp_traffic)
            
            # Insert document
            doc_id = "".join(c for c in f"{title}-{date}".lower().replace(" ", "-") if c.isalnum() or c == "-")
            event_data = {
                "id": doc_id,
                "title": f"{title} ({date})" if date else title,
                "date": date,
                "description": desc
            }
            
            reasoning_logs.append(f"3. Committing Event via insert_document into events collection: doc_id={doc_id}")
            mcp_server_db.call_tool_client_side("insert_document", {
                "collection_name": "events",
                "doc_id": doc_id,
                "document_data": event_data
            }, console_log_callback=db_manager.log_mcp_traffic)
            
            reasoning_logs.append(f"4. Provisioning registration form schema: fee=£{fee:.2f}")
            mcp_server_db.call_tool_client_side("insert_document", {
                "collection_name": "form_schemas",
                "doc_id": event_data["title"],
                "document_data": {"active": True, "fee": fee}
            }, console_log_callback=db_manager.log_mcp_traffic)
            
            return {
                "message": f"✅ Event **{title}** scheduled on **{date}** with £{fee:.0f}/adult registration form.",
                "reasoning": "\n".join(reasoning_logs)
            }
        except Exception as e:
            return {
                "message": f"❌ Firestore MCP Server Error: {e}",
                "reasoning": "\n".join(reasoning_logs)
            }
            
    elif agent_name == "Cultural Blogger Agent":
        reasoning_logs.append("1. Reading `skills/MarathiCultureSkill.md`...")
        title, content = "Community Spotlight", "A celebration of Maharashtrian heritage."
        
        if "titled" in command_lower:
            title = command.split("titled")[1].split("content")[0].split("with")[0].strip().strip("'\"")
        if "content" in command_lower:
            content = command.split("content")[1].strip().strip("'\"")
            
        reasoning_logs.append(f"Parsed Parameters:\n   - Blog Title: {title}\n   - Blog Content: {content[:60]}...")
        reasoning_logs.append("2. Saving drafted story post to database...")
        
        try:
            import uuid
            doc_id = f"blog-{str(uuid.uuid4())[:8]}"
            blog_data = {
                "id": doc_id,
                "title": title,
                "author": "Cultural Blogger Agent",
                "date": datetime.datetime.now().strftime("%B %Y"),
                "content": content
            }
            
            mcp_server_db.call_tool_client_side("insert_document", {
                "collection_name": "blogs",
                "doc_id": doc_id,
                "document_data": blog_data
            }, console_log_callback=db_manager.log_mcp_traffic)
            
            return {
                "message": f"✅ Blog story **{title}** drafted and published to the Past Stories timeline.",
                "reasoning": "\n".join(reasoning_logs)
            }
        except Exception as e:
            return {
                "message": f"❌ Firestore MCP Server Error: {e}",
                "reasoning": "\n".join(reasoning_logs)
            }
            
    elif agent_name == "DB Connection Agent":
        reasoning_logs.append("1. Initiating connection audit...")
        if "clean" in command_lower or "reset" in command_lower:
            reasoning_logs.append("2. Running cleanup command...")
            db_manager.cleanup_db()
            return {
                "message": "✅ Database cleanup completed. Defaults restored.",
                "reasoning": "\n".join(reasoning_logs)
            }
        else:
            try:
                reasoning_logs.append("2. Querying metrics collections...")
                evs = mcp_server_db.call_tool_client_side("query_collection", {"collection_name": "events"}, console_log_callback=db_manager.log_mcp_traffic)
                bls = mcp_server_db.call_tool_client_side("query_collection", {"collection_name": "blogs"}, console_log_callback=db_manager.log_mcp_traffic)
                rgs = mcp_server_db.call_tool_client_side("query_collection", {"collection_name": "registrations"}, console_log_callback=db_manager.log_mcp_traffic)
                
                return {
                    "message": f"✅ Connected to database. Status: **{'Offline Fallback JSON' if is_offline else 'Cloud Firestore Active'}**.",
                    "db_metrics": {
                        "events": len(evs),
                        "blogs": len(bls),
                        "registrations": len(rgs)
                    },
                    "reasoning": "\n".join(reasoning_logs)
                }
            except Exception as e:
                return {
                    "message": f"❌ Metrics fetch failed: {e}",
                    "reasoning": "\n".join(reasoning_logs)
                }
                
    return {"message": "Unknown Agent", "reasoning": ""}

# ─── Tool function registry for manual dispatch ─────────────────────────────
def _build_tool_registry(agent_name: str) -> tuple:
    """
    Returns (tools_list, sys_instruction, fn_registry_dict) for a given agent.
    fn_registry_dict maps function name -> callable for manual dispatch fallback.
    """
    agent_name = agent_name.strip(" 📅✍️💾")
    
    def mcp_commit_event_to_db(title: str, date: str, desc: str, ticket_fee: float = 25.0) -> dict:
        """Create a new NORWEMA event and its registration form schema in the database.
        
        Args:
            title: The title of the event.
            date: The date of the event.
            desc: The description of the event.
            ticket_fee: Ticket fee per adult in GBP. Defaults to 25.0. Set to 0.0 for free events.
        """
        event_data = db_manager.add_event(title, date, desc)
        db_manager.add_form_schema(event_data["title"], ticket_fee)
        logger.info(f"[Tool] mcp_commit_event_to_db called: title={title}, date={date}, fee={ticket_fee}")
        return {"status": "success", "message": f"Event '{title} ({date})' added via Firestore MCP with fee £{ticket_fee:.2f}."}

    def mcp_create_registration_form(event_title: str, ticket_fee: float) -> dict:
        """Create or update the registration form schema for a given event."""
        db_manager.add_form_schema(event_title, ticket_fee)
        logger.info(f"[Tool] mcp_create_registration_form called: event_title={event_title}, fee={ticket_fee}")
        return {"status": "success", "message": f"Form for '{event_title}' at £{ticket_fee:.2f}/adult."}

    def mcp_draft_cultural_blog(title: str, content: str) -> dict:
        """Draft and publish a cultural blog post to the Past Stories timeline."""
        month_year = datetime.datetime.now().strftime("%B %Y")
        db_manager.add_blog(title=title, author="Cultural Blogger Agent", date=month_year, content=content)
        logger.info(f"[Tool] mcp_draft_cultural_blog called: title={title}")
        return {"status": "success", "message": f"Blog '{title}' saved to Firestore."}

    tools_map = {
        "Event Architect Agent": (
            [mcp_commit_event_to_db, mcp_create_registration_form],
            "You are the Event Architect Agent for NORWEMA (North West Marathi Association). "
            "When the user asks to create an event, you MUST call mcp_commit_event_to_db exactly once with the "
            "event title, date and description, then summarize the outcome for the user. Do NOT just describe what you would do — call the tool.",
            {"mcp_commit_event_to_db": mcp_commit_event_to_db,
             "mcp_create_registration_form": mcp_create_registration_form}
        ),
        "Cultural Blogger Agent": (
            [mcp_draft_cultural_blog],
            "You are the Cultural Blogger Agent. Draft stories using mcp_draft_cultural_blog exactly once, "
            "then summarize the outcome for the user. Prioritize calling the tool rather than chatting.",
            {"mcp_draft_cultural_blog": mcp_draft_cultural_blog}
        ),
        "DB Connection Agent": (
            [],
            "You explain Firestore collections and metrics.",
            {}
        ),
    }
    return tools_map.get(agent_name, ([], "", {}))


# Live Gemini Mode Agent Execution (uses google-genai SDK for reliable function calling)
def run_live_agent(agent_name: str, command: str, api_key: str, selected_model: str) -> dict:
    try:
        # google-genai (new unified SDK) has proper tool_config / function-call forcing
        from google import genai as new_genai
        from google.genai import types as gt

        # New SDK uses short model names — strip "models/" prefix if present
        model_name = selected_model.replace("models/", "")

        client = new_genai.Client(api_key=api_key)
        tools_list, sys_instr, fn_registry = _build_tool_registry(agent_name)

        safe_command = command.strip()
        if not safe_command:
            return {"message": "❌ Empty command received. Please provide a prompt.", "reasoning": ""}

        reasoning_logs = []
        tool_results_dispatched = []

        def _make_config(force_tool: bool, disable_tools: bool = False) -> gt.GenerateContentConfig:
            """Build GenerateContentConfig, optionally forcing a tool call (mode=ANY) or disabling it (mode=NONE)."""
            cfg: dict = {}
            if sys_instr:
                cfg["system_instruction"] = sys_instr
            if tools_list:
                cfg["tools"] = tools_list
                if disable_tools:
                    mode = "NONE"
                elif force_tool:
                    mode = "ANY"
                else:
                    mode = "AUTO"
                cfg["tool_config"] = gt.ToolConfig(
                    function_calling_config=gt.FunctionCallingConfig(mode=mode)
                )
            return gt.GenerateContentConfig(**cfg)

        # ── Agentic loop ─────────────────────────────────────────────────────
        contents: list = [safe_command]
        response = None
        MAX_TOOL_ROUNDS = 5

        for _round in range(MAX_TOOL_ROUNDS):
            # Force tool call on first round when agent has tools; AUTO afterwards
            force = (_round == 0 and bool(tools_list))
            # Disable tools if one or more tools were already successfully executed
            disable = bool(tool_results_dispatched)
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=_make_config(force_tool=force, disable_tools=disable)
            )
            logger.info(f"[LiveAgent] Round {_round}: response parts count = "
                        f"{len(response.candidates[0].content.parts) if response.candidates else 0}")

            # Collect function_call parts (skip empty-name artefacts from thinking models)
            function_calls_this_round = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if getattr(part, "function_call", None)
                and getattr(part.function_call, "name", "")
            ]

            if not function_calls_this_round:
                break  # Model returned text — we're done

            # Append model turn to conversation history
            contents.append(response.candidates[0].content)

            # Execute each function and build function-response parts
            fn_response_parts = []
            for fc in function_calls_this_round:
                fn_name = fc.name
                fn_args = dict(fc.args)
                reasoning_logs.append(f"🔍 MCP Call: `{fn_name}` with args: {json.dumps(fn_args)}")
                logger.info(f"[LiveAgent] Dispatching tool: {fn_name}({fn_args})")

                if fn_name in fn_registry:
                    try:
                        fn_result = fn_registry[fn_name](**fn_args)
                        tool_results_dispatched.append(fn_name)
                    except Exception as tool_err:
                        fn_result = {"status": "error", "message": str(tool_err)}
                        logger.error(f"[LiveAgent] Tool {fn_name} raised: {tool_err}")
                else:
                    fn_result = {"status": "error", "message": f"Unknown tool: {fn_name}"}
                    logger.warning(f"[LiveAgent] Unknown tool requested: {fn_name}")

                fn_response_parts.append(
                    gt.Part(
                        function_response=gt.FunctionResponse(
                            name=fn_name,
                            response={"result": fn_result}
                        )
                    )
                )

            # Append tool results as a user turn and continue
            contents.append(gt.Content(role="user", parts=fn_response_parts))

        # ── Extract final text ────────────────────────────────────────────────
        output_text = ""
        if response:
            try:
                output_text = response.text
            except Exception:
                pass

        if not output_text:
            if tool_results_dispatched:
                output_text = (
                    f"✅ Done. Tools called: {', '.join(tool_results_dispatched)}. "
                    "The database has been updated."
                )
            else:
                output_text = "No direct text returned by the agent."

        return {
            "message": output_text,
            "reasoning": "\n".join(reasoning_logs) if reasoning_logs
                         else "General conversation. No MCP database tools triggered."
        }

    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower():
            return {
                "message": "❌ Live API quota exceeded. Switch to Mock Mode or try again later.",
                "reasoning": f"Gemini API Quota Error: {err}"
            }
        elif "key" in err.lower() or "invalid" in err.lower():
            return {
                "message": "❌ Invalid Gemini API key. Check settings or switch to Mock Mode.",
                "reasoning": f"Gemini API Key Error: {err}"
            }
        return {
            "message": f"❌ Live Gemini Agent Error: {err}",
            "reasoning": f"Gemini Execution Error: {err}"
        }


# Agent Execution REST Endpoint
@app.post("/api/agent/execute")
def execute_agent(req: AgentExecuteRequest, admin_auth = Depends(verify_admin)):
    # Validate inputs are non-empty before dispatching
    if not req.command or not req.command.strip():
        return JSONResponse(
            {"status": "error", "message": "Agent command must not be empty. Please enter a prompt."},
            status_code=400
        )
    if not req.agent or not req.agent.strip():
        return JSONResponse(
            {"status": "error", "message": "No agent selected."},
            status_code=400
        )

    # Run in Mock or Live mode depending on CONFIG_STATE
    if CONFIG_STATE["mock_agent"]:
        result = run_offline_agent(req.agent, req.command)
    else:
        # Run live model
        api_key = CONFIG_STATE["api_key"]
        if not api_key or not api_key.strip():
            return JSONResponse(
                {"status": "error", "message": "No Gemini API key configured. Please enter your API key on the Agents page."},
                status_code=400
            )
        result = run_live_agent(req.agent, req.command.strip(), api_key, CONFIG_STATE["selected_model"])
        
    # Inject current request context logs count
    current_logs = db_manager.mcp_logs_var.get() or []
    result["logs_count"] = len(current_logs)
    
    return build_api_response(result)


# ─── Catch-all Serve SPA ────────────────────────────────────────────────────
@app.get("/{path:path}", response_class=HTMLResponse)
def catch_all(request: Request, path: str):
    # If API path is requested but not matched, return 404
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
        
    # Otherwise, return index.html for frontend routing
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h3>Norwema Portal: index.html not found</h3>", status_code=404)
