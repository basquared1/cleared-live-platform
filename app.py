import os
import json
import hmac
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from functools import wraps

import re
import io
import base64
import anthropic as _anthropic
import requests as http_requests
from docx_builder import build_docx
from dotenv import load_dotenv
import click
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, send_file, Response,
)
from sqlalchemy import text as sa_text
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _gph

def generate_password_hash(s):
    return _gph(s, method="pbkdf2:sha256")

from models import (
    db, Platform, Submission, ClearanceItem, SubmissionDocument,
    WebhookDelivery, PlatformUser, AdminUser, ClearanceGuideline, Invite,
    CLEARANCE_TEMPLATES, PRICING_TIERS, PROJECT_TYPE_LABELS,
    TERRITORY_LABELS, INTENDED_USE_OPTIONS,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Platform form configuration presets
# Each preset defines the intake form defaults AND internal negotiation positions.
# Positions are ordered primary → fallback; BA team uses them as negotiating parameters.
# ---------------------------------------------------------------------------
FORM_PRESETS = {
    "streaming_standard": {
        "label": "Streaming Platform Standard",
        "description": "Worldwide streaming, locked — e.g. Spotify, Apple Music, Amazon Music",
        "territory": "worldwide", "territory_locked": True,
        "intended_use": ["streaming"], "intended_use_locked": True,
        "positions": [
            {"rank": 1, "label": "Primary",    "territory": "worldwide",      "uses": ["streaming"], "term": "perpetuity", "notes": "Standard ask. Worldwide streaming in perpetuity. Do not go below without approval."},
            {"rank": 2, "label": "Fallback 1", "territory": "worldwide",      "uses": ["streaming"], "term": "5_years",    "notes": "Acceptable with auto-renewal clause in contract."},
            {"rank": 3, "label": "Fallback 2", "territory": "north_america",  "uses": ["streaming"], "term": "3_years",    "notes": "Last resort. Flag for VP approval before accepting."},
        ],
    },
    "label_all_media": {
        "label": "Label Standard — All Media WW in Perp",
        "description": "All media worldwide in perpetuity, excl. theatrical & commercials — e.g. Sony, Warner, UMG",
        "territory": "worldwide", "territory_locked": True,
        "intended_use": ["streaming", "broadcast", "home_video", "social", "promotional"], "intended_use_locked": False,
        "positions": [
            {"rank": 1, "label": "Primary",    "territory": "worldwide",      "uses": ["streaming", "broadcast", "home_video", "social", "promotional"], "term": "perpetuity", "notes": "All media WW in perp, excl. theatrical and commercials. Be specific — do not grant 'All Media' as a catch-all."},
            {"rank": 2, "label": "Fallback 1", "territory": "worldwide",      "uses": ["streaming", "broadcast", "home_video"],                          "term": "perpetuity", "notes": "Drop social and promotional if rights holder pushes back. Still insist on perp."},
            {"rank": 3, "label": "Fallback 2", "territory": "worldwide",      "uses": ["streaming", "broadcast"],                                         "term": "5_years",    "notes": "Minimum acceptable. Must include renewal option and revert clause if not renewed within 60 days."},
        ],
    },
    "svod_standard": {
        "label": "SVOD / Streaming + Broadcast",
        "description": "Streaming and broadcast worldwide — e.g. Netflix, HBO Max, Hulu",
        "territory": "worldwide", "territory_locked": True,
        "intended_use": ["streaming", "broadcast"], "intended_use_locked": True,
        "positions": [
            {"rank": 1, "label": "Primary",    "territory": "worldwide",      "uses": ["streaming", "broadcast"], "term": "perpetuity", "notes": "WW streaming and broadcast in perpetuity. Standard for SVOD platforms."},
            {"rank": 2, "label": "Fallback 1", "territory": "worldwide",      "uses": ["streaming", "broadcast"], "term": "5_years",    "notes": "Accept with auto-renewal. Do not accept without renewal provision."},
            {"rank": 3, "label": "Fallback 2", "territory": "north_america",  "uses": ["streaming", "broadcast"], "term": "3_years",    "notes": "Territory restriction acceptable only for initial window — must include right of first refusal for WW expansion."},
        ],
    },
    "social_standard": {
        "label": "Social Platform Standard",
        "description": "Streaming and social media worldwide — e.g. YouTube, TikTok, Meta",
        "territory": "worldwide", "territory_locked": True,
        "intended_use": ["streaming", "social"], "intended_use_locked": True,
        "positions": [
            {"rank": 1, "label": "Primary",    "territory": "worldwide", "uses": ["streaming", "social"], "term": "perpetuity", "notes": "WW streaming and social in perpetuity."},
            {"rank": 2, "label": "Fallback 1", "territory": "worldwide", "uses": ["streaming", "social"], "term": "3_years",    "notes": "Acceptable for initial deal with renewal option."},
        ],
    },
    "custom": {
        "label": "Custom — Configure Manually",
        "description": "Set your own territory, intended use, and negotiation positions",
        "territory": "", "territory_locked": False,
        "intended_use": [], "intended_use_locked": False,
        "positions": [],
    },
}

TERM_LABELS = {
    "perpetuity": "In Perpetuity",
    "5_years":    "5 Years",
    "3_years":    "3 Years",
    "2_years":    "2 Years",
    "1_year":     "1 Year",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

_db_url = os.getenv("DATABASE_URL", "sqlite:///platform.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_PERMANENT"] = True

db.init_app(app)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def current_platform_user():
    uid = session.get("platform_user_id")
    return PlatformUser.query.get(uid) if uid else None


def current_admin():
    uid = session.get("admin_user_id")
    return AdminUser.query.get(uid) if uid else None


def require_platform(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_platform_user():
            return redirect(url_for("platform_login"))
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_admin():
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "API key required", "hint": "Pass X-API-Key header"}), 401
        platform = Platform.query.filter_by(api_key=key, is_active=True).first()
        if not platform:
            return jsonify({"error": "Invalid or inactive API key"}), 401
        request.api_platform = platform
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Webhook delivery (background thread)
# ---------------------------------------------------------------------------

def deliver_webhook(platform_id, submission_id, event_type, payload_dict):
    """Fire webhook in a background thread. Thread-safe: captures all values."""
    platform = Platform.query.get(platform_id)
    if not platform or not platform.webhook_url:
        return

    payload_str = json.dumps(payload_dict)
    sig = hmac.new(
        platform.webhook_secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    webhook_url = platform.webhook_url

    delivery = WebhookDelivery(
        platform_id=platform_id,
        submission_id=submission_id,
        event_type=event_type,
        payload=payload_str,
    )
    db.session.add(delivery)
    db.session.commit()
    delivery_id = delivery.id

    def _send():
        with app.app_context():
            d = WebhookDelivery.query.get(delivery_id)
            if not d:
                return
            try:
                resp = http_requests.post(
                    webhook_url,
                    data=payload_str,
                    headers={
                        "Content-Type": "application/json",
                        "X-Cleared-Signature": f"sha256={sig}",
                        "X-Cleared-Event": event_type,
                    },
                    timeout=10,
                )
                d.response_status = resp.status_code
                d.response_body = resp.text[:1000]
                d.success = 200 <= resp.status_code < 300
            except Exception as exc:
                d.response_status = 0
                d.response_body = str(exc)[:500]
                d.success = False
            finally:
                db.session.commit()

    threading.Thread(target=_send, daemon=True).start()


def clearance_payload(sub):
    return {
        "event": "clearance_complete",
        "submission_token": sub.token,
        "project_type": sub.project_type,
        "title": sub.title,
        "artist_name": sub.artist_name,
        "submitter_email": sub.submitter_email,
        "cleared_at": sub.cleared_at.isoformat() if sub.cleared_at else None,
        "clearance_items": [i.to_api_dict() for i in sub.clearance_items],
    }


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    return {
        "platform_user": current_platform_user(),
        "admin_user": current_admin(),
        "now": datetime.utcnow(),
    }


# ---------------------------------------------------------------------------
# AI helpers
# ---------------------------------------------------------------------------

_CLP_SYSTEM_PROMPT = """You are a SENIOR music and entertainment attorney drafting clearance agreements on behalf of a streaming platform's Business Affairs department. You have 20+ years drafting against majors, sublabels, indies, publishers, promoters, venues, and unions. You write like a senior partner who bills by the result, not the page.

## Clearance philosophy — ENFORCE ON EVERY DRAFT
These are the non-negotiable structural rules for all clearance agreements on this platform:

1. **Party structure.** Every agreement is between the PRODUCER / SUBMITTER (the content provider seeking clearance) and the LICENSOR / RIGHTS HOLDER (the individual, label, publisher, union, venue, or other third party granting rights). The PLATFORM (Netflix, Amazon, YouTube, HBO, etc.) is NEVER a party to the underlying clearance agreement. The platform is the downstream assignee and beneficiary — it is referenced only in the assignment and indemnification clauses.

   **Entity rule — CRITICAL:** The Producer/Submitter is ALWAYS identified by their production company or special purpose vehicle (SPV) — NEVER by an individual's name. General liability 101: individuals do not contract directly; their production entity bears the exposure. Use the production company name from the submission (e.g., "Bliss Productions, LLC" not "Brian Alexander"). If only an individual name is provided with no company, write "[PRODUCTION COMPANY NAME]" as the party placeholder and flag it in a note at the top: *"Note to BA: Confirm production entity name before executing — individual names should not appear as the contracting party."* The individual may appear as an authorized signatory on behalf of the entity, but never as the party itself.

2. **Producer holds all liability.** The Producer/Submitter bears sole responsibility for obtaining all clearances required for the project. The Platform is fully indemnified from any and all third-party claims arising out of the content, the clearance process, or any breach of the underlying agreements. The indemnification runs one-way: Producer/Submitter → Platform. It is broad, covering attorneys' fees, costs, settlements, and judgments.

3. **Assignability.** Every license and agreement must be fully assignable without consent of the licensor. Include an explicit assignment clause: Producer/Submitter assigns all rights obtained under this agreement to the Platform, and the licensor consents to such assignment. The licensor shall look solely to the Producer/Submitter for payment and shall have no claim against the Platform.

4. **Chain of title.** The Producer/Submitter warrants and represents that chain of title is clear and unbroken from the original rights holder through to the Platform. The licensor warrants it has full authority to grant the rights conveyed, free of any adverse claim, lien, or encumbrance.

5. **Insurance.** Producer/Submitter must procure and maintain: (a) Errors & Omissions (E&O) insurance with limits no less than $[1,000,000] per occurrence / $[3,000,000] aggregate, covering the content for the full distribution term; and (b) Commercial General Liability insurance with limits no less than $[1,000,000] per occurrence. The Platform must be named as an additional insured on both policies. Certificates of insurance must be delivered to the Platform prior to distribution.

## Drafting philosophy — ENFORCE STRICTLY
Every sentence must earn its place. Plain English over legalese. If a clause can be cut without losing a right or a protection, cut it.

## Hard rules
- California law, Los Angeles County venue — one sentence, always.
- Rights grant: worldwide, in perpetuity, all media now known or hereafter devised — stated once, broadly.
- [BRACKETED PLACEHOLDERS] for every fee, date, and amount that is genuinely unknown. Do NOT bracket things you know.
- No triple asterisks, no stray underscores, no markdown code fences.
- The platform is never a signatory. The two signatories are always (1) Producer/Submitter and (2) the Licensor/Rights Holder.

## CANONICAL RULE — CLEAN DOCUMENT STANDARD
This document will be transmitted to the counterparty. It must read as professionally final.
STRICTLY PROHIBITED: research parentheticals like "(verify against ASCAP/BMI)", internal notes, fee estimates with "(market est.)".

## Signature anchors (DocuSign)
End the agreement with exactly two signature blocks:

AGREED AND ACCEPTED — PRODUCER / SUBMITTER:

/sign_submitter/
Print Name: /name_submitter/
Date: /date_submitter/


AGREED AND ACCEPTED — LICENSOR / RIGHTS HOLDER:

/sign_ba/
Print Name: /name_ba/
Date: /date_ba/


## What to include (and nothing else)
1. Parties — Producer/Submitter and Licensor/Rights Holder (one line each; platform named only as assignee)
2. Background — two sentences max
3. Grant of Rights — comprehensive, assignable, all media worldwide in perpetuity
4. Assignment to Platform — explicit; licensor consents; licensor's recourse is solely against Producer
5. Compensation — [AMOUNT]; payment timing in one sentence; licensor has no claim against Platform
6. Producer Indemnification of Platform — broad, one-way, covering all third-party claims
7. Insurance — E&O + CGL, Platform as additional insured, certificates required before distribution
8. Reps & Warranties — chain of title, authority to grant, no adverse claims (four bullets max)
9. Governing Law — one sentence
10. Miscellaneous — entire agreement + counterparts + amendment in one paragraph
11. Signature Page — two blocks as specified above"""


def _cached_system(system: str) -> list:
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def call_claude_document(system: str, user: str) -> str:
    """Generate a document with up to two API passes to avoid truncation."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")
    client = _anthropic.Anthropic(api_key=api_key)
    cached = _cached_system(system)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=cached,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text
    if msg.stop_reason == "max_tokens":
        continuation = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=cached,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": text},
                {"role": "user", "content": "Continue the agreement from exactly where you left off. Do not repeat any content. Complete all remaining sections and signature blocks."},
            ],
        )
        text += "\n" + continuation.content[0].text
    return text


def call_claude(system: str, user: str, max_tokens: int = 4000) -> str:
    """Call Claude for shorter outputs (deal points, outreach emails)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")
    client = _anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=_cached_system(system),
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _sub_context(sub):
    return (
        f"Project: {sub.title} ({sub.project_type_label})\n"
        f"Platform: {sub.platform.name}\n"
        f"Territory: {sub.territory_label}\n"
        f"Intended Use: {', '.join(sub.intended_use_list) if sub.intended_use_list else 'Streaming'}\n"
        f"Artist/Talent: {sub.artist_name or 'N/A'}\n"
        f"Label: {sub.label or 'N/A'}\n"
        f"Publisher: {sub.publisher or 'N/A'}\n"
        f"Event: {(sub.event_name or '') + (' at ' + sub.venue if sub.venue else '')} {('on ' + sub.event_date) if sub.event_date else ''}\n"
        f"Production Company: {sub.production_company or 'N/A'}\n"
        f"Submitter: {sub.submitter_name} ({sub.submitter_company or 'N/A'})\n"
        + (f"Setlist:\n" + "\n".join(f"  - {s}" for s in sub.setlist_list) if sub.setlist_list else "")
    )


def _build_clearance_doc_user_prompt(sub, item):
    is_label_waiver = (sub.platform.platform_mode == "label_waiver")

    if is_label_waiver:
        # For label platforms: draft a Conditional Label Waiver
        return (
            f"Draft a CONDITIONAL LABEL WAIVER on behalf of {sub.platform.name} (the label).\n\n"
            f"CONTEXT: The producer/submitter has represented that they have obtained all required clearances "
            f"for the project below. {sub.platform.name} is issuing this conditional label waiver — not as a "
            f"full clearance, but conditioned upon: (1) the producer having obtained all required clearances "
            f"from promoter, publisher, performers, and venue; (2) the producer maintaining E&O and general "
            f"liability insurance naming {sub.platform.name} as additional insured; and (3) the producer "
            f"indemnifying {sub.platform.name} from any third-party claim arising from the content.\n\n"
            f"CLEARANCE ITEM BEING WAIVED: {item.item_label}\n"
            f"PRODUCER / SUBMITTER: {sub.submitter_company or '[PRODUCTION COMPANY NAME]'}\n\n"
            f"PROJECT DETAILS:\n{_sub_context(sub)}\n\n"
            f"Draft the Conditional Label Waiver. It should: state what {sub.platform.name} is waiving "
            f"and under what conditions; require producer to represent all other clearances are in place; "
            f"be revocable if producer's representations are false; assign no rights from label to producer "
            f"beyond the limited waiver; and end with signature blocks for both parties."
        )

    return (
        f"Draft a professional {item.item_label} for the following project.\n\n"
        f"REPRESENTED PARTY: {sub.submitter_company or sub.submitter_name} on behalf of {sub.platform.name}\n\n"
        f"PROJECT DETAILS:\n{_sub_context(sub)}\n\n"
        f"CLEARANCE ITEM: {item.item_label}\n"
        + (f"Rights Holder / Counterparty: {item.party_name}\n" if item.party_name else "Rights Holder / Counterparty: [RIGHTS HOLDER]\n")
        + f"\nDraft the complete agreement now."
    )


_PUB_SEP = "\n===PUBLISHING REF===\n"

def _get_publishing_notes(sub):
    """Extract publishing reference section from ba_notes (stored after separator)."""
    if sub.ba_notes and _PUB_SEP in sub.ba_notes:
        return sub.ba_notes.split(_PUB_SEP, 1)[1].strip()
    return ""

def _set_publishing_notes(sub, general_notes, pub_notes):
    """Merge general notes and publishing reference back into ba_notes."""
    if pub_notes:
        sub.ba_notes = f"{general_notes}{_PUB_SEP}{pub_notes}".strip()
    else:
        sub.ba_notes = general_notes.strip() or None

def _get_ba_notes_only(sub):
    """Return only the general notes portion (before separator)."""
    if sub.ba_notes and _PUB_SEP in sub.ba_notes:
        return sub.ba_notes.split(_PUB_SEP, 1)[0].strip()
    return sub.ba_notes or ""


def _compute_publisher_groups(sub):
    """Scan all songs and group by publishing administrator."""
    groups = {}
    for idx, song in enumerate(sub.songs or []):
        title = song.get("title", f"Song {idx+1}")
        for w in (song.get("writers") or []):
            pub = w.get("publisher", "").strip()
            if not pub:
                continue
            if pub not in groups:
                groups[pub] = {
                    "publisher": pub,
                    "pro": w.get("pro", ""),
                    "songs": [],
                    "writers_in_group": set(),
                }
            entry = {"title": title, "idx": idx, "writer": w.get("name", ""), "split_pct": w.get("split_pct", 0)}
            if title not in [s["title"] for s in groups[pub]["songs"]]:
                groups[pub]["songs"].append(entry)
            groups[pub]["writers_in_group"].add(w.get("name", ""))
    # Convert sets to lists for JSON serialization
    for g in groups.values():
        g["writers_in_group"] = sorted(g["writers_in_group"])
    return groups


def generate_draft(sub, item):
    """Generate full agreement text using the attorney system prompt."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    user_prompt = _build_clearance_doc_user_prompt(sub, item)
    return call_claude_document(_CLP_SYSTEM_PROMPT, user_prompt)


def generate_outreach(sub, item):
    """Generate a clearance outreach email."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    salutation = item.party_name if item.party_name else "[Rights Holder]"
    system = (
        f"You are a business affairs professional at {sub.platform.name}. "
        "You draft concise, professional outreach emails to rights holders requesting clearance. "
        "Never include a subject line. Write 175–225 words. "
        "Do NOT use placeholder brackets like [Name] or [Rights Holder] — use the actual names provided."
    )
    user = (
        f"Write a professional clearance outreach email requesting a {item.item_label} for:\n"
        f"{_sub_context(sub)}\n\n"
        f"Start with 'Dear {salutation},'. State exactly what rights are being requested, "
        f"for which project and platform, reference event details, request a response within 5 business days, "
        f"and close professionally. Signature is: {sub.submitter_name or ''}"
        + (f"\n{sub.submitter_company}" if sub.submitter_company else "") + ". No 'on behalf of' in the closing."
    )
    return call_claude(system, user, max_tokens=600)


# ---------------------------------------------------------------------------
# DocuSign — JWT grant flow
# ---------------------------------------------------------------------------

_ds_env = os.getenv("DOCUSIGN_ENV", "demo")
DOCUSIGN_BASE_URL = (
    "https://na4.docusign.net/restapi" if _ds_env == "production"
    else "https://demo.docusign.net/restapi"
)
DOCUSIGN_AUTH_SERVER = (
    "account.docusign.com" if _ds_env == "production" else "account-d.docusign.com"
)


def _normalize_rsa_key(raw: str) -> str:
    """Handle RSA keys pasted with literal newlines, escaped \\n, or no newlines."""
    if not raw:
        return ""
    k = raw.strip().replace("\\n", "\n").replace("\r", "")
    if "\n" in k:
        return k
    m = re.match(
        r"(-+\s*BEGIN [A-Z ]+PRIVATE KEY\s*-+)(.+?)(-+\s*END [A-Z ]+PRIVATE KEY\s*-+)",
        k, re.DOTALL,
    )
    if not m:
        return k
    header, body, footer = m.group(1), m.group(2), m.group(3)
    body = re.sub(r"\s+", "", body)
    wrapped = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"{header}\n{wrapped}\n{footer}\n"


def docusign_configured():
    return bool(
        os.getenv("DOCUSIGN_INTEGRATION_KEY")
        and os.getenv("DOCUSIGN_USER_ID")
        and os.getenv("DOCUSIGN_ACCOUNT_ID")
        and os.getenv("DOCUSIGN_PRIVATE_KEY")
    )


def get_docusign_token():
    """Get DocuSign access token via JWT grant."""
    import jwt as pyjwt
    private_key = _normalize_rsa_key(os.getenv("DOCUSIGN_PRIVATE_KEY", ""))
    integration_key = os.getenv("DOCUSIGN_INTEGRATION_KEY")
    user_id = os.getenv("DOCUSIGN_USER_ID")
    now = datetime.utcnow()
    payload = {
        "iss": integration_key,
        "sub": user_id,
        "aud": DOCUSIGN_AUTH_SERVER,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "scope": "signature",
    }
    token = pyjwt.encode(payload, private_key, algorithm="RS256")
    resp = http_requests.post(
        f"https://{DOCUSIGN_AUTH_SERVER}/oauth/token",
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": token},
        timeout=15,
    )
    if not resp.ok:
        raise Exception(f"DocuSign token {resp.status_code}: {resp.text}")
    access_token = resp.json()["access_token"]

    # Resolve the account's region-correct base URI from userinfo (avoids hardcoded pod)
    base_uri = DOCUSIGN_BASE_URL
    try:
        ui = http_requests.get(
            f"https://{DOCUSIGN_AUTH_SERVER}/oauth/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=15,
        )
        if ui.ok:
            accounts = ui.json().get("accounts", [])
            target = os.getenv("DOCUSIGN_ACCOUNT_ID")
            acct = (next((a for a in accounts if a.get("account_id") == target), None)
                    or next((a for a in accounts if a.get("is_default")), None)
                    or (accounts[0] if accounts else None))
            if acct and acct.get("base_uri"):
                base_uri = acct["base_uri"].rstrip("/") + "/restapi"
    except Exception:
        pass
    return access_token, base_uri


def _ds_tab(anchor, **extra):
    t = {"anchorString": anchor, "anchorUnits": "pixels", "anchorXOffset": "0", "anchorYOffset": "0"}
    t.update(extra)
    return t


def _ds_text_tab(anchor, label):
    return {
        "anchorString": anchor, "anchorUnits": "pixels",
        "anchorXOffset": "0", "anchorYOffset": "0",
        "tabLabel": label, "required": "false", "width": "200",
    }


def _build_ds_tabs(content, sign_anchor, signer_name):
    """Build DocuSign tabs for one signer derived from anchor patterns in document content."""
    tabs = {"signHereTabs": [_ds_tab(sign_anchor)]}
    m = re.match(r"^/sign(_?)(.+)/$", sign_anchor)
    if not m:
        return tabs
    sep, suffix = m.group(1), m.group(2)

    def has(a): return a in (content or "")
    def a(field): return f"/{field}{sep}{suffix}/"

    if has(a("name")):
        tabs["fullNameTabs"] = [_ds_tab(a("name"), value=signer_name)]
    if has(a("date")):
        tabs["dateSignedTabs"] = [_ds_tab(a("date"))]
    if has(a("initial")):
        tabs["initialHereTabs"] = [_ds_tab(a("initial"))]

    text_tabs = []
    for field, label in [("addr", "Address"), ("phone", "Phone"), ("title", "Title"),
                          ("company", "Company"), ("text", "Text")]:
        if has(a(field)):
            text_tabs.append(_ds_text_tab(a(field), label))
    if text_tabs:
        tabs["textTabs"] = text_tabs

    return tabs


# Minimal Document-like proxy so build_docx works without the full enterprise model
class _DocxProxy:
    def __init__(self, title, content):
        self.title = title
        self.content = content
        self.status = "draft"


def send_to_docusign(sub, item):
    """Send signed .docx to submitter (signer 1) via DocuSign JWT flow."""
    if not docusign_configured():
        return None, "DocuSign not configured — set DOCUSIGN_INTEGRATION_KEY, DOCUSIGN_USER_ID, DOCUSIGN_ACCOUNT_ID, DOCUSIGN_PRIVATE_KEY in Render environment."

    draft_text = item.ai_draft or f"[AI draft pending for {item.item_label}]"
    doc_proxy = _DocxProxy(title=item.item_label, content=draft_text)
    try:
        doc_bytes = build_docx(doc_proxy)
    except Exception as e:
        return None, f"Failed to build .docx: {e}"

    doc_b64 = base64.b64encode(doc_bytes).decode()

    ds_signers = [
        {
            "email": sub.submitter_email,
            "name": sub.submitter_name,
            "recipientId": "1",
            "routingOrder": "1",
            "tabs": _build_ds_tabs(draft_text, "/sign_submitter/", sub.submitter_name),
        }
    ]
    if item.party_email and item.party_name:
        ds_signers.append({
            "email": item.party_email,
            "name": item.party_name,
            "recipientId": "2",
            "routingOrder": "2",
            "tabs": _build_ds_tabs(draft_text, "/sign_rights_holder/", item.party_name),
        })

    envelope = {
        "emailSubject": f"Please sign: {item.item_label} — {sub.title}",
        "emailBlurb": (
            f"{sub.submitter_company or sub.submitter_name} — {sub.title}\n\n"
            "Please review and sign the attached clearance agreement."
        ),
        "documents": [{
            "documentBase64": doc_b64,
            "name": item.item_label,
            "fileExtension": "docx",
            "documentId": "1",
        }],
        "recipients": {"signers": ds_signers},
        "emailSettings": {
            "replyEmailAddressOverride": "clear@cleared.live",
            "replyEmailNameOverride": "Cleared.live",
        },
        "status": "sent",
    }

    try:
        access_token, ds_base = get_docusign_token()
    except Exception as e:
        return None, f"DocuSign auth failed: {e}"

    account_id = os.getenv("DOCUSIGN_ACCOUNT_ID")
    resp = http_requests.post(
        f"{ds_base}/v2.1/accounts/{account_id}/envelopes",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=envelope,
        timeout=20,
    )
    if resp.status_code == 201:
        return resp.json().get("envelopeId"), None
    return None, f"DocuSign API error {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------------------
# Background agents
# ---------------------------------------------------------------------------

def _auto_draft_agent(sub_id):
    """Background thread: generate AI drafts for all clearance items on a new submission."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return
    with app.app_context():
        sub = Submission.query.get(sub_id)
        if not sub:
            return
        for item in sub.clearance_items:
            if not item.ai_draft:
                try:
                    item.ai_draft = generate_draft(sub, item)
                except Exception:
                    pass
        db.session.commit()


def _auto_outreach_agent(item_id):
    """Background thread: generate and optionally send outreach email when item → in_progress."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return
    with app.app_context():
        item = ClearanceItem.query.get(item_id)
        if not item or item.ai_outreach_body:
            return
        sub = item.submission
        try:
            body = generate_outreach(sub, item)
        except Exception:
            return
        if not body:
            return
        item.ai_outreach_body = body

        # Auto-send via Resend if party email is known
        party_email = item.party_email
        if party_email and os.getenv("RESEND_API_KEY"):
            try:
                import resend as _resend
                _resend.api_key = os.getenv("RESEND_API_KEY")
                _resend.Emails.send({
                    "from": f"{sub.submitter_name or sub.submitter_company or 'Clearance Team'} <clear@cleared.live>",
                    "to": [party_email],
                    "reply_to": _reply_address(item),
                    "subject": f"Clearance Request — {item.item_label} | {sub.title}",
                    "text": body,
                })
                item.ai_outreach_sent_at = datetime.utcnow()
            except Exception:
                pass

        # Seed the negotiation thread with the outreach we just sent
        if item.ai_outreach_sent_at and not item.negotiation_log:
            item.negotiation_log_add({
                "role": "outbound", "label": "Outreach email",
                "body": body, "ts": datetime.utcnow().isoformat(),
            })
            item.neg_state = "awaiting_reply"

        db.session.commit()


# ---------------------------------------------------------------------------
# AI Negotiation Agent
# ---------------------------------------------------------------------------

_NEGOTIATION_SYSTEM = """You are an autonomous business affairs negotiator handling a rights-clearance negotiation on behalf of a content producer. You do ALL the analytical and drafting work. A human submitter approves each message before it is sent, and a platform Business Affairs (BA) attorney gives the final clearance sign-off at the end.

Each turn you read the full negotiation thread plus the rights holder's latest message, decide where things stand, and draft the next move.

Hold these non-negotiable clearance principles — the platform requires them:
- The production company / SPV is always the contracting party, never an individual.
- The producer holds all liability; rights must be assignable to the distributing platform.
- Secure the broadest grant the deal terms allow (territory, term, media); narrow scope only when necessary to close.
- E&O and general liability insurance and a warranted chain of title are expected.

Negotiate firmly but professionally toward the platform's stated positions. Fall back from the primary position toward the fallback positions only as needed to close. If the rights holder agrees to terms, move to signature. If they raise a deal-breaker or demand something outside your authority, escalate to the BA rather than conceding.

Respond ONLY with valid JSON, no markdown, no prose outside the JSON object."""


def _fmt_negotiation_positions(positions):
    if not positions:
        return "No platform negotiation positions configured — use sound BA judgment and the deal terms."
    lines = []
    for p in positions:
        rank = p.get("rank") or p.get("label") or "Position"
        lines.append(
            f"- [{rank}] {p.get('label','')}: territory={p.get('territory','—')}, "
            f"uses={p.get('uses','—')}, term={p.get('term','—')}. {p.get('notes','')}".strip()
        )
    return "\n".join(lines)


def _run_negotiation(sub, item):
    """Analyze the thread and draft the next move. Returns a recommendation dict or None."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    positions = sub.platform.negotiation_positions if sub.platform else []
    dt = item.deal_terms or {}
    deal_str = (
        f"fee={dt.get('fee') or '—'} ({dt.get('fee_type') or '—'}), "
        f"territory={dt.get('territory') or '—'}, term={dt.get('term') or '—'}, "
        f"media={', '.join(dt.get('media_rights') or []) or '—'}, "
        f"MFN={'yes' if dt.get('mfn') else 'no'}. Notes: {dt.get('notes') or '—'}"
    )
    thread = item.negotiation_log or []
    thread_str = "\n\n".join(
        f"[{e.get('label') or e.get('role','message')}]\n{e.get('body','')}" for e in thread
    ) or "(no messages yet)"

    user = (
        f"CLEARANCE ITEM: {item.item_label}\n"
        f"RIGHTS HOLDER: {item.party_name or '[unknown]'} ({item.party_company or ''}) <{item.party_email or 'no email'}>\n\n"
        f"PROJECT:\n{_sub_context(sub)}\n\n"
        f"DEAL TERMS WE ARE SEEKING:\n{deal_str}\n\n"
        f"PLATFORM NEGOTIATION POSITIONS (primary first, then fallbacks):\n{_fmt_negotiation_positions(positions)}\n\n"
        f"NEGOTIATION THREAD SO FAR (oldest first):\n{thread_str}\n\n"
        "Analyze the rights holder's most recent message and decide the next move. "
        "Return a JSON object with EXACTLY these fields:\n"
        '{\n'
        '  "classification": "accepted" | "counter" | "question" | "declined" | "unclear",\n'
        '  "assessment": "2-3 sentences: where the negotiation stands and what they want",\n'
        '  "recommended_action": "send_for_signature" | "send_counter" | "answer_question" | "send_reply" | "escalate_to_ba",\n'
        '  "draft_reply": "the full email body to send next — no subject line, no placeholder brackets, use real names. If escalating, write a brief holding note.",\n'
        '  "deal_term_changes": "plain text describing any terms conceded or proposed this round, or \\"none\\"",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "rationale": "1-2 sentences on why this is the right move, referencing the platform positions"\n'
        '}\n'
        "Use recommended_action=send_for_signature ONLY when the material terms are agreed and the next step is signing. "
        "Use escalate_to_ba when they demand something outside the platform positions or a clear deal-breaker."
    )
    raw = call_claude(_NEGOTIATION_SYSTEM, user, max_tokens=1500)
    if not raw:
        return None
    import json as _json
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip().lstrip("json").strip() if clean.lstrip().startswith("json") else clean
        # Locate the JSON object
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        return _json.loads(clean)
    except Exception:
        return {
            "classification": "unclear",
            "assessment": "The AI response could not be parsed automatically. Review the rights holder's message and draft a reply manually, or regenerate.",
            "recommended_action": "send_reply",
            "draft_reply": "",
            "deal_term_changes": "none",
            "confidence": "low",
            "rationale": "Automatic parsing failed.",
            "raw": raw[:1500],
        }


def _negotiation_agent(item_id):
    """Background thread: analyze the latest reply and stage a recommendation."""
    with app.app_context():
        item = ClearanceItem.query.get(item_id)
        if not item:
            return
        sub = item.submission
        try:
            rec = _run_negotiation(sub, item)
        except Exception as e:
            app.logger.error(f"NEGOTIATION AGENT ERROR — {type(e).__name__}: {e}")
            rec = None
        if rec:
            item.ai_recommendation_save(rec)
            item.neg_state = "needs_approval"
        else:
            item.neg_state = "awaiting_reply"
        db.session.commit()


# ---------------------------------------------------------------------------
# Public — landing
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    platforms = Platform.query.filter_by(is_active=True).all()
    return render_template("index.html", platforms=platforms, pricing_tiers=PRICING_TIERS)


# ---------------------------------------------------------------------------
# Submitter — intake form
# ---------------------------------------------------------------------------

@app.route("/submit/<platform_slug>", methods=["GET", "POST"])
def submit(platform_slug):
    platform = Platform.query.filter_by(slug=platform_slug, is_active=True).first_or_404()

    if request.method == "POST":
        # Invite gate — POST
        invite_token = request.form.get("invite_token", "").strip()
        invite = Invite.query.filter_by(token=invite_token, platform_id=platform.id).first()
        if not invite or invite.is_used:
            flash("Invalid or already-used invite link. Please request a new invite.", "danger")
            return redirect(url_for("submit", platform_slug=platform_slug))

        ptype    = request.form.get("project_type", "live_music")
        ptier    = request.form.get("pricing_tier", "standard")
        price_c  = PRICING_TIERS.get(ptier, PRICING_TIERS["standard"])["price"] * 100

        sub = Submission(
            platform_id        = platform.id,
            project_type       = ptype,
            title              = request.form.get("title", "").strip(),
            artist_name        = request.form.get("artist_name", "").strip(),
            event_name         = request.form.get("event_name", "").strip(),
            venue              = request.form.get("venue", "").strip(),
            event_date         = request.form.get("event_date", "").strip(),
            setlist            = request.form.get("setlist", "").strip(),
            label              = request.form.get("label", "").strip(),
            publisher          = request.form.get("publisher", "").strip(),
            production_company = request.form.get("production_company", "").strip(),
            director           = request.form.get("director", "").strip(),
            intended_use       = ",".join(request.form.getlist("intended_use")),
            territory          = request.form.get("territory", "us"),
            notes              = request.form.get("notes", "").strip(),
            submitter_name     = request.form.get("submitter_name", "").strip(),
            submitter_company  = request.form.get("submitter_company", "").strip(),
            submitter_email    = request.form.get("submitter_email", "").strip(),
            submitter_phone    = request.form.get("submitter_phone", "").strip(),
            pricing_tier       = ptier,
            price_cents        = price_c,
            status             = "submitted",
        )
        db.session.add(sub)
        db.session.flush()

        # Label platforms use a review/waiver template instead of full clearance template
        if platform.platform_mode == "label_waiver":
            template_key = "live_music_label"
        else:
            template_key = ptype
        for item_def in CLEARANCE_TEMPLATES.get(template_key, CLEARANCE_TEMPLATES["live_music"]):
            db.session.add(ClearanceItem(
                submission_id = sub.id,
                item_key      = item_def["key"],
                item_label    = item_def["label"],
                priority      = item_def["priority"],
                status        = "pending",
            ))

        db.session.commit()

        # Mark invite as used
        invite.used_at      = datetime.utcnow()
        invite.submission_id = sub.id
        db.session.commit()

        # Auto-draft agent: generate AI drafts in background immediately after submission
        threading.Thread(target=_auto_draft_agent, args=(sub.id,), daemon=True).start()
        # For live music: AI finds setlist + publisher info in background
        if sub.project_type == "live_music":
            threading.Thread(target=_ai_fill_songs, args=(sub.id,), daemon=True).start()
        return redirect(url_for("submit_confirm", token=sub.token))

    # Invite gate — GET
    invite_token = request.args.get("invite", "").strip()
    invite = Invite.query.filter_by(token=invite_token, platform_id=platform.id).first() if invite_token else None
    if not invite or invite.is_used:
        return render_template("invite_required.html", platform=platform), 403

    # Public guidelines: keyed by project_type, only approved + show_to_submitters=True
    public_guidelines = {
        g.project_type: g.public_content
        for g in ClearanceGuideline.query.filter_by(
            platform_id=platform.id, status="approved", show_to_submitters=True
        ).all()
        if g.public_content
    }
    return render_template(
        "submit.html",
        platform=platform,
        invite=invite,
        pricing_tiers=PRICING_TIERS,
        project_type_labels=PROJECT_TYPE_LABELS,
        territory_labels=TERRITORY_LABELS,
        intended_use_options=INTENDED_USE_OPTIONS,
        clearance_templates=CLEARANCE_TEMPLATES,
        public_guidelines=public_guidelines,
    )


@app.route("/submit/confirm/<token>")
def submit_confirm(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    return render_template("submit_confirm.html", sub=sub)


# ---------------------------------------------------------------------------
# Submitter — token-based status tracker (no login)
# ---------------------------------------------------------------------------

@app.route("/track/<token>")
def track(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    return render_template("track.html", sub=sub,
                           publishing_notes=_get_publishing_notes(sub),
                           neg_positions=sub.platform.negotiation_positions,
                           actions=_scan_submitter_actions(sub))


@app.route("/track/<token>/save-publishing-notes", methods=["POST"])
def track_save_publishing_notes(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    pub = request.form.get("publishing_notes", "").strip()
    _set_publishing_notes(sub, _get_ba_notes_only(sub), pub)
    db.session.commit()
    flash("Publishing reference saved.", "success")
    return redirect(url_for("track", token=token) + "#songs-section")


# ---------------------------------------------------------------------------
# Submitter — token-authenticated action routes (no login required)
# ---------------------------------------------------------------------------

@app.route("/track/<token>/item/<int:item_id>/start", methods=["POST"])
def track_item_start(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.status = "in_progress"
    db.session.commit()
    threading.Thread(target=_auto_outreach_agent, args=(item.id,), daemon=True).start()
    # Generate agreement draft in background if missing
    if not item.ai_draft:
        threading.Thread(target=_auto_draft_agent, args=(sub.id,), daemon=True).start()
    return redirect(url_for("track", token=token))


@app.route("/track/<token>/item/<int:item_id>/upload", methods=["POST"])
def track_item_upload(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("track", token=token))
    doc = SubmissionDocument(
        submission_id     = sub.id,
        clearance_item_id = item.id,
        title             = f.filename,
        doc_type          = "signed_document",
        filename          = f.filename,
        file_data         = f.read(),
        mimetype          = f.mimetype or "application/octet-stream",
        uploaded_by       = sub.submitter_name,
    )
    db.session.add(doc)
    db.session.commit()
    return redirect(url_for("track", token=token))


@app.route("/track/<token>/item/<int:item_id>/submit-review", methods=["POST"])
def track_item_submit_review(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.status = "under_review"
    db.session.commit()
    # If all items are under_review, cleared, waived, or n_a — move submission to in_clearance
    all_done = all(
        i.status in ("under_review", "cleared", "waived", "n_a")
        for i in sub.clearance_items
    )
    if all_done and sub.status not in ("cleared", "rejected"):
        sub.status = "in_clearance"
        db.session.commit()
    return redirect(url_for("track", token=token))


@app.route("/track/<token>/item/<int:item_id>/gen-draft", methods=["POST"])
def track_item_gen_draft(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.ai_draft = None
    db.session.commit()
    draft = generate_draft(sub, item)
    if draft:
        item.ai_draft = draft
        db.session.commit()
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/save-outreach", methods=["POST"])
def track_item_save_outreach(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.ai_outreach_body = request.form.get("outreach_text", item.ai_outreach_body)
    db.session.commit()
    flash("Outreach email saved.", "success")
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/save-draft", methods=["POST"])
def track_item_save_draft(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.ai_draft = request.form.get("draft_text", item.ai_draft)
    db.session.commit()
    flash("Draft saved.", "success")
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/set-contact", methods=["POST"])
def track_item_set_contact(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.party_company = request.form.get("party_company", "").strip() or None
    item.party_name    = request.form.get("party_name", "").strip() or None
    item.party_email   = request.form.get("party_email", "").strip().lower() or None
    db.session.commit()
    flash("Contact saved.", "success")
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/ai-suggest-contact", methods=["POST"])
def track_item_ai_suggest_contact(token, item_id):
    from flask import jsonify
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    company = request.form.get("company", "").strip()
    if not company:
        return jsonify({"error": "Enter a company name first."}), 400
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "AI unavailable."}), 503

    system = (
        "You are a music and entertainment industry clearance expert specializing in sync licensing. "
        "Your job is to identify the correct PUBLISHING ADMINISTRATOR or rights holder that must be "
        "contacted to obtain sync/master/clearance licenses. "
        "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
    )
    # Determine if this is a music clearance item — if so, treat company as artist/song context
    is_music_item = any(k in (item.item_label or "").lower()
                        for k in ("sync", "music", "master", "publishing", "song", "track", "record"))
    if is_music_item:
        user = (
            f"Identify the publishing ADMINISTRATOR(S) that handle sync licensing for:\n"
            f"Artist / Rights Holder: {company}\n"
            f"Item type: {item.item_label}\n"
            f"Project: {sub.project_type_label} — {sub.title} on {sub.platform.name}\n\n"
            f"CRITICAL: Return the major publishing ADMINISTRATOR (Sony Music Publishing, UMPG, "
            f"Warner Chappell, Kobalt, BMG, etc.) — NOT a personal publishing entity, NOT a record label.\n"
            f"If the songs are CO-ADMINISTERED by multiple publishers, set co_admins to a list of all.\n\n"
            f"Return JSON:\n"
            f"  contact_name: string — sync licensing department name\n"
            f"  contact_email: string — sync licensing email for the PRIMARY administrator\n"
            f"  confidence: 'high' | 'medium' | 'low'\n"
            f"  note: string — identify the administrator(s) and any MFN/co-admin considerations\n"
            f"  co_admins: array of {{company, contact_email}} for any additional administrators that "
            f"must ALSO be contacted — empty array [] if single publisher\n\n"
            f"Examples of known contacts: Sony Music Publishing sync@sonymusic.com, "
            f"Kobalt Music Publishing synclicensing@kobaltmusic.com, "
            f"UMPG sync.licensing@umusic.com, Warner Chappell synclicensing@warnerchappell.com"
        )
    else:
        user = (
            f"For a {item.item_label} clearance request, identify the correct licensing contact at:\n"
            f"Company: {company}\n"
            f"Project context: {sub.project_type_label} — {sub.title}\n"
            f"Platform: {sub.platform.name}\n\n"
            f"Return JSON:\n"
            f"  contact_name: string — department or person name\n"
            f"  contact_email: string — best clearance/licensing email\n"
            f"  confidence: 'high' | 'medium' | 'low'\n"
            f"  note: string — one sentence on this contact\n"
            f"  co_admins: [] (empty — only relevant for music publishing)\n\n"
            f"Use real known contacts for Live Nation, AEG, major venues, studios, networks. "
            f"For unknown companies use clearances@company.com or licensing@company.com format."
        )
    import json as _json
    raw = call_claude(system, user, max_tokens=500)
    if not raw:
        return jsonify({"error": "AI did not respond."}), 500
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(clean)
        if "co_admins" not in data:
            data["co_admins"] = []
        # Auto-save primary contact to item if high confidence
        if data.get("confidence") == "high":
            item.party_company = company
            item.party_name    = data.get("contact_name") or item.party_name
            item.party_email   = (data.get("contact_email") or "").lower() or item.party_email
            db.session.commit()
        return jsonify(data)
    except Exception:
        return jsonify({"error": "Could not parse AI response.", "raw": raw}), 500


@app.route("/track/<token>/item/<int:item_id>/ai-fill-vars", methods=["POST"])
def track_item_ai_fill_vars(token, item_id):
    from flask import jsonify
    import json as _json
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "AI unavailable"}), 503

    var_names = request.form.getlist("vars")
    if not var_names:
        return jsonify({}), 200

    dt = item.deal_terms
    system = (
        "You are a legal document specialist. Fill in contract variable fields with accurate, "
        "specific values based on the project context provided. "
        "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
    )
    user = (
        f"Fill in the following contract variables for a {item.item_label} agreement.\n\n"
        f"Project context:\n{_sub_context(sub)}\n\n"
        f"Rights Holder: {item.party_company or item.party_name or 'Unknown'}\n"
        f"Rights Holder Email: {item.party_email or 'Unknown'}\n"
        f"Deal Terms: fee=${dt.get('fee') or 'TBD'}, fee_type={dt.get('fee_type') or 'TBD'}, "
        f"territory={dt.get('territory') or 'Worldwide'}, term={dt.get('term') or 'Perpetuity'}, "
        f"media_rights={', '.join(dt.get('media_rights') or ['Streaming'])}\n\n"
        f"Variables to fill (return ONLY these keys in JSON):\n"
        + "\n".join(f"  - {v}" for v in var_names)
        + "\n\nFor each variable, provide a specific, accurate value. Use the project data above. "
        f"For STATE: use the state where the event/company is located. "
        f"For ENTITY TYPE AND STATE: e.g. 'a California limited liability company'. "
        f"For AMOUNT: use the fee from deal terms or suggest a reasonable market rate. "
        f"For PAYMENT SCHEDULE: suggest standard terms like 'full upon execution' or '50% upon execution, 50% upon delivery'. "
        f"For DATE/EFFECTIVE DATE: use the event date or today June 21 2026. "
        f"For TERM: use the deal terms term. "
        f"Never leave a value as a bracket placeholder."
    )
    raw = call_claude(system, user, max_tokens=600)
    if not raw:
        return jsonify({"error": "AI did not respond"}), 500
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(clean)
        return jsonify(data)
    except Exception:
        return jsonify({"error": "Could not parse AI response", "raw": raw[:200]}), 500


@app.route("/track/<token>/item/<int:item_id>/send-clearance", methods=["POST"])
def track_item_send_clearance(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    if not item.ai_draft:
        flash("Generate the AI draft agreement first.", "danger")
        return redirect(url_for("track", token=token) + f"#item-card-{item_id}")
    if not item.party_email:
        flash("Add the rights holder email address first.", "danger")
        return redirect(url_for("track", token=token) + f"#item-card-{item_id}")
    dt = item.deal_terms
    if not (dt.get("territory") or dt.get("media_rights")):
        flash("Fill in deal terms (territory and media rights) before sending.", "danger")
        return redirect(url_for("track", token=token) + f"#item-card-{item_id}")
    # Build outreach body
    outreach_body = item.ai_outreach_body
    if not outreach_body:
        outreach_body = generate_outreach(sub, item) or ""
    item.ai_outreach_body = outreach_body
    # Seed the negotiation thread with this outreach
    if not item.negotiation_log:
        item.negotiation_log_add({
            "role": "outbound", "label": "Outreach email",
            "body": outreach_body, "ts": datetime.utcnow().isoformat(),
        })
        item.neg_state = "awaiting_reply"
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key and outreach_body:
        try:
            import resend as _resend
            _resend.api_key = resend_key
            _resend.Emails.send({
                "from": f"{sub.submitter_name or sub.submitter_company or 'Clearance Team'} <clear@cleared.live>",
                "to": [item.party_email],
                "reply_to": _reply_address(item),
                "subject": f"Clearance Request — {item.item_label} | {sub.title}",
                "text": outreach_body,
            })
            item.ai_outreach_sent_at = datetime.utcnow()
            db.session.commit()
            flash(f"Outreach sent to {item.party_email}.", "success")
        except Exception as e:
            app.logger.error(f"RESEND ERROR — type={type(e).__name__} key_set={bool(resend_key)} key_prefix={resend_key[:12] if resend_key else 'NONE'} error={e}")
            db.session.commit()
            flash(f"Email send failed: {e}. Draft saved — copy and send manually.", "warning")
    else:
        item.ai_outreach_sent_at = datetime.utcnow()
        db.session.commit()
        flash("Resend not configured — outreach drafted. Copy and send manually.", "warning")
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


def _neg_redirect(token, item_id):
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/record-reply", methods=["POST"])
def track_item_record_reply(token, item_id):
    """Submitter brings the rights holder's reply into the platform; AI then analyzes it."""
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    reply = request.form.get("reply_body", "").strip()
    if not reply:
        flash("Paste the rights holder's reply before recording it.", "warning")
        return _neg_redirect(token, item_id)
    item.negotiation_log_add({
        "role": "inbound", "label": "Rights holder reply",
        "body": reply, "ts": datetime.utcnow().isoformat(),
    })
    item.neg_state = "analyzing"
    item.ai_recommendation_save(None)
    db.session.commit()
    threading.Thread(target=_negotiation_agent, args=(item.id,), daemon=True).start()
    flash("Reply recorded — the AI is analyzing it and drafting the next move.", "info")
    return _neg_redirect(token, item_id)


@app.route("/track/<token>/item/<int:item_id>/regenerate-reply", methods=["POST"])
def track_item_regenerate_reply(token, item_id):
    """Re-run the negotiation agent, optionally with submitter guidance."""
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    guidance = request.form.get("guidance", "").strip()
    if guidance:
        item.negotiation_log_add({
            "role": "system", "label": "Submitter guidance to AI",
            "body": guidance, "ts": datetime.utcnow().isoformat(),
        })
    item.neg_state = "analyzing"
    item.ai_recommendation_save(None)
    db.session.commit()
    threading.Thread(target=_negotiation_agent, args=(item.id,), daemon=True).start()
    flash("Regenerating the AI recommendation…", "info")
    return _neg_redirect(token, item_id)


@app.route("/track/<token>/item/<int:item_id>/edit-reply", methods=["POST"])
def track_item_edit_reply(token, item_id):
    """Submitter edits the AI's drafted reply before approving."""
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    rec = item.ai_recommendation
    if rec:
        rec["draft_reply"] = request.form.get("draft_reply", "").strip()
        item.ai_recommendation_save(rec)
        db.session.commit()
        flash("Draft updated.", "success")
    return _neg_redirect(token, item_id)


@app.route("/track/<token>/item/<int:item_id>/approve-send", methods=["POST"])
def track_item_approve_send(token, item_id):
    """Submitter signs off on the AI's recommended move and it goes out."""
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    rec = item.ai_recommendation
    if not rec:
        flash("No AI recommendation to approve.", "warning")
        return _neg_redirect(token, item_id)
    action = rec.get("recommended_action", "send_reply")
    body = request.form.get("draft_reply", "").strip() or rec.get("draft_reply", "")

    # --- Path A: terms agreed → send for signature via DocuSign ---
    if action == "send_for_signature":
        envelope_id, error = send_to_docusign(sub, item)
        if envelope_id:
            item.docusign_envelope_id = envelope_id
            item.docusign_status      = "sent"
            item.status               = "docusign_pending"
            item.neg_state            = "signature_sent"
            item.negotiation_log_add({
                "role": "outbound", "label": "Agreement sent for signature (DocuSign)",
                "body": body or "Terms agreed — agreement sent for e-signature.",
                "ts": datetime.utcnow().isoformat(),
            })
            item.ai_recommendation_save(None)
            db.session.commit()
            flash("Approved — agreement sent for signature via DocuSign.", "success")
        else:
            flash(f"DocuSign: {error}", "danger")
        return _neg_redirect(token, item_id)

    # --- Path B: send the drafted reply as an email ---
    resend_key = os.getenv("RESEND_API_KEY")
    sent = False
    if resend_key and item.party_email and body:
        try:
            import resend as _resend
            _resend.api_key = resend_key
            _resend.Emails.send({
                "from": f"{sub.submitter_name or sub.submitter_company or 'Clearance Team'} <clear@cleared.live>",
                "to": [item.party_email],
                "reply_to": _reply_address(item),
                "subject": f"Re: Clearance Request — {item.item_label} | {sub.title}",
                "text": body,
            })
            sent = True
        except Exception as e:
            app.logger.error(f"NEG SEND ERROR — {type(e).__name__}: {e}")
    item.negotiation_log_add({
        "role": "outbound",
        "label": "Reply sent to rights holder" if sent else "Reply (Resend unavailable — copy & send manually)",
        "body": body, "ts": datetime.utcnow().isoformat(),
    })
    item.neg_state = "awaiting_reply"
    item.ai_recommendation_save(None)
    db.session.commit()
    if sent:
        flash("Approved and sent. Record the next reply when it comes in.", "success")
    else:
        flash("Saved to the thread — Resend not configured, so copy the message and send manually.", "warning")
    return _neg_redirect(token, item_id)


@app.route("/track/<token>/suggest-deal-terms", methods=["POST"])
def track_suggest_deal_terms(token):
    from flask import jsonify
    sub = Submission.query.filter_by(token=token).first_or_404()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "AI unavailable"}), 503

    territory   = request.form.get("territory", "Worldwide")
    term        = request.form.get("term", "Perpetuity")
    media_rights = request.form.getlist("media_rights")
    item_label  = request.form.get("item_label", "music publishing rights")
    rights_str  = ", ".join(media_rights) if media_rights else "Streaming"

    system = (
        "You are a senior music business affairs executive with deep knowledge of music licensing fees. "
        "Provide practical, market-rate fee guidance. Be specific with ranges. "
        "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
    )
    user = (
        f"Suggest a market-rate licensing fee for the following clearance:\n\n"
        f"Clearance type: {item_label}\n"
        f"Project: {sub.title} ({sub.project_type_label})\n"
        f"Platform: {sub.platform.name} ({sub.platform.tier} tier)\n"
        f"Artist: {sub.artist_name or 'N/A'}\n"
        f"Territory: {territory}\n"
        f"Term: {term}\n"
        f"Media Rights: {rights_str}\n\n"
        f"Return JSON with these fields:\n"
        f"  fee_low: integer (low end of range)\n"
        f"  fee_high: integer (high end of range)\n"
        f"  fee_suggested: integer (single recommended number)\n"
        f"  fee_type: string (one of: Flat Fee, Per Song, Step Deal, Gratis)\n"
        f"  rationale: string (2-3 sentences explaining the range and key factors)\n\n"
        f"Base on real-world market rates for this type of clearance. "
        f"If gratis is appropriate (e.g. promotional, label-to-label), say so with explanation."
    )
    raw = call_claude(system, user, max_tokens=400)
    if not raw:
        return jsonify({"error": "AI did not respond"}), 500
    import json as _json
    try:
        # Strip any markdown fencing if model adds it
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(clean)
        return jsonify(data)
    except Exception:
        return jsonify({"error": "Could not parse AI response", "raw": raw}), 500


@app.route("/track/<token>/item/<int:item_id>/deal-terms", methods=["POST"])
def track_item_deal_terms(token, item_id):
    sub  = Submission.query.filter_by(token=token).first_or_404()
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    terms = {
        "fee":           request.form.get("fee", "").strip() or None,
        "fee_type":      request.form.get("fee_type", "").strip() or None,
        "territory":     request.form.get("territory", "").strip() or None,
        "term":          request.form.get("term", "").strip() or None,
        "mfn":           bool(request.form.get("mfn")),
        "media_rights":  request.form.getlist("media_rights"),
        "notes":         request.form.get("notes", "").strip() or None,
    }
    item.deal_terms_save(terms)
    db.session.commit()
    flash("Deal terms saved.", "success")
    return redirect(url_for("track", token=token) + f"#item-card-{item_id}")


def _ai_fill_songs(sub_id):
    """Phase 1: get setlist titles only. Phase 2: fill writers per-song (uses publishing reference)."""
    import json
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return
    with app.app_context():
        sub = Submission.query.get(sub_id)
        if not sub or sub.project_type != "live_music":
            return
        existing = sub.setlist_list or []

        # ── Phase 1: setlist titles only ─────────────────────────────────────
        setlist_prompt = (
            f"Artist: {sub.artist_name or 'Unknown'}\n"
            f"Event: {sub.event_name or sub.title}\n"
            f"Venue: {sub.venue or 'Unknown'}\n"
            f"Date: {sub.event_date or 'Unknown'}\n"
            f"Known setlist (may be empty): {', '.join(existing) if existing else 'not provided'}\n\n"
            f"Return the setlist for this event as a JSON array. Each element:\n"
            f'{{"title": str, "is_cover": bool, "original_artist": str or null, '
            f'"confidence": "high"|"medium"|"low", "status": "pending", '
            f'"writers": [], "deal_terms": {{}}}}\n'
            f"No writers — just song titles. Return JSON only, no markdown."
        )
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": setlist_prompt}]
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:])
                if text.endswith("```"):
                    text = text[:-3].strip()
            songs = json.loads(text)
            default_deal = {"fee": None, "fee_type": None, "territory": None,
                            "term": None, "mfn": False, "cue_sheet_days": 30,
                            "media_rights": [], "notes": ""}
            for s in songs:
                if "deal_terms" not in s or not s["deal_terms"]:
                    s["deal_terms"] = dict(default_deal)
                # Always clear writers in Phase 1 — Phase 2 fills them with the
                # publisher-admin prompt. Prevents stale/wrong data from Phase 1.
                s["writers"] = []
            sub.songs_save(songs)
            if not sub.setlist:
                sub.setlist = "\n".join(s["title"] for s in songs)
            db.session.commit()
            app.logger.info(f"AI setlist phase 1 done for sub {sub_id}: {len(songs)} songs")
        except Exception as e:
            app.logger.error(f"AI setlist phase 1 failed for sub {sub_id}: {e}")
            return

        # Phase 2 is triggered separately — see _ai_fill_all_writers


def _ai_fill_all_writers(sub_id):
    """Background: fill writers for every song sequentially (runs after setlist phase)."""
    with app.app_context():
        sub = Submission.query.get(sub_id)
        if not sub:
            return
        for idx in range(len(sub.songs)):
            try:
                _ai_fill_song_writers(sub_id, idx)
            except Exception as e:
                app.logger.error(f"Writer fill failed song {idx} sub {sub_id}: {e}")


def _ai_fill_song_writers(sub_id, idx):
    """Background: fill writers for a single song by index."""
    import json
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return
    with app.app_context():
        sub = Submission.query.get(sub_id)
        if not sub:
            return
        songs = sub.songs
        if idx < 0 or idx >= len(songs):
            return
        song = songs[idx]
        title = song.get("title", "Unknown")
        artist = sub.artist_name or "Unknown"
        _pub = _get_publishing_notes(sub)
        publishing_ref = (
            f"\nPUBLISHING REFERENCE (verified admin corrections for specific writers):\n{_pub}\n"
            if _pub else ""
        )
        prompt = (
            f"You are a music publishing rights research assistant specializing in sync licensing clearance.\n"
            f"Song: \"{title}\" by {artist}\n\n"
            f"STEP 1 — FIND ALL WRITERS:\n"
            f"Research the full list of credited songwriters for this song from PRO databases "
            f"(BMI, ASCAP, SESAC). List every credited songwriter and their approximate song split.\n"
            f"- Do NOT include featured performers — only credited writers.\n"
            f"- If uncertain about co-writers, list only the primary artist at 100%.\n\n"
            f"STEP 2 — ASSIGN PUBLISHING ADMINISTRATORS:\n"
            f"For each writer, identify their SYNC LICENSING ADMINISTRATOR — the major company "
            f"that can actually issue sync licenses. This is NOT the songwriter's personal pub entity.\n"
            f"- Valid administrators: Sony Music Publishing, Universal Music Publishing Group (UMPG), "
            f"Warner Chappell Music, Kobalt Music Publishing, BMG Rights Management, Downtown Music "
            f"Publishing, Concord Music Publishing, Spirit Music Group, SONGS Music Publishing, etc.\n"
            f"- NEVER return a personal pub company or record label as the publisher.\n"
            f"- If the Publishing Reference below names an administrator for a specific writer, "
            f"use that instead of your best guess — but only for that writer. All other writers "
            f"keep their independently researched administrators.\n"
            f"- If a writer's share is CO-ADMINISTERED (e.g. 50% Sony / 50% Kobalt of their share), "
            f"create TWO entries for that writer, each with half their song split.\n\n"
            f"STEP 3 — BUILD THE JSON:\n"
            f"The Publishing Reference percentages refer to how that writer's OWN share is administered, "
            f"NOT to the overall song split. Example for a 3-writer song where Noah Kahan has 33.3% "
            f"and is co-administered Sony/Kobalt 50/50:\n"
            f"  Noah Kahan / Sony Music Publishing / BMI / 16.7%\n"
            f"  Noah Kahan / Kobalt Music Publishing / BMI / 16.7%\n"
            f"  Co-writer 2 / their publisher / PRO / 33.3%\n"
            f"  Co-writer 3 / their publisher / PRO / 33.4%\n"
            f"  Total = 100%\n"
            f"{publishing_ref}\n"
            f"Return ONLY a JSON array — no prose, no markdown:\n"
            f'[{{"name": str, "publisher": str, "pro": "ASCAP"|"BMI"|"SESAC"|"SOCAN"|"PRS", "split_pct": number}}]\n'
            f"All split_pct values must sum to exactly 100."
        )
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:])
                if text.endswith("```"):
                    text = text[:-3].strip()
            writers = json.loads(text)
            songs[idx]["writers"] = writers
            sub.songs_save(songs)
            db.session.commit()
            app.logger.info(f"AI writers filled for song idx {idx} in sub {sub_id}")
        except Exception as e:
            app.logger.error(f"AI writer fill failed for sub {sub_id} idx {idx}: {e}")


@app.route("/track/<token>/ai-fill-songs", methods=["POST"])
def track_ai_fill_songs(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    _ai_fill_songs(sub.id)   # Phase 1: setlist titles only, synchronous
    # Phase 2 handled client-side via /fill-next-writers batched JSON calls
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/fill-next-writers", methods=["POST"])
def track_fill_next_writers(token):
    """Fill writers for a batch of songs. Called repeatedly by JS until done."""
    from flask import jsonify
    sub  = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    start = int(request.form.get("start", 0))
    force = request.form.get("force") == "1"
    batch = 3
    filled = []
    for idx in range(start, min(start + batch, len(songs))):
        if force or not songs[idx].get("writers"):
            _ai_fill_song_writers(sub.id, idx)
            filled.append(idx)
    next_start = start + batch
    return jsonify({
        "next":  next_start,
        "done":  next_start >= len(songs),
        "total": len(songs),
        "filled": filled,
    })


@app.route("/track/<token>/songs/add", methods=["POST"])
def track_song_add(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    writer_name = request.form.get("writer_name", "").strip()
    writer_entry = {
        "name":      writer_name,
        "publisher": request.form.get("publisher", "").strip(),
        "pro":       request.form.get("pro", "").strip(),
        "split_pct": 100,
    }
    songs.append({
        "title":          request.form.get("title", "").strip(),
        "writers":        [writer_entry] if writer_name else [],
        "is_cover":       request.form.get("is_cover") == "1",
        "original_artist": request.form.get("original_artist", "").strip() or None,
        "confidence":     "manual",
        "status":         "pending",
        "deal_terms": {
            "fee": None, "fee_type": None, "territory": None,
            "term": None, "mfn": False, "cue_sheet_days": 30,
            "media_rights": [], "notes": ""
        },
    })
    sub.songs_save(songs)
    db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/delete/<int:idx>", methods=["POST"])
def track_song_delete(token, idx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        songs.pop(idx)
        sub.songs_save(songs)
        db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/update/<int:idx>", methods=["POST"])
def track_song_update(token, idx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        songs[idx]["title"]         = request.form.get("title", songs[idx].get("title", ""))
        songs[idx]["is_cover"]      = request.form.get("is_cover") == "1"
        songs[idx]["original_artist"] = request.form.get("original_artist", "") or None
        songs[idx]["status"]        = request.form.get("status", songs[idx].get("status", "pending"))
        sub.songs_save(songs)
        db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/<int:idx>/writer/add", methods=["POST"])
def track_song_writer_add(token, idx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        writer = {
            "name":      request.form.get("writer_name", "").strip(),
            "publisher": request.form.get("publisher", "").strip(),
            "pro":       request.form.get("pro", "").strip(),
            "split_pct": int(request.form.get("split_pct", 0) or 0),
        }
        songs[idx].setdefault("writers", []).append(writer)
        sub.songs_save(songs)
        db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/<int:idx>/writer/<int:widx>/delete", methods=["POST"])
def track_song_writer_delete(token, idx, widx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        writers = songs[idx].get("writers", [])
        if 0 <= widx < len(writers):
            writers.pop(widx)
            songs[idx]["writers"] = writers
            sub.songs_save(songs)
            db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/<int:idx>/writer/<int:widx>/update", methods=["POST"])
def track_song_writer_update(token, idx, widx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        writers = songs[idx].get("writers", [])
        if 0 <= widx < len(writers):
            writers[widx]["name"]      = request.form.get("name", writers[widx]["name"]).strip()
            writers[widx]["publisher"] = request.form.get("publisher", writers[widx].get("publisher", "")).strip()
            writers[widx]["pro"]       = request.form.get("pro", writers[widx].get("pro", "")).strip()
            try:
                writers[widx]["split_pct"] = float(request.form.get("split_pct", writers[widx].get("split_pct", 0)))
            except ValueError:
                pass
            songs[idx]["writers"] = writers
            sub.songs_save(songs)
            db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/<int:idx>/ai-fill-writers", methods=["POST"])
def track_song_ai_fill_writers(token, idx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    _ai_fill_song_writers(sub.id, idx)
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/pub-groups/generate", methods=["POST"])
def track_pub_groups_generate(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    groups = _compute_publisher_groups(sub)
    # Merge with existing saved data (preserve contact/outreach/status)
    existing = sub.publisher_clearances
    for pub, g in groups.items():
        saved = existing.get(pub, {})
        g["contact_name"]     = saved.get("contact_name", "")
        g["contact_email"]    = saved.get("contact_email", "")
        g["ai_outreach"]      = saved.get("ai_outreach", "")
        g["outreach_sent_at"] = saved.get("outreach_sent_at", "")
        g["rh_response"]      = saved.get("rh_response", "")
        g["rh_response_notes"]= saved.get("rh_response_notes", "")
        g["status"]           = saved.get("status", "pending")
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return redirect(url_for("track", token=token) + "#pub-clearance-section")


@app.route("/track/<token>/pub-groups/contact", methods=["POST"])
def track_pub_groups_contact(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher in groups:
        groups[publisher]["contact_name"]  = request.form.get("contact_name", "").strip()
        groups[publisher]["contact_email"] = request.form.get("contact_email", "").strip()
        sub.publisher_clearances_save(groups)
        db.session.commit()
    return redirect(url_for("track", token=token) + "#pub-clearance-section")


@app.route("/track/<token>/pub-groups/outreach", methods=["POST"])
def track_pub_groups_outreach(token):
    from flask import jsonify
    sub = Submission.query.filter_by(token=token).first_or_404()
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return jsonify({"error": "Publisher group not found"}), 404

    g = groups[publisher]
    song_list = "\n".join(
        f"  - \"{s['title']}\" (writer: {s['writer']}, {s['split_pct']}% of song)"
        for s in g.get("songs", [])
    )
    neg = sub.platform.negotiation_positions if sub.platform else {}
    primary = (neg or [{}])[0] if isinstance(neg, list) else {}
    system = (
        "You are a music clearance professional drafting sync license request emails. "
        "Write professional, concise outreach. Do not use placeholders — write real content."
    )
    user = (
        f"Draft a sync license request email to {publisher}'s sync licensing department.\n\n"
        f"From: {sub.submitter_name or 'Music Clearance Team'} on behalf of {sub.platform.name if sub.platform else 'our platform'}\n"
        f"Project: {sub.project_type_label} — {sub.title}\n"
        f"Artist performing: {sub.artist_name or 'Unknown'}\n"
        f"Event: {sub.event_name or sub.title}\n"
        f"Venue: {sub.venue or 'TBD'}\n"
        f"Date: {sub.event_date or 'TBD'}\n"
        f"Platform: {sub.platform.name if sub.platform else 'Streaming'}\n\n"
        f"Songs requesting clearance ({len(g.get('songs', []))} total):\n{song_list}\n\n"
        f"Deal terms requested:\n"
        f"  Territory: {primary.get('territory', 'Worldwide')}\n"
        f"  Term: {primary.get('term', 'Perpetuity')}\n"
        f"  Uses: {', '.join(primary.get('uses', ['Streaming']))}\n\n"
        f"Include MFN language if appropriate (this project is clearing rights with multiple publishers simultaneously). "
        f"Request that all songs be covered under one blanket sync license agreement for efficiency. "
        f"Sign off with just the sender's name and company — no 'on behalf of' in the closing. "
        f"Signature: {sub.submitter_name or ''}"
        + (f"\n{sub.submitter_company}" if sub.submitter_company else "") + ". "
        f"Keep to 3–4 short paragraphs. Professional tone. No markdown formatting."
    )
    raw = call_claude(system, user, max_tokens=800)
    if not raw:
        return jsonify({"error": "AI did not respond"}), 500
    groups[publisher]["ai_outreach"] = raw
    groups[publisher]["status"] = "in_progress"
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return jsonify({"outreach": raw})


@app.route("/track/<token>/pub-groups/send", methods=["POST"])
def track_pub_groups_send(token):
    from flask import jsonify
    import resend as _resend
    sub = Submission.query.filter_by(token=token).first_or_404()
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return jsonify({"error": "Publisher group not found"}), 404
    g = groups[publisher]
    if not g.get("contact_email"):
        return jsonify({"error": "No contact email set for this publisher"}), 400
    if not g.get("ai_outreach"):
        return jsonify({"error": "Generate the outreach draft first"}), 400

    _resend.api_key = os.getenv("RESEND_API_KEY")
    try:
        _resend.Emails.send({
            "from": f"{sub.submitter_name or sub.submitter_company or 'Clearance Team'} <clear@cleared.live>",
            "to": g["contact_email"],
            "subject": f"Sync License Request — {sub.artist_name or sub.title} ({len(g.get('songs',[]))} songs) — {sub.platform.name if sub.platform else ''}",
            "text": g["ai_outreach"],
        })
        from datetime import datetime as _dt
        groups[publisher]["outreach_sent_at"] = _dt.utcnow().isoformat()
        groups[publisher]["status"] = "under_review"
        sub.publisher_clearances_save(groups)
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/track/<token>/pub-groups/response", methods=["POST"])
def track_pub_groups_response(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return redirect(url_for("track", token=token) + "#pub-clearance-section")
    from datetime import datetime as _dt
    groups[publisher]["rh_response"]        = request.form.get("rh_response", "")
    groups[publisher]["rh_response_notes"]  = request.form.get("rh_response_notes", "")
    groups[publisher]["rh_response_at"]     = _dt.utcnow().isoformat()
    resp = groups[publisher]["rh_response"]
    if resp == "accepted":
        groups[publisher]["status"] = "cleared"
    elif resp == "declined":
        groups[publisher]["status"] = "pending"
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return redirect(url_for("track", token=token) + "#pub-clearance-section")


@app.route("/track/<token>/songs/<int:idx>/deal-terms", methods=["POST"])
def track_song_deal_terms(token, idx):
    sub = Submission.query.filter_by(token=token).first_or_404()
    songs = sub.songs
    if 0 <= idx < len(songs):
        songs[idx]["deal_terms"] = {
            "fee":           request.form.get("fee") or None,
            "fee_type":      request.form.get("fee_type") or None,
            "territory":     request.form.get("territory") or None,
            "term":          request.form.get("term") or None,
            "mfn":           request.form.get("mfn") == "1",
            "cue_sheet_days": int(request.form.get("cue_sheet_days", 30) or 30),
            "media_rights":  request.form.getlist("media_rights"),
            "notes":         request.form.get("notes", ""),
        }
        sub.songs_save(songs)
        db.session.commit()
    return redirect(url_for("track", token=token) + "#songs-section")


@app.route("/track/<token>/songs/bulk-deal-terms", methods=["POST"])
def track_song_bulk_deal_terms(token):
    sub = Submission.query.filter_by(token=token).first_or_404()
    terms = {
        "fee":           request.form.get("fee") or None,
        "fee_type":      request.form.get("fee_type") or None,
        "territory":     request.form.get("territory") or None,
        "term":          request.form.get("term") or None,
        "mfn":           request.form.get("mfn") == "1",
        "cue_sheet_days": int(request.form.get("cue_sheet_days", 30) or 30),
        "media_rights":  request.form.getlist("media_rights"),
        "notes":         request.form.get("notes", ""),
    }
    sub.deal_terms_save(terms)
    if request.form.get("apply_to_all") == "1":
        songs = sub.songs
        for s in songs:
            s["deal_terms"] = dict(terms)
        sub.songs_save(songs)
    db.session.commit()
    flash("Bulk deal terms saved.", "success")
    return redirect(url_for("track", token=token) + "#songs-section")


# ---------------------------------------------------------------------------
# Platform BA — auth
# ---------------------------------------------------------------------------

@app.route("/platform/login", methods=["GET", "POST"])
def platform_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = PlatformUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["platform_user_id"] = user.id
            session["platform_id"] = user.platform_id
            return redirect(url_for("platform_dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("platform/login.html")


@app.route("/platform/invite", methods=["POST"])
@require_platform
def platform_send_invite():
    email        = request.form.get("email", "").strip().lower()
    name         = request.form.get("name", "").strip()
    project_hint = request.form.get("project_hint", "").strip()

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("platform_dashboard"))

    user = current_platform_user()
    invite = Invite(
        platform_id  = user.platform.id,
        email        = email,
        name         = name or None,
        project_hint = project_hint or None,
    )
    db.session.add(invite)
    db.session.commit()

    invite_url = url_for("submit", platform_slug=user.platform.slug, invite=invite.token, _external=True)

    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        import resend as _resend
        _resend.api_key = resend_key
        body = render_template("email/invite.html",
            platform_name  = user.platform.name,
            platform_color = user.platform.primary_color or "#0d3b6e",
            name           = name or None,
            project_hint   = project_hint or None,
            invite_url     = invite_url,
        )
        try:
            _resend.Emails.send({
                "from": "Cleared.live <clear@blisslegalstudio.com>",  # TODO: swap to clear@cleared.live once domain verified
                "to": email,
                "subject": f"You've been invited to submit a clearance request — {user.platform.name}",
                "html": body,
            })
            flash(f"Invite sent to {email}.", "success")
        except Exception as e:
            flash(f"Invite created but email failed: {e}. Share this link manually: {invite_url}", "warning")
    else:
        flash(f"Invite created. Share this link with {email}: {invite_url}", "info")

    return redirect(url_for("platform_dashboard"))


@app.route("/platform/settings", methods=["GET", "POST"])
@require_platform
def platform_settings():
    import json
    user = current_platform_user()
    p    = user.platform
    if request.method == "POST":
        p.form_territory           = request.form.get("form_territory") or None
        p.form_territory_locked    = bool(request.form.get("form_territory_locked"))
        p.form_intended_use        = ",".join(request.form.getlist("form_intended_use")) or None
        p.form_intended_use_locked = bool(request.form.get("form_intended_use_locked"))
        # Collect up to 4 negotiation positions from form
        positions = []
        for i in range(1, 5):
            label     = request.form.get(f"pos_{i}_label", "").strip()
            territory = request.form.get(f"pos_{i}_territory", "").strip()
            uses         = request.form.getlist(f"pos_{i}_uses")
            uses_exclude = request.form.getlist(f"pos_{i}_uses_exclude")
            term         = request.form.get(f"pos_{i}_term", "").strip()
            notes        = request.form.get(f"pos_{i}_notes", "").strip()
            if label and territory:
                positions.append({"rank": i, "label": label, "territory": territory,
                                   "uses": uses, "uses_exclude": uses_exclude,
                                   "term": term, "notes": notes})
        p.negotiation_positions_json = json.dumps(positions) if positions else None
        db.session.commit()
        flash("Form configuration saved.", "success")
        return redirect(url_for("platform_settings"))
    return render_template("platform/settings.html",
        platform             = p,
        platform_user        = user,
        territory_labels     = TERRITORY_LABELS,
        intended_use_options = INTENDED_USE_OPTIONS,
        term_labels          = TERM_LABELS,
        form_presets         = FORM_PRESETS,
    )


@app.route("/platform/invites/<int:invite_id>/delete", methods=["POST"])
@require_platform
def platform_delete_invite(invite_id):
    user   = current_platform_user()
    invite = Invite.query.filter_by(id=invite_id, platform_id=user.platform.id).first_or_404()
    db.session.delete(invite)
    db.session.commit()
    flash("Invite deleted.", "success")
    return redirect(url_for("platform_invites"))


@app.route("/platform/invites")
@require_platform
def platform_invites():
    user    = current_platform_user()
    invites = Invite.query.filter_by(platform_id=user.platform.id).order_by(Invite.created_at.desc()).all()
    return render_template("platform/invites.html", invites=invites, platform=user.platform)


@app.route("/platform/logout")
def platform_logout():
    session.pop("platform_user_id", None)
    session.pop("platform_id", None)
    return redirect(url_for("platform_login"))


# ---------------------------------------------------------------------------
# Platform BA — dashboard
# ---------------------------------------------------------------------------

@app.route("/platform/dashboard")
@require_platform
def platform_dashboard():
    user     = current_platform_user()
    platform = user.platform
    sf       = request.args.get("status", "")
    tf       = request.args.get("type", "")

    q = Submission.query.filter_by(platform_id=platform.id)
    if sf:
        q = q.filter_by(status=sf)
    if tf:
        q = q.filter_by(project_type=tf)
    submissions = q.order_by(Submission.created_at.desc()).all()

    stats = {
        "total":        Submission.query.filter_by(platform_id=platform.id).count(),
        "cleared":      Submission.query.filter_by(platform_id=platform.id, status="cleared").count(),
        "in_clearance": Submission.query.filter_by(platform_id=platform.id, status="in_clearance").count(),
        "new":          Submission.query.filter_by(platform_id=platform.id, status="submitted").count(),
    }
    return render_template(
        "platform/dashboard.html",
        platform=platform,
        submissions=submissions,
        stats=stats,
        sf=sf, tf=tf,
        project_type_labels=PROJECT_TYPE_LABELS,
        ba_actions=_scan_ba_actions(platform),
    )


@app.route("/platform/project/<int:sub_id>")
@require_platform
def platform_project(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    return render_template(
        "platform/project_detail.html",
        sub=sub,
        platform=user.platform,
        pricing_tiers=PRICING_TIERS,
        territory_labels=TERRITORY_LABELS,
        intended_use_options=INTENDED_USE_OPTIONS,
        term_labels=TERM_LABELS,
        ba_notes_only=_get_ba_notes_only(sub),
        publishing_notes=_get_publishing_notes(sub),
    )


@app.route("/platform/project/<int:sub_id>/status", methods=["POST"])
@require_platform
def platform_set_status(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)

    new_status = request.form.get("status", "")
    valid = ("submitted", "in_review", "in_clearance", "cleared", "rejected")
    if new_status in valid:
        sub.status     = new_status
        sub.updated_at = datetime.utcnow()
        if new_status == "cleared":
            sub.cleared_at = datetime.utcnow()
            db.session.commit()
            deliver_webhook(user.platform_id, sub.id, "clearance_complete", clearance_payload(sub))
        else:
            db.session.commit()
        flash(f"Status updated to '{sub.status_label}'.", "success")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>", methods=["POST"])
@require_platform
def platform_update_item(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)

    new_status = request.form.get("status", "")
    if new_status in ("pending", "in_progress", "cleared", "waived", "n_a"):
        item.status      = new_status
        item.notes       = request.form.get("notes", item.notes or "").strip() or item.notes
        item.party_name  = request.form.get("party_name", item.party_name or "").strip() or item.party_name
        item.party_email = request.form.get("party_email", item.party_email or "").strip() or item.party_email
        if new_status in ("cleared", "waived"):
            item.cleared_at = datetime.utcnow()
            item.cleared_by = user.username
        db.session.commit()
        # Auto-outreach agent: generate (and send if email known) when item moves to in_progress
        if new_status == "in_progress":
            threading.Thread(target=_auto_outreach_agent, args=(item.id,), daemon=True).start()

        if sub.is_fully_cleared and sub.status not in ("cleared", "rejected"):
            sub.status = "in_clearance"
            db.session.commit()

        deliver_webhook(user.platform_id, sub.id, "item_updated", {
            "event": "item_updated",
            "submission_token": sub.token,
            "item_key": item.item_key,
            "item_status": item.status,
            "progress_pct": sub.progress_pct,
            "all_cleared": sub.is_fully_cleared,
        })

    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/approve", methods=["POST"])
@require_platform
def platform_approve_item(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    item.status     = "cleared"
    item.cleared_at = datetime.utcnow()
    item.cleared_by = user.username
    db.session.commit()

    deliver_webhook(user.platform_id, sub.id, "item_updated", {
        "event": "item_updated",
        "submission_token": sub.token,
        "item_key": item.item_key,
        "item_status": item.status,
        "progress_pct": sub.progress_pct,
        "all_cleared": sub.is_fully_cleared,
    })

    if sub.is_fully_cleared and sub.status not in ("cleared", "rejected"):
        sub.status     = "cleared"
        sub.cleared_at = datetime.utcnow()
        db.session.commit()
        deliver_webhook(user.platform_id, sub.id, "clearance_complete", clearance_payload(sub))

    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/reject", methods=["POST"])
@require_platform
def platform_reject_item(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    item.status = "in_progress"
    reject_note = request.form.get("reject_note", "").strip()
    if reject_note:
        item.notes = reject_note
    db.session.commit()
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/add-item", methods=["POST"])
@require_platform
def platform_add_item(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    label    = request.form.get("item_label", "").strip()
    category = request.form.get("item_category", "clearance")  # clearance | document | insurance
    notes    = request.form.get("item_notes", "").strip()
    gen_ai   = request.form.get("gen_ai") == "1"
    if not label:
        flash("Item label is required.", "danger")
        return redirect(url_for("platform_project", sub_id=sub_id))
    # Build a descriptive key from category + label
    key = f"ba_added_{category}_{label[:40].lower().replace(' ','_')}"
    max_priority = max((i.priority for i in sub.clearance_items), default=0)
    item = ClearanceItem(
        submission_id = sub.id,
        item_key      = key,
        item_label    = label,
        priority      = max_priority + 1,
        status        = "pending",
        notes         = notes or None,
    )
    db.session.add(item)
    db.session.commit()
    if gen_ai:
        import threading
        def _draft():
            with app.app_context():
                it = ClearanceItem.query.get(item.id)
                s  = Submission.query.get(sub.id)
                prompt = (
                    f"Draft a {category} agreement for: {label}.\n"
                    f"Project: {s.title} ({s.project_type}) for {s.platform.name}.\n"
                    f"Territory: {s.territory}. BA notes: {notes or 'none'}.\n"
                    f"Use [BRACKETS] for party names, dates, and amounts to fill in. "
                    f"Be concise and legally precise."
                )
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    resp = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1500,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    it.ai_draft = resp.content[0].text
                    db.session.commit()
                except Exception as e:
                    app.logger.error(f"AI draft for custom item failed: {e}")
        threading.Thread(target=_draft, daemon=True).start()
        flash(f"'{label}' added — AI draft generating in background (~30 sec).", "success")
    else:
        flash(f"'{label}' added to clearance checklist.", "success")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/notes", methods=["POST"])
@require_platform
def platform_save_notes(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    if "ba_notes" in request.form:
        general = request.form.get("ba_notes", "").strip()
        _set_publishing_notes(sub, general, _get_publishing_notes(sub))
    if "publishing_notes" in request.form:
        pub = request.form.get("publishing_notes", "").strip()
        _set_publishing_notes(sub, _get_ba_notes_only(sub), pub)
    sub.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Saved.", "success")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/upload", methods=["POST"])
@require_platform
def platform_upload(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)

    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("platform_project", sub_id=sub_id))

    item_id_raw = request.form.get("clearance_item_id")
    doc = SubmissionDocument(
        submission_id     = sub_id,
        clearance_item_id = int(item_id_raw) if item_id_raw else None,
        title             = request.form.get("title", f.filename).strip(),
        doc_type          = request.form.get("doc_type", "other"),
        filename          = f.filename,
        file_data         = f.read(),
        mimetype          = f.mimetype or "application/octet-stream",
        uploaded_by       = user.username,
    )
    db.session.add(doc)
    db.session.commit()
    flash("Document uploaded.", "success")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/doc/<int:doc_id>/download")
@require_platform
def platform_download_doc(doc_id):
    user = current_platform_user()
    doc  = SubmissionDocument.query.get_or_404(doc_id)
    if doc.submission.platform_id != user.platform_id:
        abort(403)
    return send_file(
        __import__("io").BytesIO(doc.file_data),
        download_name=doc.filename,
        as_attachment=True,
        mimetype=doc.mimetype or "application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Admin — Cleared.live internal
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = AdminUser.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session["admin_user_id"] = user.id
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_user_id", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/")
@require_admin
def admin_dashboard():
    platforms         = Platform.query.order_by(Platform.created_at.desc()).all()
    total_submissions = Submission.query.count()
    total_cleared     = Submission.query.filter_by(status="cleared").count()
    recent            = Submission.query.order_by(Submission.created_at.desc()).limit(10).all()
    return render_template(
        "admin/dashboard.html",
        platforms=platforms,
        total_submissions=total_submissions,
        total_cleared=total_cleared,
        recent=recent,
    )


@app.route("/admin/platforms/new", methods=["GET", "POST"])
@require_admin
def admin_new_platform():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = request.form.get("slug", "").strip().lower().replace(" ", "-")

        platform = Platform(
            name            = name,
            slug            = slug,
            logo_text       = request.form.get("logo_text", name.split()[0]).strip(),
            ba_contact_name = request.form.get("ba_contact_name", "").strip(),
            ba_contact_email= request.form.get("ba_contact_email", "").strip(),
            webhook_url     = request.form.get("webhook_url", "").strip() or None,
            tier            = request.form.get("tier", "standard"),
            primary_color   = request.form.get("primary_color", "#0d3b6e").strip(),
            accepted_types  = ",".join(request.form.getlist("accepted_types")) or "live_music",
        )
        db.session.add(platform)
        db.session.flush()

        ba_username = request.form.get("ba_username", "").strip()
        ba_password = request.form.get("ba_password", "").strip()
        if ba_username and ba_password:
            db.session.add(PlatformUser(
                platform_id   = platform.id,
                username      = ba_username,
                email         = platform.ba_contact_email,
                password_hash = generate_password_hash(ba_password),
                role          = "admin",
            ))
        db.session.commit()
        flash(f"Platform '{name}' created. API key: {platform.api_key}", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin/new_platform.html",
        project_type_labels=PROJECT_TYPE_LABELS,
    )


@app.route("/admin/platform/<int:platform_id>/edit", methods=["GET", "POST"])
@require_admin
def admin_edit_platform(platform_id):
    p = Platform.query.get_or_404(platform_id)
    if request.method == "POST":
        p.name           = request.form.get("name", p.name).strip()
        p.slug           = request.form.get("slug", p.slug).strip().lower().replace(" ", "-")
        p.logo_text      = request.form.get("logo_text", "").strip() or None
        p.primary_color  = request.form.get("primary_color", p.primary_color).strip()
        p.ba_contact_name  = request.form.get("ba_contact_name", "").strip() or None
        p.ba_contact_email = request.form.get("ba_contact_email", "").strip() or None
        p.webhook_url    = request.form.get("webhook_url", "").strip() or None
        p.tier           = request.form.get("tier", p.tier)
        p.accepted_types = ",".join(request.form.getlist("accepted_types")) or p.accepted_types
        p.is_active      = bool(request.form.get("is_active"))
        db.session.commit()
        flash(f"Platform '{p.name}' updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/edit_platform.html", p=p, project_type_labels=PROJECT_TYPE_LABELS)


@app.route("/admin/platform/<int:platform_id>/delete", methods=["POST"])
@require_admin
def admin_delete_platform(platform_id):
    p = Platform.query.get_or_404(platform_id)
    name = p.name
    if p.total_count > 0:
        flash(f"Cannot delete '{name}' — it has {p.total_count} submissions. Deactivate it instead.", "danger")
        return redirect(url_for("admin_dashboard"))
    # Remove dependent records before deleting the platform
    Invite.query.filter_by(platform_id=p.id).delete()
    ClearanceGuideline.query.filter_by(platform_id=p.id).delete()
    WebhookDelivery.query.filter_by(platform_id=p.id).delete()
    PlatformUser.query.filter_by(platform_id=p.id).delete()
    db.session.delete(p)
    db.session.commit()
    flash(f"Platform '{name}' deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/submissions")
@require_admin
def admin_submissions():
    subs = Submission.query.order_by(Submission.created_at.desc()).limit(200).all()
    return render_template("admin/submissions.html", subs=subs, project_type_labels=PROJECT_TYPE_LABELS)


@app.route("/admin/submission/<int:sub_id>", methods=["GET"])
@require_admin
def admin_submission(sub_id):
    sub = Submission.query.get_or_404(sub_id)
    return render_template(
        "admin/submission_detail.html",
        sub=sub,
        pricing_tiers=PRICING_TIERS,
    )


@app.route("/admin/submission/<int:sub_id>/item/<int:item_id>", methods=["POST"])
@require_admin
def admin_update_item(sub_id, item_id):
    sub  = Submission.query.get_or_404(sub_id)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    new_status = request.form.get("status", "")
    if new_status in ("pending", "in_progress", "cleared", "waived", "n_a"):
        item.status     = new_status
        item.notes      = request.form.get("notes", item.notes or "").strip() or item.notes
        item.party_name = request.form.get("party_name", item.party_name or "").strip() or item.party_name
        if new_status in ("cleared", "waived"):
            item.cleared_at = datetime.utcnow()
            item.cleared_by = "admin"
        db.session.commit()
    return redirect(url_for("admin_submission", sub_id=sub_id))


@app.route("/admin/submission/<int:sub_id>/release", methods=["POST"])
@require_admin
def admin_release(sub_id):
    sub            = Submission.query.get_or_404(sub_id)
    sub.status     = "cleared"
    sub.cleared_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    db.session.commit()
    deliver_webhook(sub.platform_id, sub.id, "clearance_complete", clearance_payload(sub))
    flash("Project released — webhook fired.", "success")
    return redirect(url_for("admin_submission", sub_id=sub_id))


@app.route("/admin/submission/<int:sub_id>/payment", methods=["POST"])
@require_admin
def admin_set_payment(sub_id):
    sub = Submission.query.get_or_404(sub_id)
    new_pmt = request.form.get("payment_status", "")
    if new_pmt in ("pending", "invoiced", "paid", "waived"):
        sub.payment_status = new_pmt
        db.session.commit()
        flash(f"Payment status set to '{new_pmt}'.", "success")
    return redirect(url_for("admin_submission", sub_id=sub_id))


# ---------------------------------------------------------------------------
# REST API v1
# ---------------------------------------------------------------------------

@app.route("/api/v1/status/<token>")
def api_status(token):
    """Public: check clearance status by submission token."""
    sub = Submission.query.filter_by(token=token).first()
    if not sub:
        return jsonify({"error": "Not found"}), 404
    return jsonify(sub.to_api_dict())


@app.route("/api/v1/projects")
@require_api_key
def api_projects():
    """Platform: list submissions for this platform."""
    platform = request.api_platform
    status   = request.args.get("status", "")
    ptype    = request.args.get("project_type", "")
    q = Submission.query.filter_by(platform_id=platform.id)
    if status:
        q = q.filter_by(status=status)
    if ptype:
        q = q.filter_by(project_type=ptype)
    subs = q.order_by(Submission.created_at.desc()).limit(200).all()
    return jsonify([s.to_api_dict() for s in subs])


@app.route("/api/v1/projects/<token>")
@require_api_key
def api_project_detail(token):
    """Platform: get full detail for one submission."""
    platform = request.api_platform
    sub      = Submission.query.filter_by(token=token, platform_id=platform.id).first()
    if not sub:
        return jsonify({"error": "Not found"}), 404
    return jsonify(sub.to_api_dict())


@app.route("/api/v1/webhook/test", methods=["POST"])
@require_api_key
def api_webhook_test():
    """Platform: fire a test webhook to verify the endpoint."""
    platform = request.api_platform
    if not platform.webhook_url:
        return jsonify({"sent": False, "error": "No webhook URL configured on this platform."}), 400
    deliver_webhook(platform.id, None, "test", {
        "event": "test",
        "platform": platform.name,
        "message": "Cleared.live webhook test — if you see this, your endpoint is working.",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return jsonify({"sent": True, "url": platform.webhook_url})


@app.route("/api/v1/docs")
def api_docs():
    return render_template("api_docs.html")


# ---------------------------------------------------------------------------
# AI + DocuSign routes
# ---------------------------------------------------------------------------

@app.route("/platform/project/<int:sub_id>/ai-draft-all", methods=["POST"])
@require_platform
def platform_ai_draft_all(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    if not os.getenv("ANTHROPIC_API_KEY"):
        flash("ANTHROPIC_API_KEY not configured in Render environment.", "danger")
        return redirect(url_for("platform_project", sub_id=sub_id))
    # Force-regenerate all drafts in background (clears existing so agent rewrites them)
    for item in sub.clearance_items:
        item.ai_draft = None
    db.session.commit()
    threading.Thread(target=_auto_draft_agent, args=(sub.id,), daemon=True).start()
    flash(f"Regenerating {len(sub.clearance_items)} AI drafts in background — refresh in ~60 seconds.", "info")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/ai-draft", methods=["POST"])
@require_platform
def platform_ai_draft(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    draft = generate_draft(sub, item)
    if draft:
        item.ai_draft = draft
        db.session.commit()
        flash(f"AI draft generated for {item.item_label}.", "success")
    else:
        flash("ANTHROPIC_API_KEY not configured in Render environment.", "danger")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/ai-outreach", methods=["POST"])
@require_platform
def platform_ai_outreach(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    body = generate_outreach(sub, item)
    if not body:
        flash("ANTHROPIC_API_KEY not configured in Render environment.", "danger")
        return redirect(url_for("platform_project", sub_id=sub_id))
    item.ai_outreach_body    = body
    item.ai_outreach_sent_at = datetime.utcnow()
    db.session.commit()
    flash(f"AI outreach drafted for {item.item_label}.", "success")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/docusign", methods=["POST"])
@require_platform
def platform_docusign(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    envelope_id, error = send_to_docusign(sub, item)
    if envelope_id:
        item.docusign_envelope_id = envelope_id
        item.docusign_status      = "sent"
        item.status               = "docusign_pending"
        db.session.commit()
        flash(f"DocuSign envelope sent for {item.item_label}. ID: {envelope_id[:12]}…", "success")
    else:
        flash(f"DocuSign: {error}", "danger")
    return redirect(url_for("platform_project", sub_id=sub_id))


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/log-response", methods=["POST"])
@require_platform
def platform_item_log_response(sub_id, item_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub_id:
        abort(403)
    rh_response = request.form.get("rh_response", "").strip()
    item.rh_response       = rh_response or None
    item.rh_response_notes = request.form.get("rh_response_notes", "").strip() or None
    item.rh_response_at    = datetime.utcnow()
    if rh_response == "accepted":
        item.status = "under_review"
        flash(f"{item.item_label}: Rights holder accepted — ready to send DocuSign.", "success")
    elif rh_response == "declined":
        item.status = "in_progress"
        flash(f"{item.item_label}: Rights holder declined — item returned to submitter.", "warning")
    else:
        flash(f"{item.item_label}: Counter offer logged.", "info")
    db.session.commit()
    return redirect(url_for("platform_project", sub_id=sub_id))


# ---------------------------------------------------------------------------
# Clearance Guidelines
# ---------------------------------------------------------------------------

_GUIDELINE_SYSTEM = """You are a senior streaming-platform Business Affairs attorney writing internal clearance guidelines. These guidelines will be read by BA staff when processing incoming clearance submissions. Write in plain English. Be specific, practical, and actionable. No legal boilerplate — these are internal operating instructions, not agreements."""

def _guideline_user_prompt(project_type, platform_name, item_labels):
    items_list = "\n".join(f"- {l}" for l in item_labels)
    return (
        f"Write clearance guidelines for a {platform_name} BA reviewing a **{project_type.replace('_', ' ').title()}** submission.\n\n"
        f"The clearance items for this project type are:\n{items_list}\n\n"
        f"For each item write:\n"
        f"1. What to look for / what rights are needed\n"
        f"2. Common issues and red flags\n"
        f"3. Standard deal terms / what to accept vs. push back on\n"
        f"4. Who the typical counterparty is and how to reach them\n\n"
        f"Platform rules that apply to ALL agreements on this platform:\n"
        f"- Agreements are between Producer/Submitter and Licensor — platform is never a party\n"
        f"- Producer/Submitter indemnifies platform from all third-party claims\n"
        f"- All rights must be assignable to platform without licensor consent\n"
        f"- Chain of title must be clear and unbroken\n"
        f"- E&O ($1M/$3M) + CGL ($1M) insurance required; platform as additional insured\n\n"
        f"Format with a ## header per clearance item. Be specific, not generic."
    )


@app.route("/platform/guidelines")
@require_platform
def platform_guidelines():
    user = current_platform_user()
    platform = Platform.query.get(user.platform_id)
    guidelines = {
        g.project_type: g
        for g in ClearanceGuideline.query.filter_by(platform_id=user.platform_id).all()
    }
    project_types = list(PROJECT_TYPE_LABELS.items())  # [(key, label), ...]
    return render_template(
        "platform/guidelines.html",
        platform=platform, platform_user=user,
        guidelines=guidelines, project_types=project_types,
        clearance_templates=CLEARANCE_TEMPLATES,
    )


@app.route("/platform/guidelines/<project_type>", methods=["GET", "POST"])
@require_platform
def platform_guideline_detail(project_type):
    if project_type not in PROJECT_TYPE_LABELS:
        abort(404)
    user = current_platform_user()
    platform = Platform.query.get(user.platform_id)
    g = ClearanceGuideline.query.filter_by(
        platform_id=user.platform_id, project_type=project_type
    ).first()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "ai_draft":
            item_labels = [t["label"] for t in CLEARANCE_TEMPLATES.get(project_type, [])]
            try:
                content = call_claude(
                    _GUIDELINE_SYSTEM,
                    _guideline_user_prompt(project_type, platform.name, item_labels),
                    max_tokens=4000,
                )
            except Exception as e:
                flash(f"AI draft failed: {e}", "danger")
                return redirect(url_for("platform_guideline_detail", project_type=project_type))
            if not g:
                g = ClearanceGuideline(platform_id=user.platform_id, project_type=project_type)
                db.session.add(g)
            g.content = content
            g.status = "draft"
            db.session.commit()
            flash("AI draft generated. Review and approve when ready.", "success")

        elif action == "save":
            if not g:
                g = ClearanceGuideline(platform_id=user.platform_id, project_type=project_type)
                db.session.add(g)
            g.content = request.form.get("content", "").strip()
            g.public_content = request.form.get("public_content", "").strip()
            g.show_to_submitters = request.form.get("show_to_submitters") == "1"
            g.status = "draft"
            db.session.commit()
            flash("Guidelines saved as draft.", "success")

        elif action == "approve":
            if g and g.content:
                g.status = "approved"
                g.approved_by = user.username
                g.approved_at = datetime.utcnow()
                g.version = (g.version or 1) + 1
                db.session.commit()
                flash("Guidelines approved and published.", "success")
            else:
                flash("Nothing to approve — generate or save a draft first.", "warning")

        return redirect(url_for("platform_guideline_detail", project_type=project_type))

    return render_template(
        "platform/guideline_detail.html",
        platform=platform, platform_user=user,
        guideline=g, project_type=project_type,
        project_type_label=PROJECT_TYPE_LABELS[project_type],
        clearance_items=CLEARANCE_TEMPLATES.get(project_type, []),
    )


# ---------------------------------------------------------------------------
# Legal pages (public)
# ---------------------------------------------------------------------------

@app.route("/privacy")
def privacy_policy():
    return render_template("privacy.html")


@app.route("/terms")
def terms_of_service():
    return render_template("terms.html")


# ---------------------------------------------------------------------------
# Orchestrator — proactive action queues + digest
# ---------------------------------------------------------------------------

STALL_DAYS = 4   # no rights-holder reply after this many days → flag a follow-up


def _last_outbound_at(item):
    for turn in reversed(item.negotiation_log or []):
        if turn.get("role") == "outbound" and turn.get("ts"):
            try:
                return datetime.fromisoformat(turn["ts"])
            except Exception:
                return item.ai_outreach_sent_at
    return item.ai_outreach_sent_at


def _scan_submitter_actions(sub):
    """What does the submitter need to do, right now, across this submission?"""
    actions = []
    for it in sub.clearance_items:
        if it.status in ("cleared", "waived", "n_a", "under_review"):
            continue
        if it.neg_state == "needs_approval":
            rec = it.ai_recommendation or {}
            if rec.get("recommended_action") == "send_for_signature":
                actions.append({"item_id": it.id, "label": it.item_label, "urgency": "high",
                                "action": "Approve & send for signature",
                                "detail": "AI says terms are agreed — one click to send the agreement."})
            else:
                actions.append({"item_id": it.id, "label": it.item_label, "urgency": "high",
                                "action": "Approve the AI's drafted reply",
                                "detail": rec.get("assessment") or "AI has drafted your next move."})
        elif it.neg_state == "awaiting_reply":
            last = _last_outbound_at(it)
            if last and (datetime.utcnow() - last) > timedelta(days=STALL_DAYS):
                days = (datetime.utcnow() - last).days
                actions.append({"item_id": it.id, "label": it.item_label, "urgency": "medium",
                                "action": "Follow up — no reply",
                                "detail": f"No response in {days} days. Record a reply or send a nudge."})
        elif it.status == "pending":
            actions.append({"item_id": it.id, "label": it.item_label, "urgency": "low",
                            "action": "Start clearance", "detail": "Not started yet."})
        elif it.status == "in_progress" and not it.ai_outreach_sent_at:
            actions.append({"item_id": it.id, "label": it.item_label, "urgency": "medium",
                            "action": "Send outreach",
                            "detail": "Add the rights holder contact and send the request."})
    return actions


def _scan_ba_actions(platform):
    """What does the platform BA need to sign off on or review?"""
    actions = []
    for sub in Submission.query.filter_by(platform_id=platform.id).all():
        if sub.is_fully_cleared and sub.status != "cleared":
            actions.append({"sub_id": sub.id, "title": sub.title, "item": None, "urgency": "high",
                            "action": "Give final clearance sign-off",
                            "detail": "All items approved — mark the submission cleared."})
        for it in sub.clearance_items:
            if it.status == "under_review":
                actions.append({"sub_id": sub.id, "title": sub.title, "item": it.item_label, "urgency": "high",
                                "action": "Sign off or reject",
                                "detail": "Submitter sent this for your review."})
            elif it.neg_state == "needs_approval" and (it.ai_recommendation or {}).get("recommended_action") == "escalate_to_ba":
                actions.append({"sub_id": sub.id, "title": sub.title, "item": it.item_label, "urgency": "medium",
                                "action": "AI escalated — advise submitter",
                                "detail": (it.ai_recommendation or {}).get("assessment") or "Outside standard authority."})
            elif it.status == "docusign_pending":
                actions.append({"sub_id": sub.id, "title": sub.title, "item": it.item_label, "urgency": "low",
                                "action": "Awaiting signature", "detail": "Out for DocuSign signature."})
    return actions


def _send_digest_email(to_addr, subject, html_body):
    resend_key = os.getenv("RESEND_API_KEY")
    if not resend_key:
        return False
    try:
        import resend as _resend
        _resend.api_key = resend_key
        _resend.Emails.send({
            "from": "Cleared.live <clear@cleared.live>",
            "to": [to_addr],
            "subject": subject,
            "html": html_body,
        })
        return True
    except Exception as e:
        app.logger.error(f"DIGEST SEND ERROR — {type(e).__name__}: {e}")
        return False


def _digest_rows(actions, link):
    rows = ""
    order = {"high": 0, "medium": 1, "low": 2}
    for a in sorted(actions, key=lambda x: order.get(x.get("urgency"), 3)):
        color = {"high": "#dc2626", "medium": "#d97706", "low": "#64748b"}.get(a.get("urgency"), "#64748b")
        label = a.get("label") or a.get("item") or a.get("title") or ""
        rows += (
            f'<tr><td style="padding:8px 0;border-bottom:1px solid #eee;">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:8px;"></span>'
            f'<strong>{a.get("action","")}</strong> — {label}'
            f'<div style="color:#64748b;font-size:13px;margin-left:16px;">{a.get("detail","")}</div></td></tr>'
        )
    return (
        f'<div style="font-family:system-ui,Arial,sans-serif;max-width:600px;margin:0 auto;">'
        f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
        f'<p style="margin-top:20px;"><a href="{link}" '
        f'style="background:#0d3b6e;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;">Open Cleared.live</a></p></div>'
    )


@app.route("/cron/digest", methods=["GET", "POST"])
def cron_digest():
    """Cron-triggered: email submitters and BAs whatever needs their attention."""
    secret = request.args.get("secret") or request.headers.get("X-Cron-Secret")
    if os.getenv("CRON_SECRET") and secret != os.getenv("CRON_SECRET"):
        abort(403)
    base = request.url_root.rstrip("/")
    sent = {"submitters": 0, "ba": 0}

    active = Submission.query.filter(
        Submission.status.in_(["submitted", "in_review", "in_clearance"])
    ).all()
    for sub in active:
        acts = [a for a in _scan_submitter_actions(sub) if a["urgency"] in ("high", "medium")]
        if acts and sub.submitter_email:
            link = f"{base}{url_for('track', token=sub.token)}"
            if _send_digest_email(sub.submitter_email,
                                  f"Your clearance to-do — {sub.title} ({len(acts)})",
                                  _digest_rows(acts, link)):
                sent["submitters"] += 1

    for platform in Platform.query.filter_by(is_active=True).all():
        acts = [a for a in _scan_ba_actions(platform) if a["urgency"] in ("high", "medium")]
        emails = {u.email for u in platform.users if u.email}
        if platform.ba_contact_email:
            emails.add(platform.ba_contact_email)
        if acts and emails:
            link = f"{base}{url_for('platform_dashboard')}"
            for em in emails:
                _send_digest_email(em, f"Clearance queue — {platform.name}: {len(acts)} need you",
                                   _digest_rows(acts, link))
            sent["ba"] += 1

    return {"ok": True, "sent": sent}, 200


# ---------------------------------------------------------------------------
# Inbound email — auto-capture rights-holder replies into the negotiation
# ---------------------------------------------------------------------------

def _reply_address(item):
    """Per-item Reply-To so inbound replies route back to the right negotiation."""
    if not item.reply_token:
        item.reply_token = secrets.token_urlsafe(12)
    domain = os.getenv("INBOUND_DOMAIN", "cleared.live")
    return f"reply+{item.reply_token}@{domain}"


def _extract_reply_token(to_field):
    import re
    # to_field may be a string, a list of strings, or a list of {address|email} dicts
    candidates = []
    if isinstance(to_field, str):
        candidates = [to_field]
    elif isinstance(to_field, list):
        for t in to_field:
            if isinstance(t, str):
                candidates.append(t)
            elif isinstance(t, dict):
                candidates.append(t.get("address") or t.get("email") or "")
    for c in candidates:
        m = re.search(r"reply\+([A-Za-z0-9_\-]+)@", c or "")
        if m:
            return m.group(1)
    return None


def _clean_reply(text):
    """Trim the most common quoted-history markers so the AI sees just the new message."""
    if not text:
        return ""
    lines, out = text.splitlines(), []
    for ln in lines:
        s = ln.strip()
        if s.startswith(">"):
            break
        if s.startswith("On ") and ("wrote:" in s or s.endswith("wrote:")):
            break
        if "-----Original Message-----" in s or s.startswith("From: "):
            break
        out.append(ln)
    return "\n".join(out).strip() or text.strip()


@app.route("/inbound/email", methods=["POST"])
def inbound_email():
    """Resend inbound webhook → append the reply to the thread and run the AI agent."""
    secret = request.args.get("secret")
    if os.getenv("INBOUND_SECRET") and secret != os.getenv("INBOUND_SECRET"):
        abort(403)
    data = request.get_json(silent=True) or {}
    payload = data.get("data", data)
    to_field = payload.get("to") or payload.get("to_address") or payload.get("recipient") or ""
    text = payload.get("text") or payload.get("body") or payload.get("html") or ""
    token = _extract_reply_token(to_field)
    if not token:
        return {"ok": False, "reason": "no reply token in recipient"}, 200
    item = ClearanceItem.query.filter_by(reply_token=token).first()
    if not item:
        return {"ok": False, "reason": "no matching item"}, 200
    item.negotiation_log_add({
        "role": "inbound", "label": "Rights holder reply (email)",
        "body": _clean_reply(text), "ts": datetime.utcnow().isoformat(),
    })
    item.neg_state = "analyzing"
    item.ai_recommendation_save(None)
    db.session.commit()
    threading.Thread(target=_negotiation_agent, args=(item.id,), daemon=True).start()
    return {"ok": True, "item": item.id}, 200


# ---------------------------------------------------------------------------
# DB init CLI
# ---------------------------------------------------------------------------

@app.cli.command("init-db")
def init_db():
    db.create_all()

    if not AdminUser.query.filter_by(username="admin").first():
        db.session.add(AdminUser(
            username      = "admin",
            email         = "clear@cleared.live",
            password_hash = generate_password_hash("changeme"),
        ))
        db.session.commit()
        print("Admin created — username: admin / password: changeme")

    if not Platform.query.filter_by(slug="amazon-live").first():
        p = Platform(
            name             = "Amazon Live",
            slug             = "amazon-live",
            logo_text        = "Amazon",
            ba_contact_name  = "Patrick Yemidijian",
            ba_contact_email = "pyemidijian@amazon.com",
            tier             = "enterprise",
            primary_color    = "#FF9900",
            accepted_types   = "live_music,documentary,unscripted,social",
        )
        db.session.add(p)
        db.session.flush()
        db.session.add(PlatformUser(
            platform_id   = p.id,
            username      = "amazon_ba",
            email         = "pyemidijian@amazon.com",
            password_hash = generate_password_hash("amazon123"),
            role          = "admin",
        ))
        db.session.commit()
        print(f"Amazon Live platform created.")
        print(f"  BA login:  amazon_ba / amazon123")
        print(f"  API key:   {p.api_key}")
        print(f"  Submit URL: http://localhost:5002/submit/amazon-live")

    # Add more demo platforms
    demos = [
        ("Netflix", "netflix",     "Netflix",  "#E50914", "standard",    "live_music,documentary,unscripted,social,ugc,podcast"),
        ("YouTube", "youtube",     "YouTube",  "#FF0000", "standard",    "live_music,documentary,unscripted,social,ugc,podcast"),
        ("HBO",     "hbo",         "HBO",      "#1E1E1E", "standard",    "live_music,documentary,unscripted,social,ugc"),
        ("UMG",     "umg",         "UMG",      "#003087", "enterprise",  "live_music,documentary,unscripted,social,ugc,podcast"),
        ("Spotify", "spotify",     "Spotify",  "#1DB954", "enterprise",  "live_music,podcast,social,ugc"),
    ]
    for name, slug, logo, color, tier, accepted in demos:
        if not Platform.query.filter_by(slug=slug).first():
            db.session.add(Platform(
                name=name, slug=slug, logo_text=logo,
                tier=tier, primary_color=color,
                accepted_types=accepted,
            ))
    db.session.commit()
    print("Demo platforms: Netflix, YouTube, HBO, UMG, Spotify")
    print("\nDatabase ready.")


@app.cli.command("add-platform")
def add_platform_cmd():
    """Add Spotify, Sony, Warner, UMG to the live database (safe to re-run)."""
    # (name, slug, logo, color, tier, accepted_types, platform_mode)
    demos = [
        ("Spotify",        "spotify",        "Spotify",  "#1DB954", "enterprise", "live_music,podcast,social,ugc",                          "clearance"),
        ("YouTube",        "youtube",        "YouTube",  "#FF0000", "enterprise", "live_music,documentary,unscripted,social,ugc,podcast",    "clearance"),
        ("Amazon",         "amazon",         "Amazon",   "#FF9900", "enterprise", "live_music,documentary,unscripted,social,ugc,podcast",    "clearance"),
        ("Apple TV+",      "apple-tv",       "Apple TV+","#555555", "enterprise", "live_music,documentary,unscripted,podcast",               "clearance"),
        ("HBO / Max",      "hbo-max",        "Max",      "#6A1B9A", "enterprise", "live_music,documentary,unscripted",                       "clearance"),
        ("Hulu",           "hulu",           "Hulu",     "#1CE783", "enterprise", "live_music,documentary,unscripted,social",                "clearance"),
        ("Sony Music",     "sony",           "Sony",     "#000000", "enterprise", "live_music",                                              "label_waiver"),
        ("Warner Records", "warner-records", "Warner",   "#0099FF", "enterprise", "live_music",                                              "label_waiver"),
        ("UMG",            "umg-label",      "UMG",      "#003087", "enterprise", "live_music",                                              "label_waiver"),
    ]
    for name, slug, logo, color, tier, accepted, mode in demos:
        if Platform.query.filter_by(slug=slug).first():
            print(f"  {name}: already exists — skipping")
            continue
        p = Platform(
            name=name, slug=slug, logo_text=logo,
            tier=tier, primary_color=color,
            accepted_types=accepted, platform_mode=mode,
        )
        db.session.add(p)
        db.session.commit()
        ba_user = slug.replace("-", "_") + "_ba"
        ba_pass = slug.replace("-", "_") + "123"
        print(f"  {name} ({mode}) created — submit URL: /submit/{slug}")
        print(f"  Create BA login: flask create-ba-user {slug} {ba_user} {ba_pass}")



@app.cli.command("create-ba-user")
@click.argument("platform_slug")
@click.argument("username")
@click.argument("password")
def create_ba_user_cmd(platform_slug, username, password):
    """Create a BA login for a platform. Usage: flask create-ba-user <slug> <username> <password>"""
    p = Platform.query.filter_by(slug=platform_slug).first()
    if not p:
        print(f"Platform '{platform_slug}' not found.")
        return
    if PlatformUser.query.filter_by(username=username).first():
        print(f"User '{username}' already exists.")
        return
    db.session.add(PlatformUser(
        platform_id=p.id, username=username, email=f"{username}@cleared.live",
        password_hash=generate_password_hash(password), role="admin",
    ))
    db.session.commit()
    print(f"Created {username} for {p.name} — login at /platform/login")


@app.cli.command("migrate-db")
def migrate_db_cmd():
    """Add new columns and tables (safe to re-run).

    ClearanceItem.status now supports: pending | in_progress | under_review | cleared | waived | n_a
    No DB schema change needed for 'under_review' — it uses the existing VARCHAR status column.
    """
    item_cols = [
        ("ai_draft",             "TEXT"),
        ("ai_deal_points",       "TEXT"),
        ("ai_outreach_body",     "TEXT"),
        ("ai_outreach_sent_at",  "TIMESTAMP"),
        ("docusign_envelope_id", "VARCHAR(100)"),
        ("docusign_status",      "VARCHAR(50)"),
        ("party_email",          "VARCHAR(200)"),
        ("party_company",        "VARCHAR(200)"),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in item_cols:
            try:
                conn.execute(sa_text(
                    f"ALTER TABLE clearance_items ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                conn.commit()
                print(f"  clearance_items.{col_name} OK")
            except Exception as exc:
                conn.rollback()
                print(f"  clearance_items.{col_name}: {exc}")
        # Create clearance_guidelines table if missing
        try:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS clearance_guidelines (
                    id                 SERIAL PRIMARY KEY,
                    platform_id        INTEGER NOT NULL REFERENCES platforms(id),
                    project_type       VARCHAR(30) NOT NULL,
                    content            TEXT,
                    public_content     TEXT,
                    show_to_submitters BOOLEAN DEFAULT FALSE,
                    status             VARCHAR(20) DEFAULT 'draft',
                    approved_by        VARCHAR(100),
                    approved_at        TIMESTAMP,
                    version            INTEGER DEFAULT 1,
                    created_at         TIMESTAMP DEFAULT NOW(),
                    updated_at         TIMESTAMP DEFAULT NOW(),
                    UNIQUE(platform_id, project_type)
                )
            """))
            conn.commit()
            print("  clearance_guidelines table OK")
        except Exception as exc:
            conn.rollback()
            print(f"  clearance_guidelines: {exc}")
        # Add platform_mode to platforms table
        try:
            conn.execute(sa_text(
                "ALTER TABLE platforms ADD COLUMN IF NOT EXISTS platform_mode VARCHAR(20) DEFAULT 'clearance'"
            ))
            conn.commit()
            print("  platforms.platform_mode OK")
        except Exception as exc:
            conn.rollback()
            print(f"  platforms.platform_mode: {exc}")
        # Create invites table if missing (invite-only gate)
        try:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS invites (
                    id            SERIAL PRIMARY KEY,
                    platform_id   INTEGER NOT NULL REFERENCES platforms(id),
                    email         VARCHAR(200) NOT NULL,
                    name          VARCHAR(200),
                    project_hint  VARCHAR(300),
                    token         VARCHAR(100) UNIQUE NOT NULL,
                    created_at    TIMESTAMP DEFAULT NOW(),
                    used_at       TIMESTAMP,
                    submission_id INTEGER REFERENCES submissions(id)
                )
            """))
            conn.commit()
            print("  invites table OK")
        except Exception as exc:
            conn.rollback()
            print(f"  invites: {exc}")
        # Add public columns to existing clearance_guidelines table
        for col_name, col_type in [("public_content", "TEXT"), ("show_to_submitters", "BOOLEAN DEFAULT FALSE")]:
            try:
                conn.execute(sa_text(
                    f"ALTER TABLE clearance_guidelines ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                conn.commit()
                print(f"  clearance_guidelines.{col_name} OK")
            except Exception as exc:
                conn.rollback()
                print(f"  clearance_guidelines.{col_name}: {exc}")
        # Add platform form-config columns
        for col_name, col_type in [
            ("form_territory",             "VARCHAR(50)"),
            ("form_territory_locked",      "BOOLEAN DEFAULT FALSE"),
            ("form_intended_use",          "VARCHAR(300)"),
            ("form_intended_use_locked",   "BOOLEAN DEFAULT FALSE"),
            ("negotiation_positions_json", "TEXT"),
        ]:
            try:
                conn.execute(sa_text(
                    f"ALTER TABLE platforms ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                conn.commit()
                print(f"  platforms.{col_name} OK")
            except Exception as exc:
                conn.rollback()
                print(f"  platforms.{col_name}: {exc}")
        # Add songs_json to submissions
        try:
            conn.execute(sa_text(
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS songs_json TEXT"
            ))
            conn.commit()
            print("  submissions.songs_json OK")
        except Exception as exc:
            conn.rollback()
            print(f"  submissions.songs_json: {exc}")
        # Add deal_terms_json to submissions
        try:
            conn.execute(sa_text(
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS deal_terms_json TEXT"
            ))
            conn.commit()
            print("  submissions.deal_terms_json OK")
        except Exception as exc:
            conn.rollback()
            print(f"  submissions.deal_terms_json: {exc}")
        # Add publishing_notes to submissions
        try:
            conn.execute(sa_text(
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS publishing_notes TEXT"
            ))
            conn.commit()
            print("  submissions.publishing_notes OK")
        except Exception as exc:
            conn.rollback()
            print(f"  submissions.publishing_notes: {exc}")
        # Add deal_terms_json to clearance_items
        try:
            conn.execute(sa_text(
                "ALTER TABLE clearance_items ADD COLUMN IF NOT EXISTS deal_terms_json TEXT"
            ))
            conn.commit()
            print("  clearance_items.deal_terms_json OK")
        except Exception as exc:
            conn.rollback()
            print(f"  clearance_items.deal_terms_json: {exc}")
        for col_name, col_type in [
            ("rh_response", "VARCHAR(20)"),
            ("rh_response_notes", "TEXT"),
            ("rh_response_at", "TIMESTAMP"),
            ("neg_state", "VARCHAR(30)"),
            ("negotiation_log_json", "TEXT"),
            ("ai_recommendation_json", "TEXT"),
            ("reply_token", "VARCHAR(60)"),
        ]:
            try:
                conn.execute(sa_text(f"ALTER TABLE clearance_items ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                conn.commit()
                print(f"  clearance_items.{col_name} OK")
            except Exception as exc:
                conn.rollback()
                print(f"  clearance_items.{col_name}: {exc}")
        try:
            conn.execute(sa_text(
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS publisher_clearances_json TEXT"
            ))
            conn.commit()
            print("  submissions.publisher_clearances_json OK")
        except Exception as exc:
            conn.rollback()
            print(f"  submissions.publisher_clearances_json: {exc}")
    print("Migration complete.")


@app.cli.command("seed-guidelines")
def seed_guidelines_cmd():
    """AI-generate clearance guidelines for all project types across all platforms.
    Run once from Render shell after setting ANTHROPIC_API_KEY. Safe to re-run —
    skips any project type that already has approved guidelines."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — cannot generate guidelines.")
        return

    platforms = Platform.query.filter_by(is_active=True).all()
    project_types = list(PROJECT_TYPE_LABELS.keys())

    for platform in platforms:
        print(f"\n=== {platform.name} ===")
        for ptype in project_types:
            existing = ClearanceGuideline.query.filter_by(
                platform_id=platform.id, project_type=ptype, status="approved"
            ).first()
            if existing:
                print(f"  {ptype}: already approved — skipping")
                continue

            item_labels = [t["label"] for t in CLEARANCE_TEMPLATES.get(ptype, [])]
            print(f"  {ptype}: generating...", end="", flush=True)
            try:
                content = call_claude(
                    _GUIDELINE_SYSTEM,
                    _guideline_user_prompt(ptype, platform.name, item_labels),
                    max_tokens=4000,
                )
                g = ClearanceGuideline.query.filter_by(
                    platform_id=platform.id, project_type=ptype
                ).first()
                if not g:
                    g = ClearanceGuideline(platform_id=platform.id, project_type=ptype)
                    db.session.add(g)
                g.content = content
                g.status = "approved"
                g.approved_by = "seed-guidelines"
                g.approved_at = datetime.utcnow()
                g.version = 1
                db.session.commit()
                print(" done")
            except Exception as e:
                print(f" FAILED: {e}")

    print("\nGuideline seeding complete.")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
