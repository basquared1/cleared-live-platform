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
    session, flash, jsonify, abort, send_file, send_from_directory, Response, g,
)
from sqlalchemy import text as sa_text
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _gph

def generate_password_hash(s):
    return _gph(s, method="pbkdf2:sha256")

from models import (
    db, Platform, Submission, ClearanceItem, SubmissionDocument,
    WebhookDelivery, PlatformUser, AdminUser, ClearanceGuideline, Invite,
    Template, DealTerm, FestivalArtist, ProjectContact, ReleaseRequest,
    CLEARANCE_TEMPLATES, PRICING_TIERS, PROJECT_TYPE_LABELS,
    TERRITORY_LABELS, INTENDED_USE_OPTIONS,
    MUSIC_ITEM_KEYS, is_music_item,
    PRODUCTION_PROJECT_TYPES, CREW_ROLES, CREW_ROLE_LABELS,
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

_CLP_SYSTEM_PROMPT = """You are a SENIOR music and entertainment Business & Legal Affairs attorney drafting clearance agreements. Depending on the matter you act for either the Producer/Submitter or the platform, as context requires — but the agreement's party structure always follows the rules below regardless of who you represent. You have 20+ years drafting against majors, sublabels, indies, publishers, promoters, venues, and unions. You write like a senior partner who bills by the result, not the page.

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


def call_claude(system: str, user: str, max_tokens: int = 4000, continue_on_truncation: bool = False) -> str:
    """Call Claude for shorter outputs (deal points, outreach emails).

    Set continue_on_truncation=True for longer outputs (e.g. guideline drafts with
    tables/checklists) to re-prompt and append when a pass hits the max_tokens limit.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")
    client = _anthropic.Anthropic(api_key=api_key)
    cached = _cached_system(system)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=cached,
        messages=[{"role": "user", "content": user}],
    )
    text = message.content[0].text
    if continue_on_truncation:
        # Re-prompt up to twice more if the model runs out of room mid-output.
        for _ in range(2):
            if message.stop_reason != "max_tokens":
                break
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=cached,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "Continue from exactly where you left off. Do not repeat any content. Complete all remaining sections."},
                ],
            )
            text += "\n" + message.content[0].text
    return text


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


def _guideline_block(sub):
    """The platform BA's approved internal clearance guideline for this project type,
    formatted for inclusion in drafting/negotiation prompts. Empty string if none —
    so the AI applies the BA's house rules rather than generic assumptions."""
    try:
        gl = ClearanceGuideline.query.filter_by(
            platform_id=sub.platform_id, project_type=sub.project_type, status="approved",
        ).first()
    except Exception:
        return ""
    if not (gl and gl.content):
        return ""
    return (
        "\n\nPLATFORM BA CLEARANCE GUIDELINES (authoritative house rules — follow these "
        "when drafting; they take precedence over generic assumptions):\n"
        + gl.content.strip() + "\n"
    )


def _item_rights_holder(sub, item):
    """Best-known rights holder for a clearance item — the counterparty if set,
    otherwise the record label for master/label items (the label controls the master)."""
    if item.party_company or item.party_name:
        return item.party_company or item.party_name
    key = (item.item_key or "")
    if ("master" in key or "label" in key) and (sub.label or "").strip():
        return sub.label.strip()
    return ""


def _build_clearance_doc_user_prompt(sub, item, ai_only=False):
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
            + _guideline_block(sub)
        )

    rh = _item_rights_holder(sub, item)
    agreed_block = _agreed_points_block(_item_deal_points(item))
    afee = _agreed_fee(_item_deal_points(item))
    dtt = item.deal_terms or {}
    cue_days = dtt.get("cue_sheet_days") or 30
    if afee is not None:
        fee_line = f"LICENSE FEE: ${afee:,.0f} (agreed) — insert this exact figure.\n"
    elif dtt.get("fee"):
        fee_line = (f"LICENSE FEE: ${dtt.get('fee')} (proposed, not yet agreed) — use it but note it is "
                    "subject to final agreement.\n")
    else:
        fee_line = ("LICENSE FEE: not yet agreed — the fee is set after negotiation, so leave a single [FEE] "
                    "placeholder and do NOT invent a number.\n")
    return (
        f"Draft a professional {item.item_label} for the following project.\n\n"
        f"CONTRACTING PARTY (Producer/Submitter): {sub.submitter_company or sub.submitter_name}. "
        f"The agreement is between this Producer/Submitter and the Licensor/Rights Holder. "
        f"{sub.platform.name} is named ONLY as assignee of the granted rights — it is NOT a contracting party, "
        f"and the Producer/Submitter does NOT act 'on behalf of' {sub.platform.name}.\n\n"
        f"PROJECT DETAILS:\n{_sub_context(sub)}\n\n"
        f"CLEARANCE ITEM: {item.item_label}\n"
        + (f"LICENSOR / RIGHTS HOLDER: {rh}\n" if rh else "LICENSOR / RIGHTS HOLDER: [RIGHTS HOLDER]\n")
        + (f"AGREED / PROPOSED DEAL TERMS (use these real values verbatim — do not bracket them):\n{agreed_block}\n"
           if agreed_block else "")
        + fee_line
        + f"STANDARD PERIODS: use 5 business days for any notice or cure period, and {cue_days} days for "
          f"cue-sheet delivery, unless a deal term says otherwise.\n"
        + _guideline_block(sub)
        + ("" if ai_only else _template_block(item))
        + "\nUse the real values above wherever possible. Only bracket a value that is genuinely unknown — "
          "e.g. the rights holder's exact legal entity type/state, or the fee if not yet agreed. "
          "Draft the complete agreement now."
    )


def _template_block(item):
    """If a firm-approved template exists for this item type (folded in from PLB),
    instruct the model to use it as the structural basis. Empty string if none."""
    try:
        tpl = Template.query.filter_by(doc_type=item.item_key, is_active=True).first()
    except Exception:
        tpl = None
    if not tpl or not tpl.content:
        return ""
    try:
        tpl.times_used = (tpl.times_used or 0) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()
    return (
        f"\n\nFIRM-APPROVED TEMPLATE — use this as the structural and clause basis for your draft. "
        f"Preserve its structure, defined terms, and protective language; adapt the bracketed "
        f"placeholders to the project details above and tighten anything project-specific:\n"
        f"-----8<----- TEMPLATE: {tpl.name} -----8<-----\n{tpl.content}\n-----8<----- END TEMPLATE -----8<-----\n"
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


def generate_draft(sub, item, ai_only=False):
    """Generate full agreement text using the attorney system prompt.
    ai_only=True drafts from scratch without the firm-approved template (secondary path)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    user_prompt = _build_clearance_doc_user_prompt(sub, item, ai_only=ai_only)
    return call_claude_document(_CLP_SYSTEM_PROMPT, user_prompt)


def generate_outreach(sub, item):
    """Generate a clearance outreach email."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    salutation = item.party_name if item.party_name else "[Rights Holder]"
    platform_name = sub.platform.name if sub.platform else "the platform"
    system = (
        "You are a music clearance professional helping a content producer draft outreach emails to rights holders. "
        "The email is sent BY the producer/submitter, in their own name and company — NOT by the platform. "
        f"Reference the project and the platform ({platform_name}) it will stream on as context only; never write that "
        "the sender is contacting anyone 'on behalf of' the platform, and never imply the sender works for or represents the platform. "
        "You draft concise, professional outreach emails to rights holders requesting clearance. "
        "Never include a subject line. Write 175–225 words. "
        "Do NOT use placeholder brackets like [Name] or [Rights Holder] — use the actual names provided."
    )
    user = (
        f"Write a professional clearance outreach email requesting a {item.item_label} for:\n"
        f"{_sub_context(sub)}\n\n"
        f"Start with 'Dear {salutation},'. State exactly what rights are being requested, "
        f"for which project, referencing {platform_name} only as where the finished project will stream "
        f"(the sender is the producer making the request — not writing on behalf of {platform_name}). "
        f"Reference event details, request a response within 5 business days, "
        f"and close professionally. Signature is: {sub.submitter_name or ''}"
        + (f"\n{sub.submitter_company}" if sub.submitter_company else "") + ". No 'on behalf of' in the closing."
        + _guideline_block(sub)
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

    draft_text = item.ai_draft or f"[Draft pending for {item.item_label}]"
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


def _ds_envelope_status(ds_base, access_token, account_id, envelope_id):
    """Current status of a DocuSign envelope (lowercased), or None on error."""
    r = http_requests.get(
        f"{ds_base}/v2.1/accounts/{account_id}/envelopes/{envelope_id}",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=20,
    )
    if r.ok:
        return (r.json().get("status") or "").lower()
    return None


def _ds_download_combined_pdf(ds_base, access_token, account_id, envelope_id):
    """Download the combined, fully-executed PDF (all documents + certificate)."""
    r = http_requests.get(
        f"{ds_base}/v2.1/accounts/{account_id}/envelopes/{envelope_id}/documents/combined",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/pdf"},
        timeout=60,
    )
    if r.ok and r.content:
        return r.content
    return None


def fetch_executed_envelope(item):
    """If the item's DocuSign envelope is completed, download the executed PDF and
    store it as an 'executed' SubmissionDocument so the agreement lands in the
    record automatically. Idempotent — a no-op if a copy is already on file.

    Mutates the session (adds the doc / updates docusign_status) but does NOT
    commit — the caller commits. Returns (stored: bool, message: str)."""
    if not item.docusign_envelope_id:
        return False, "No DocuSign envelope on this item."
    if not docusign_configured():
        return False, "DocuSign not configured."
    # Already captured the executed copy for this envelope? Nothing to do.
    if SubmissionDocument.query.filter_by(
            clearance_item_id=item.id, doc_type="executed").first():
        return False, "Executed copy already on file."
    try:
        access_token, ds_base = get_docusign_token()
    except Exception as e:
        return False, f"DocuSign auth failed: {e}"
    account_id = os.getenv("DOCUSIGN_ACCOUNT_ID")
    status = _ds_envelope_status(ds_base, access_token, account_id, item.docusign_envelope_id)
    if status != "completed":
        if status and status != (item.docusign_status or "").lower():
            item.docusign_status = status   # keep our local mirror current
        return False, f"Envelope status is '{status or 'unknown'}', not completed yet."
    pdf = _ds_download_combined_pdf(ds_base, access_token, account_id, item.docusign_envelope_id)
    if not pdf:
        return False, "Envelope completed but the executed PDF download failed."
    safe = re.sub(r"[^A-Za-z0-9]+", "-", item.item_label).strip("-").lower() or "agreement"
    db.session.add(SubmissionDocument(
        submission_id     = item.submission_id,
        clearance_item_id = item.id,
        title             = f"Executed agreement — {item.item_label}",
        doc_type          = "executed",
        filename          = f"{safe}-executed.pdf",
        file_data         = pdf,
        mimetype          = "application/pdf",
        uploaded_by       = "DocuSign",
    ))
    item.docusign_status = "completed"
    item.negotiation_log_add({
        "role": "system",
        "label": "Executed agreement received from DocuSign",
        "body": "The fully executed agreement was downloaded from DocuSign and stored to the project record.",
        "ts": datetime.utcnow().isoformat(),
    })
    return True, "Executed agreement stored."


def _parse_connect_payload(req):
    """Extract (envelope_id, status) from a DocuSign Connect payload — tolerant of
    the newer JSON ('Connect') format and the legacy XML/SOAP format."""
    data = req.get_json(silent=True)
    if isinstance(data, dict):
        d = data.get("data") if isinstance(data.get("data"), dict) else {}
        env = d.get("envelopeId") or data.get("envelopeId")
        status = ((d.get("envelopeSummary") or {}).get("status")
                  or data.get("status") or data.get("event"))
        if env:
            return env, (status or "").lower().replace("envelope-", "")
    raw = req.get_data(as_text=True) or ""
    if "<EnvelopeID>" in raw or "<EnvelopeStatus" in raw:
        m_id = re.search(r"<EnvelopeID>([^<]+)</EnvelopeID>", raw)
        m_st = re.search(r"<Status>([^<]+)</Status>", raw)
        if m_id:
            return m_id.group(1), (m_st.group(1).lower() if m_st else "")
    return None, None


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


def _ensure_deal_terms(sub, item):
    """Default an item's deal terms to the platform BA's primary negotiation
    position when none are set, so outreach can be sent without the submitter
    re-entering terms the platform already mandates. Returns the deal terms."""
    dt = item.deal_terms or {}
    if dt.get("territory") or dt.get("media_rights"):
        return dt
    positions = sub.platform.negotiation_positions if sub.platform else []
    primary = positions[0] if isinstance(positions, list) and positions else {}
    dt = {
        **dt,
        "territory":    dt.get("territory")    or primary.get("territory") or "worldwide",
        "term":         dt.get("term")         or primary.get("term")      or "perpetuity",
        "media_rights": dt.get("media_rights") or primary.get("uses")      or ["streaming"],
    }
    item.deal_terms_save(dt)
    return dt


def _auto_outreach_agent(item_id):
    """Background thread: fully STAGE outreach when an item → in_progress so the
    submitter can send with a single click. Does NOT send — it AI-fills the
    rights-holder contact if missing, drafts the outreach, and defaults deal
    terms to the platform's primary position. The submitter clicks Send."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return
    with app.app_context():
        item = ClearanceItem.query.get(item_id)
        if not item:
            return
        sub = item.submission

        # AI-fill the rights-holder contact if we don't have one yet, so the
        # Send button is actionable. The submitter still confirms by clicking Send.
        if not item.party_email:
            # The artist is only SEARCH context for the lookup — never the company.
            hint = item.party_company or sub.artist_name or sub.label or sub.title
            data = _ai_contact_lookup(sub, item, hint)
            if data and data.get("contact_email"):
                item.party_company = (item.party_company or (data.get("contact_company") or "").strip()
                                      or _item_rights_holder(sub, item) or None)
                item.party_name    = item.party_name or data.get("contact_name")
                item.party_email   = (data.get("contact_email") or "").lower()

        # Draft the outreach email (does not send).
        if not item.ai_outreach_body:
            try:
                body = generate_outreach(sub, item)
                if body:
                    item.ai_outreach_body = body
            except Exception:
                pass

        # Default deal terms to the platform BA's primary position.
        _ensure_deal_terms(sub, item)

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
        + (f"DEAL POINTS ALREADY AGREED (do not reopen these):\n{_agreed_points_block(_item_deal_points(item))}\n\n"
           if _agreed_points_block(_item_deal_points(item)) else "")
        + f"PLATFORM NEGOTIATION POSITIONS (primary first, then fallbacks):\n{_fmt_negotiation_positions(positions)}\n"
        + _guideline_block(sub) + "\n"
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

# Public, login-free marketing/onboarding walkthroughs — shareable at /walkthroughs.
# Self-contained static HTML in the repo's walkthroughs/ folder.
WALKTHROUGHS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "walkthroughs")


@app.route("/walkthroughs")
@app.route("/walthroughs")      # common typo (missing 'k')
@app.route("/walkthrough")      # singular
def walkthroughs_redirect():
    # Redirect to the trailing-slash form so the hub's relative links resolve under /walkthroughs/.
    return redirect("/walkthroughs/", code=301)


@app.route("/walkthroughs/")
def walkthroughs_index():
    return send_from_directory(WALKTHROUGHS_DIR, "index.html")


@app.route("/walkthroughs/<path:filename>")
def walkthroughs_file(filename):
    # send_from_directory safely rejects path traversal; only serve .html files.
    if not filename.endswith(".html"):
        abort(404)
    return send_from_directory(WALKTHROUGHS_DIR, filename)


@app.route("/favicon.ico")
def favicon_ico():
    # Browsers and webview/desktop tab contexts request /favicon.ico at the site
    # root and ignore the <link rel="icon"> tags. Serve the C-clef .ico here.
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/apple-touch-icon.png")
@app.route("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    # iOS/Safari fetch these at the root regardless of <link> tags.
    return send_from_directory(
        os.path.join(app.root_path, "static"), "apple-touch-icon.png"
    )


@app.route("/")
def index():
    return render_template("index.html", pricing_tiers=PRICING_TIERS)


@app.route("/start")
def start():
    """Submitter entry point — choose a platform to request an invite from, or clear independently."""
    platforms   = Platform.query.filter_by(is_active=True).order_by(Platform.name).all()
    distributors = [p for p in platforms if p.platform_mode != "label_waiver"]
    labels       = [p for p in platforms if p.platform_mode == "label_waiver"]
    return render_template(
        "start.html",
        distributors=distributors,
        labels=labels,
        pricing_tiers=PRICING_TIERS,
    )


@app.route("/start/request/<platform_slug>", methods=["POST"])
def request_invite(platform_slug):
    """A submitter asks a connected platform's BA team for an invite to submit a project.
    Creates a tracked invite and notifies the platform BA (falls back to Cleared.live ops)."""
    platform = Platform.query.filter_by(slug=platform_slug, is_active=True).first_or_404()

    email        = request.form.get("email", "").strip().lower()
    name         = request.form.get("name", "").strip()
    project_hint = request.form.get("project_hint", "").strip()

    if not email:
        flash("Please enter your email so the platform can send your invite.", "danger")
        return redirect(url_for("start"))

    invite = Invite(
        platform_id  = platform.id,
        email        = email,
        name         = name or None,
        project_hint = project_hint or None,
    )
    db.session.add(invite)
    db.session.commit()

    invite_url = url_for("submit", platform_slug=platform.slug, invite=invite.token, _external=True)
    ba_to      = platform.ba_contact_email or "clear@cleared.live"

    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        import resend as _resend
        _resend.api_key = resend_key
        try:
            _resend.Emails.send({
                "from": "Cleared.live <clear@cleared.live>",
                "to": ba_to,
                "subject": f"Invite request — {name or email} wants to submit to {platform.name}",
                "html": (
                    f"<p><strong>{name or email}</strong> has requested an invite to submit a "
                    f"clearance project to <strong>{platform.name}</strong>.</p>"
                    f"<p><strong>Name:</strong> {name or '—'}<br>"
                    f"<strong>Email:</strong> {email}<br>"
                    f"<strong>Project:</strong> {project_hint or '—'}</p>"
                    f"<p>An invite has been created in your dashboard. To grant access, "
                    f"forward this personal link to the submitter:</p>"
                    f"<p><a href=\"{invite_url}\">{invite_url}</a></p>"
                ),
            })
        except Exception as e:
            app.logger.error(f"Invite-request email failed: {e}")

    flash(
        f"Request sent to {platform.name}. Their clearance team will email your invite to {email}.",
        "success",
    )
    return redirect(url_for("start"))


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
    sub = _sub(token)
    return render_template("submit_confirm.html", sub=sub)


# ---------------------------------------------------------------------------
# Submitter — token-based status tracker (no login)
# ---------------------------------------------------------------------------

# A submission is reachable by two tokens: the primary `token` (full access) and
# an optional `music_access_token` (delegated music supervisor — Music Clearance
# section only). _MUSIC_SCOPE_ENDPOINTS lists the view functions a music-scope
# token may reach; item-level endpoints are further restricted to music items.
_MUSIC_SCOPE_ENDPOINTS = {
    "track", "track_music", "track_neg_status", "track_save_publishing_notes",
    "track_ai_fill_songs", "track_fill_next_writers",
    "track_song_add", "track_song_delete", "track_song_update",
    "track_song_writer_add", "track_song_writer_delete", "track_song_writer_update",
    "track_song_ai_fill_writers", "track_song_deal_terms", "track_song_bulk_deal_terms",
    "track_suggest_deal_terms",
    "track_pub_groups_generate", "track_pub_groups_contact", "track_pub_groups_suggest_contact",
    "track_pub_groups_outreach", "track_pub_groups_save_outreach", "track_pub_groups_send",
    "track_pub_groups_response", "track_pub_groups_record_reply",
    "track_pub_groups_regenerate", "track_pub_groups_approve_send",
    "track_pub_groups_gen_license", "track_pub_groups_license_download",
    "track_pub_groups_deal_points", "track_pub_groups_point_counter",
    "track_item_deal_points", "track_item_point_counter",
    "track_item_start", "track_item_upload", "track_item_submit_review",
    "track_item_gen_draft", "track_item_save_outreach", "track_item_save_draft",
    "track_item_set_contact", "track_item_ai_suggest_contact", "track_item_ai_fill_vars",
    "track_item_send_clearance", "track_item_record_reply", "track_item_regenerate_reply",
    "track_item_edit_reply", "track_item_approve_send", "track_item_deal_terms",
}


def _resolve_token(token):
    """Return (submission, scope) where scope is 'full' or 'music'; (None, None) if no match."""
    sub = Submission.query.filter_by(token=token).first()
    if sub:
        return sub, "full"
    if token:
        sub = Submission.query.filter_by(music_access_token=token).first()
        if sub:
            return sub, "music"
    return None, None


@app.before_request
def _gate_submitter_scope():
    """Central access gate for the submitter tracker. The music-scope token may only
    reach allowed endpoints, and item endpoints only for music items."""
    ep = request.endpoint
    va = request.view_args or {}
    if not ep or "token" not in va:
        return
    if not (ep == "track" or ep.startswith("track_")):
        return  # only the submitter tracker family is token-gated here
    sub, scope = _resolve_token(va.get("token"))
    if sub is None:
        abort(404)
    g.sub = sub
    g.scope = scope
    if scope == "music":
        if ep not in _MUSIC_SCOPE_ENDPOINTS:
            abort(403)
        if "item_id" in va:
            it = ClearanceItem.query.get(va.get("item_id"))
            if not it or it.submission_id != sub.id or not is_music_item(it.item_key):
                abort(403)


def _sub(token):
    """Resolve the submission for a submitter route. Reuses the scope resolved by the
    gate (which accepts the music token for allowed endpoints); otherwise primary-only."""
    if getattr(g, "sub", None) is not None:
        return g.sub
    return Submission.query.filter_by(token=token).first_or_404()


def _submitter_redirect(token, anchor="", music_only=False):
    """Redirect back to whichever submitter page the POST came from.

    After the music split, Songs & Publishing, the publisher groups, and the
    music clearance items live on the dedicated /track/<token>/music page — so
    actions there must return there, not bounce to the main workspace.
      - delegate (music-scope token): only has the root view → 'track'
      - music_only actions (songs/publishers): primary → 'track_music'
      - otherwise (shared item cards): infer from the referring page so a
        general item returns to the workspace and a music item to /music
    """
    if getattr(g, "scope", "full") == "music":
        ep = "track"
    elif music_only:
        ep = "track_music"
    else:
        ref = (request.referrer or "").split("?")[0].split("#")[0].rstrip("/")
        ep = "track_music" if ref.endswith("/music") else "track"
    return redirect(url_for(ep, token=token) + anchor)


def _render_track(token, view):
    """Render the submitter workspace in one of three views:
      'main'     — primary token, main workspace (general clearances + a compact
                   music tracker card that links to the music page)
      'music'    — primary token, dedicated Music Clearance page (full music world
                   + the delegate panel + a link back to the main workspace)
      'delegate' — music-scope token, music-only view for a delegated music contact
    """
    sub = _sub(token)
    # Published clearance guideline for this project type, if the BA has shared one.
    # Shown on the main workspace only — the music page stays focused.
    project_guidelines = None
    if view == "main":
        gl = ClearanceGuideline.query.filter_by(
            platform_id=sub.platform_id, project_type=sub.project_type,
            status="approved", show_to_submitters=True,
        ).first()
        project_guidelines = gl.public_content if (gl and gl.public_content) else None
    # Split clearance items into the Music Clearance group and everything else. Issuer-only
    # items (e.g. the label's conditional-waiver issuance) are the reviewing platform's action,
    # not the submitter's work — hide them from the submitter workspace.
    music_items   = [ci for ci in sub.clearance_items if is_music_item(ci.item_key) and not ci.is_issuer_action]
    general_items = [ci for ci in sub.clearance_items if not is_music_item(ci.item_key) and not ci.is_issuer_action]
    # Which item types have a firm-approved template — drives templates-first drafting UI.
    try:
        template_keys = {t.doc_type for t in Template.query.filter_by(is_active=True).all()}
    except Exception:
        template_keys = set()
    return render_template("track.html", sub=sub,
                           access_token=token,
                           publishing_notes=_get_publishing_notes(sub),
                           neg_positions=sub.platform.negotiation_positions,
                           actions=_scan_submitter_actions(sub),
                           project_guidelines=project_guidelines,
                           music_items=music_items, general_items=general_items,
                           mfn_ledger=_mfn_ledger(sub),
                           template_keys=template_keys,
                           view=view)


@app.route("/track/<token>")
def track(token):
    # A delegated music contact lands here too — keep them on the full music view.
    view = "delegate" if getattr(g, "scope", "full") == "music" else "main"
    return _render_track(token, view)


@app.route("/track/<token>/music")
def track_music(token):
    view = "delegate" if getattr(g, "scope", "full") == "music" else "music"
    return _render_track(token, view)


@app.route("/track/<token>/music-delegate", methods=["POST"])
def track_music_delegate(token):
    """Primary-token only: create or revoke a delegated music-contact access link."""
    sub = _sub(token)
    action = request.form.get("action", "invite")
    if action == "revoke":
        sub.music_access_token = None
        db.session.commit()
        return jsonify({"ok": True, "revoked": True})
    name  = request.form.get("music_contact_name", "").strip()
    email = request.form.get("music_contact_email", "").strip()
    if not email:
        return jsonify({"error": "Enter the music contact's email."}), 400
    sub.music_contact_name  = name
    sub.music_contact_email = email
    if not sub.music_access_token:
        sub.music_access_token = secrets.token_urlsafe(24)
    db.session.commit()
    link = url_for("track", token=sub.music_access_token, _external=True)
    sent = False
    if os.getenv("RESEND_API_KEY"):
        try:
            import resend as _resend
            _resend.api_key = os.getenv("RESEND_API_KEY")
            _resend.Emails.send({
                "from": f"{sub.submitter_name or 'Cleared.live'} <clear@cleared.live>",
                "to": email,
                "subject": f"Music clearance access — {sub.title}",
                "text": (f"You've been asked to handle music clearance for \"{sub.title}\".\n\n"
                         f"Open your music clearance workspace here:\n{link}\n\n"
                         f"This link gives access to the music clearance section only."),
            })
            sent = True
        except Exception:
            sent = False
    return jsonify({"ok": True, "link": link, "sent": sent,
                    "contact_name": sub.music_contact_name,
                    "contact_email": sub.music_contact_email})


# ---------------------------------------------------------------------------
# Cast & Crew registry + general-release signing
# ---------------------------------------------------------------------------

def _default_release_template():
    """Default general appearance/materials release, with {placeholders}. A producer can
    override this per project. Tax ID is intentionally NOT requested — it's collected only
    if/when the signer is paid, on the W-9 at that time, never stored by the platform."""
    return (
        "GENERAL RELEASE\n\n"
        "Project: {project}\n"
        "Producer: {producer}\n\n"
        "For good and valuable consideration, receipt of which is acknowledged, I, {signer}, "
        "grant to {producer} (\"Producer\") and its successors, licensees, and assigns "
        "(including {platform} as distributor) the irrevocable right to record, use, and "
        "distribute my name, likeness, voice, appearance, and any materials I provide in "
        "connection with the project identified above, in all media now known or later "
        "devised, throughout the universe, in perpetuity.\n\n"
        "I acknowledge that I have no right of approval, no claim to compensation beyond any "
        "separately agreed fee, and no claim arising out of any use of the materials. I "
        "represent that I am free to grant these rights and that doing so does not violate any "
        "agreement or third-party right.\n\n"
        "This release is governed by the laws of the State of {state}."
    )


def _general_release_text(sub, rr):
    """Render the release for signing — the producer's custom template if set, else the
    default — substituting project/signer placeholders. Governing law defaults to California."""
    tmpl   = sub.release_template or _default_release_template()
    signer = rr.signer_name or "[SIGNER NAME]"
    fields = {
        "{signer}":   signer,
        "{producer}": sub.submitter_company or sub.submitter_name or "[PRODUCER]",
        "{project}":  sub.title or "[PROJECT]",
        "{platform}": sub.platform.name if sub.platform else "the distributing platform",
        "{state}":    "California",
    }
    body = tmpl
    for k, v in fields.items():
        body = body.replace(k, v)
    return body.rstrip() + f"\n\nSigner: {signer}\nEmail: {rr.signer_email or '[EMAIL]'}\n"


def _build_release_pdf(release_text, signer, signed_at_str, signature_png):
    """Render the signed general release (text + signature image + execution line) to a PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=inch, bottomMargin=inch,
                            leftMargin=inch, rightMargin=inch, title="Signed General Release")
    styles = getSampleStyleSheet()
    body  = ParagraphStyle("body",  parent=styles["Normal"], fontName="Times-Roman", fontSize=11, leading=16)
    title = ParagraphStyle("title", parent=styles["Title"],  fontName="Times-Bold",  fontSize=15, spaceAfter=12)

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []
    for ln in release_text.split("\n"):
        if not ln.strip():
            story.append(Spacer(1, 8))
        elif ln.strip() == "GENERAL RELEASE":
            story.append(Paragraph("GENERAL RELEASE", title))
        else:
            story.append(Paragraph(esc(ln), body))
    story.append(Spacer(1, 28))
    story.append(Paragraph("Signature:", body))
    try:
        img = Image(io.BytesIO(signature_png))
        maxw = 2.4 * inch
        if img.imageWidth > maxw:
            img.drawHeight = img.imageHeight * (maxw / img.imageWidth)
            img.drawWidth  = maxw
        img.hAlign = "LEFT"
        story.append(img)
    except Exception:
        story.append(Paragraph("[signature on file]", body))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Signed by {esc(signer)}", body))
    story.append(Paragraph(f"Date: {esc(signed_at_str)} UTC", body))
    doc.build(story)
    return buf.getvalue()


def _send_release_email(sub, rr, reminder=False):
    """Email the signer their release link. Returns True if actually sent."""
    if not (os.getenv("RESEND_API_KEY") and rr.signer_email):
        return False
    link = url_for("release_sign", token=rr.token, _external=True)
    producer = sub.submitter_company or sub.submitter_name or "the producer"
    subject = (f"Reminder: please sign your release — {sub.title}" if reminder
               else f"Please sign your release — {sub.title}")
    try:
        import resend as _resend
        _resend.api_key = os.getenv("RESEND_API_KEY")
        _resend.Emails.send({
            "from": f"{sub.submitter_name or 'Cleared.live'} <clear@cleared.live>",
            "to": rr.signer_email,
            "subject": subject,
            "text": (f"{'This is a reminder that ' if reminder else ''}"
                     f"{producer} has asked you to sign a release for \"{sub.title}\".\n\n"
                     f"Review and sign here:\n{link}\n\n"
                     f"It takes about a minute — no account needed."),
        })
        return True
    except Exception:
        return False


def _production_sub_or_404(token):
    sub = _sub(token)
    if sub.project_type not in PRODUCTION_PROJECT_TYPES:
        abort(404)
    return sub


@app.route("/track/<token>/people")
def track_people(token):
    """Cast & Crew tab — the project's people/company registry (production types only)."""
    sub = _production_sub_or_404(token)
    contacts = ProjectContact.query.filter_by(submission_id=sub.id)\
        .order_by(ProjectContact.created_at).all()
    # Group by role in CREW_ROLES order.
    grouped = []
    for key, label in CREW_ROLES:
        members = [c for c in contacts if c.role == key]
        if members:
            grouped.append((label, members))
    return render_template("track_people.html", sub=sub, access_token=token,
                           contacts=contacts, grouped=grouped, crew_roles=CREW_ROLES,
                           release_template_current=sub.release_template or "",
                           release_template_default=_default_release_template())


@app.route("/track/<token>/people/release-template", methods=["POST"])
def people_release_template(token):
    """Producer saves (or resets) their own general-release template for this project."""
    sub = _production_sub_or_404(token)
    text = request.form.get("release_template", "").strip()
    sub.release_template = text or None     # empty resets to the default
    db.session.commit()
    flash("Release template saved." if text else "Reverted to the default release.", "success")
    return redirect(url_for("track_people", token=token))


@app.route("/track/<token>/people/add", methods=["POST"])
def people_add(token):
    sub = _production_sub_or_404(token)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required.", "danger")
        return redirect(url_for("track_people", token=token))
    db.session.add(ProjectContact(
        submission_id = sub.id,
        kind          = request.form.get("kind", "person"),
        name          = name,
        company       = request.form.get("company", "").strip() or None,
        role          = request.form.get("role", "talent"),
        email         = request.form.get("email", "").strip().lower() or None,
        phone         = request.form.get("phone", "").strip() or None,
        website       = request.form.get("website", "").strip() or None,
        credit_requirements = request.form.get("credit_requirements", "").strip() or None,
        notes         = request.form.get("notes", "").strip() or None,
    ))
    db.session.commit()
    flash(f"Added {name}.", "success")
    return redirect(url_for("track_people", token=token))


@app.route("/track/<token>/people/<int:contact_id>/update", methods=["POST"])
def people_update(token, contact_id):
    sub = _production_sub_or_404(token)
    c = ProjectContact.query.filter_by(id=contact_id, submission_id=sub.id).first_or_404()
    c.name    = request.form.get("name", c.name).strip() or c.name
    c.company = request.form.get("company", "").strip() or None
    c.role    = request.form.get("role", c.role)
    c.email   = request.form.get("email", "").strip().lower() or None
    c.phone   = request.form.get("phone", "").strip() or None
    c.website = request.form.get("website", "").strip() or None
    c.credit_requirements = request.form.get("credit_requirements", "").strip() or None
    c.notes   = request.form.get("notes", "").strip() or None
    db.session.commit()
    flash(f"Updated {c.name}.", "success")
    return redirect(url_for("track_people", token=token))


@app.route("/track/<token>/people/<int:contact_id>/delete", methods=["POST"])
def people_delete(token, contact_id):
    sub = _production_sub_or_404(token)
    c = ProjectContact.query.filter_by(id=contact_id, submission_id=sub.id).first_or_404()
    db.session.delete(c)
    db.session.commit()
    flash("Contact removed.", "success")
    return redirect(url_for("track_people", token=token))


@app.route("/track/<token>/people/<int:contact_id>/send-release", methods=["POST"])
def people_send_release(token, contact_id):
    """Create (or reuse) a release request for this person and deliver the signing link —
    copy link always returned; emailed too when an address is present."""
    sub = _production_sub_or_404(token)
    c = ProjectContact.query.filter_by(id=contact_id, submission_id=sub.id).first_or_404()
    rr = ReleaseRequest.query.filter_by(contact_id=c.id)\
        .filter(ReleaseRequest.status != "signed").first()
    if not rr:
        rr = ReleaseRequest(submission_id=sub.id, contact_id=c.id,
                            signer_name=c.name, signer_email=c.email)
        db.session.add(rr)
        db.session.flush()
    rr.signer_name  = c.name
    rr.signer_email = c.email
    sent = _send_release_email(sub, rr)
    rr.status   = "sent"
    rr.sent_at  = rr.sent_at or datetime.utcnow()
    rr.log_add("sent", f"Emailed to {c.email}" if sent else "Link generated (copy/paste)")
    db.session.commit()
    link = url_for("release_sign", token=rr.token, _external=True)
    if sent:
        flash(f"Release sent to {c.email}. Shareable link: {link}", "success")
    else:
        flash(f"Release link ready — copy and send it to {c.name}: {link}", "info")
    return redirect(url_for("track_people", token=token))


@app.route("/track/<token>/release/<int:release_id>/remind", methods=["POST"])
def release_remind(token, release_id):
    sub = _production_sub_or_404(token)
    rr = ReleaseRequest.query.filter_by(id=release_id, submission_id=sub.id).first_or_404()
    if rr.status == "signed":
        flash("Already signed.", "info")
        return redirect(url_for("track_people", token=token))
    sent = _send_release_email(sub, rr, reminder=True)
    rr.reminders_sent   = (rr.reminders_sent or 0) + 1
    rr.last_reminder_at = datetime.utcnow()
    rr.log_add("reminder", f"Manual reminder to {rr.signer_email}" if sent else "Manual reminder (no email configured)")
    db.session.commit()
    flash(f"Reminder sent to {rr.signer_email or rr.signer_name}." if sent
          else "Logged a reminder (email not configured).", "success")
    return redirect(url_for("track_people", token=token))


# ── Public general-release signing (no auth — token-scoped) ────────────────
@app.route("/release/<token>")
def release_sign(token):
    rr = ReleaseRequest.query.filter_by(token=token).first_or_404()
    sub = rr.submission
    if rr.status not in ("signed", "declined"):
        if not rr.viewed_at:
            rr.viewed_at = datetime.utcnow()
            rr.log_add("viewed", "Signer opened the release")
            if rr.status == "sent":
                rr.status = "viewed"
            db.session.commit()
    return render_template("release_sign.html", rr=rr, sub=sub,
                           release_text=_general_release_text(sub, rr))


@app.route("/release/<token>/sign", methods=["POST"])
def release_do_sign(token):
    rr = ReleaseRequest.query.filter_by(token=token).first_or_404()
    sub = rr.submission
    if rr.status == "signed":
        return render_template("release_signed.html", rr=rr, sub=sub)
    printed = request.form.get("printed_name", "").strip()
    sig     = request.form.get("signature_data", "")
    if not printed or not sig.startswith("data:image"):
        flash("Please print your name and draw your signature.", "warning")
        return redirect(url_for("release_sign", token=token))
    try:
        png = base64.b64decode(sig.split(",", 1)[1])
    except Exception:
        flash("Signature could not be read. Please try again.", "danger")
        return redirect(url_for("release_sign", token=token))
    rr.signer_name = printed or rr.signer_name
    now = datetime.utcnow()
    release_text = _general_release_text(sub, rr)
    signed_str   = now.strftime("%B %-d, %Y %H:%M")
    safe_name    = "".join(ch for ch in (printed or "release") if ch.isalnum() or ch in " -_").strip().replace(" ", "_")
    try:
        pdf_bytes = _build_release_pdf(release_text, printed, signed_str, png)
        file_data, mimetype, filename = pdf_bytes, "application/pdf", f"Signed_Release_{safe_name}.pdf"
    except Exception as e:
        app.logger.error(f"Release PDF build failed, storing signature image: {e}")
        file_data, mimetype, filename = png, "image/png", f"Signed_Release_{safe_name}.png"
    db.session.add(SubmissionDocument(
        submission_id = sub.id,
        title         = f"Signed General Release — {rr.signer_name}",
        doc_type      = "signed_release",
        filename      = filename,
        file_data     = file_data,
        mimetype      = mimetype,
        notes         = release_text + f"\n\nSigned by {printed} at {now.isoformat()} UTC",
        uploaded_by   = printed,
    ))
    rr.status    = "signed"
    rr.signed_at = now
    rr.log_add("signed", f"Signed by {printed}")
    db.session.commit()
    return render_template("release_signed.html", rr=rr, sub=sub)


# ---------------------------------------------------------------------------
# Festival — multi-artist lineup routing
# ---------------------------------------------------------------------------

def _match_label_platform(label_name):
    """Find a connected label Platform (label_waiver mode) whose name matches the
    promoter-entered label text. Case-insensitive substring match, either direction."""
    if not label_name:
        return None
    needle = label_name.strip().lower()
    labels = Platform.query.filter_by(platform_mode="label_waiver", is_active=True).all()
    for p in labels:
        name = (p.name or "").lower()
        logo = (p.logo_text or "").lower()
        if needle in name or name in needle or (logo and (needle in logo or logo in needle)):
            return p
    return None


def _spawn_artist_submission(festival, artist, platform):
    """Create a per-artist clearance thread (child Submission) for the festival.

    The PROMOTER owns and is responsible for completing every artist's clearance — routing
    never transfers that work. A thread on a label platform uses the label-waiver package so
    the label can REVIEW the promoter's completed clearances and ISSUE its conditional waiver;
    a direct thread uses the standard live_music package the promoter clears itself. Either
    way the submitter (owner) is the promoter; the artist's management/label is only an
    optional assist contact."""
    template_key = "live_music_label" if platform.platform_mode == "label_waiver" else "live_music"
    child = Submission(
        platform_id        = platform.id,
        project_type       = "live_music",
        title              = f"{festival.event_name or festival.title} — {artist.artist_name}",
        artist_name        = artist.artist_name,
        event_name         = festival.event_name or festival.title,
        venue              = festival.venue,
        event_date         = festival.event_date,
        label              = artist.label_name,
        territory          = festival.territory,
        intended_use       = festival.intended_use,
        submitter_name     = festival.submitter_name,
        submitter_company  = festival.submitter_company,
        submitter_email    = festival.submitter_email,   # the promoter owns and is responsible for the thread
        submitter_phone    = festival.submitter_phone,
        pricing_tier       = festival.pricing_tier,
        price_cents        = 0,
        status             = "submitted",
        ba_notes           = (
            f"Festival lineup clearance — part of \"{festival.event_name or festival.title}\". "
            f"Promoter ({festival.submitter_company or festival.submitter_name}) is responsible for "
            f"completing this artist's clearances; "
            + (f"{platform.name} reviews them and issues its conditional waiver."
               if platform.platform_mode == "label_waiver"
               else "cleared directly.")
            + (f" Assist contact: {artist.contact_email}." if artist.contact_email else "")
        ),
    )
    db.session.add(child)
    db.session.flush()
    for item_def in CLEARANCE_TEMPLATES.get(template_key, CLEARANCE_TEMPLATES["live_music"]):
        db.session.add(ClearanceItem(
            submission_id=child.id, item_key=item_def["key"],
            item_label=item_def["label"], priority=item_def["priority"], status="pending",
        ))
    return child


@app.route("/track/<token>/festival")
def track_festival(token):
    """Festival lineup workspace — the promoter manages and completes clearance for every
    artist: opening a thread on the artist's label (so the label can review and issue its
    conditional waiver), clearing an independent act directly, or inviting a label/manager
    to assist. The promoter remains responsible throughout."""
    sub = _sub(token)
    artists = FestivalArtist.query.filter_by(submission_id=sub.id)\
        .order_by(FestivalArtist.created_at).all()
    # Surface the label-platform match for any not-yet-routed artist so the promoter
    # sees where each artist will go before they route.
    suggestions = {}
    for a in artists:
        if a.status == "pending" and a.is_signed:
            m = _match_label_platform(a.label_name)
            suggestions[a.id] = m
    return render_template("track_festival.html", sub=sub, access_token=token,
                           artists=artists, suggestions=suggestions)


@app.route("/track/<token>/festival/artist/add", methods=["POST"])
def festival_artist_add(token):
    sub = _sub(token)
    name = request.form.get("artist_name", "").strip()
    if not name:
        flash("Artist name is required.", "danger")
        return redirect(url_for("track_festival", token=token))
    db.session.add(FestivalArtist(
        submission_id = sub.id,
        artist_name   = name,
        label_name    = request.form.get("label_name", "").strip() or None,
        is_signed     = request.form.get("is_signed") == "1",
        contact_name  = request.form.get("contact_name", "").strip() or None,
        contact_email = request.form.get("contact_email", "").strip().lower() or None,
        notes         = request.form.get("notes", "").strip() or None,
    ))
    db.session.commit()
    flash(f"Added {name} to the lineup.", "success")
    return redirect(url_for("track_festival", token=token))


@app.route("/track/<token>/festival/artist/<int:artist_id>/delete", methods=["POST"])
def festival_artist_delete(token, artist_id):
    sub = _sub(token)
    a = FestivalArtist.query.filter_by(id=artist_id, submission_id=sub.id).first_or_404()
    db.session.delete(a)
    db.session.commit()
    flash("Artist removed from the lineup.", "success")
    return redirect(url_for("track_festival", token=token))


@app.route("/track/<token>/festival/artist/<int:artist_id>/route", methods=["POST"])
def festival_artist_route(token, artist_id):
    """Open a promoter-owned clearance thread for an artist. The promoter completes the
    clearances either way:
      mode=label  → thread sits on the matched label's platform so the label can review the
                    completed clearances and issue its conditional waiver
      mode=direct → promoter clears the artist directly under the festival's own platform"""
    sub = _sub(token)
    a   = FestivalArtist.query.filter_by(id=artist_id, submission_id=sub.id).first_or_404()
    if a.child_submission_id:
        flash(f"{a.artist_name} is already routed.", "info")
        return redirect(url_for("track_festival", token=token))

    mode = request.form.get("mode", "direct")
    if mode == "label":
        label = _match_label_platform(a.label_name)
        if not label:
            flash(f"No connected label matches \"{a.label_name or '—'}\". "
                  f"Route directly or hand off instead.", "warning")
            return redirect(url_for("track_festival", token=token))
        child = _spawn_artist_submission(sub, a, label)
        a.routed_platform_id  = label.id
        a.child_submission_id = child.id
        a.status = "routed_label"
        db.session.commit()
        flash(f"Clearance thread opened for {a.artist_name}. You complete the clearances; "
              f"{label.name} reviews them and issues its conditional waiver. You remain responsible.",
              "success")
    else:
        child = _spawn_artist_submission(sub, a, sub.platform)
        a.child_submission_id = child.id
        a.status = "routed_direct"
        db.session.commit()
        flash(f"Direct clearance thread opened for {a.artist_name} — you clear this artist yourself.", "success")
    return redirect(url_for("track_festival", token=token))


@app.route("/track/<token>/festival/artist/<int:artist_id>/handoff", methods=["POST"])
def festival_artist_handoff(token, artist_id):
    """Invite the artist's management or label to ASSIST with this artist's clearance.
    Creates the promoter-owned thread (if not already) and emails the contact a link to help.
    This does NOT transfer responsibility — the promoter remains the owner and is responsible
    for completing the clearances."""
    sub = _sub(token)
    a   = FestivalArtist.query.filter_by(id=artist_id, submission_id=sub.id).first_or_404()
    to_email = (request.form.get("handoff_email", "").strip().lower()
                or a.contact_email or "")
    if not to_email:
        flash("Enter an email to invite to assist.", "danger")
        return redirect(url_for("track_festival", token=token))

    # Ensure a clearance thread exists — handoff routes to the label if matched, else direct.
    if not a.child_submission_id:
        label = _match_label_platform(a.label_name) if a.is_signed else None
        child = _spawn_artist_submission(sub, a, label or sub.platform)
        a.child_submission_id = child.id
        a.routed_platform_id  = label.id if label else None
        db.session.flush()
    child = Submission.query.get(a.child_submission_id)
    a.status        = "handed_off"
    a.handed_off_to = to_email
    db.session.commit()

    link = url_for("track", token=child.token, _external=True)
    sent = False
    if os.getenv("RESEND_API_KEY"):
        try:
            import resend as _resend
            _resend.api_key = os.getenv("RESEND_API_KEY")
            _resend.Emails.send({
                "from": f"{sub.submitter_name or 'Cleared.live'} <clear@cleared.live>",
                "to": to_email,
                "subject": f"Clearance assist request — {a.artist_name} at {sub.event_name or sub.title}",
                "text": (f"{sub.submitter_company or sub.submitter_name or 'The promoter'} has invited you to "
                         f"help with clearance for {a.artist_name} at \"{sub.event_name or sub.title}\".\n\n"
                         f"Open the clearance workspace here:\n{link}\n\n"
                         f"You can help complete the clearance items for this artist. "
                         f"{sub.submitter_company or sub.submitter_name or 'The promoter'} remains responsible "
                         f"for ensuring this artist is fully cleared."),
            })
            sent = True
        except Exception:
            sent = False
    if sent:
        flash(f"Invited {to_email} to assist with {a.artist_name}'s clearance. "
              f"You remain responsible for completing it.", "success")
    else:
        flash(f"Assist link ready. Share it with {to_email}: {link}", "info")
    return redirect(url_for("track_festival", token=token))


SIGNED_DOC_TYPES = ("signed_release", "executed", "onsite_signature", "signed_document")


@app.route("/track/<token>/signed")
def track_signed(token):
    """Signed Documents tab — every executed/signed artifact, clickable to open."""
    sub  = _sub(token)
    docs = SubmissionDocument.query.filter(
        SubmissionDocument.submission_id == sub.id,
        SubmissionDocument.doc_type.in_(SIGNED_DOC_TYPES),
    ).order_by(SubmissionDocument.created_at.desc()).all()
    return render_template("track_signed.html", sub=sub, access_token=token, docs=docs)


@app.route("/track/<token>/agreements")
def track_agreements(token):
    """Submitter-facing Agreements tab — every agreement with its lifecycle stage
    (draft → negotiating → out for signature → executed) plus the full paper trail."""
    sub = _sub(token)
    items = sorted(
        sub.submitter_items,   # hide issuer-only items (e.g. the label's waiver issuance)
        key=lambda it: (it.agreement_stage_order, it.agreement_last_activity or datetime.min),
        reverse=True,
    )
    return render_template(
        "track_agreements.html",
        sub=sub,
        access_token=token,
        items=items,
        paper_trail=_project_paper_trail(sub),
        view="agreements",
    )


@app.route("/track/<token>/doc/<int:doc_id>/download")
def track_download_doc(token, doc_id):
    """Token-scoped document download for the submitter workspace."""
    sub = _sub(token)
    doc = SubmissionDocument.query.get_or_404(doc_id)
    if doc.submission_id != sub.id:
        abort(403)
    inline = request.args.get("inline") == "1"
    return send_file(
        io.BytesIO(doc.file_data),
        download_name=doc.filename,
        as_attachment=not inline,
        mimetype=doc.mimetype or "application/octet-stream",
    )


@app.route("/track/<token>/neg-status")
def track_neg_status(token):
    """Lightweight JSON snapshot of each item's negotiation state, polled by the
    submitter workspace so it can refresh only when the AI agent finishes —
    instead of blindly reloading and clobbering in-progress edits."""
    sub = _sub(token)
    return jsonify({str(it.id): (it.neg_state or "") for it in sub.clearance_items})


@app.route("/track/<token>/save-publishing-notes", methods=["POST"])
def track_save_publishing_notes(token):
    sub = _sub(token)
    pub = request.form.get("publishing_notes", "").strip()
    _set_publishing_notes(sub, _get_ba_notes_only(sub), pub)
    db.session.commit()
    flash("Publishing reference saved.", "success")
    return _submitter_redirect(token, "#songs-section", music_only=True)


# ---------------------------------------------------------------------------
# Submitter — token-authenticated action routes (no login required)
# ---------------------------------------------------------------------------

@app.route("/track/<token>/item/<int:item_id>/start", methods=["POST"])
def track_item_start(token, item_id):
    sub  = _sub(token)
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
    sub  = _sub(token)
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


@app.route("/track/<token>/item/<int:item_id>/agreement.docx")
def track_item_agreement_docx(token, item_id):
    """Download the item's AI-drafted agreement as a Word .docx (folded in from PLB)."""
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    draft_text = item.ai_draft or f"[Draft pending for {item.item_label}]"
    doc_bytes  = build_docx(_DocxProxy(title=item.item_label, content=draft_text))
    safe = re.sub(r"[^A-Za-z0-9]+", "-", item.item_label).strip("-").lower() or "agreement"
    return send_file(
        io.BytesIO(doc_bytes),
        as_attachment=True,
        download_name=f"{safe}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.route("/track/<token>/item/<int:item_id>/sign-onsite", methods=["GET", "POST"])
def track_item_sign_onsite(token, item_id):
    """On-site signing (folded in from PLB): capture a canvas signature + printed name,
    store it as a signed document, and send the item for review — no DocuSign needed."""
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    if request.method == "POST":
        printed_name = request.form.get("printed_name", "").strip()
        sig_data     = request.form.get("signature_data", "")
        if not printed_name or not sig_data.startswith("data:image"):
            flash("Please print your name and draw your signature.", "warning")
            return redirect(url_for("track_item_sign_onsite", token=token, item_id=item.id))
        try:
            png = base64.b64decode(sig_data.split(",", 1)[1])
        except Exception:
            flash("Signature could not be read. Please try again.", "danger")
            return redirect(url_for("track_item_sign_onsite", token=token, item_id=item.id))
        db.session.add(SubmissionDocument(
            submission_id     = sub.id,
            clearance_item_id = item.id,
            title             = f"On-site signature — {item.item_label}",
            doc_type          = "onsite_signature",
            filename          = "signature.png",
            file_data         = png,
            mimetype          = "image/png",
            notes             = f"Signed on-site by {printed_name}",
            uploaded_by       = printed_name,
        ))
        item.docusign_status = "signed_onsite"
        item.status          = "under_review"
        db.session.commit()
        flash(f"Signed on-site by {printed_name}. Sent for review.", "success")
        return redirect(url_for("track", token=token))
    return render_template("sign_onsite.html", sub=sub, item=item)


# ── Deal-Term negotiation board (folded in from PLB) ────────────────────────
def _board_item(token, item_id):
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    return sub, item


@app.route("/track/<token>/item/<int:item_id>/board/add", methods=["POST"])
def track_board_add(token, item_id):
    sub, item = _board_item(token, item_id)
    label = request.form.get("label", "").strip()
    if not label:
        flash("Enter a term name (e.g. Fee, Term, Territory).", "warning")
        return _submitter_redirect(token, f"#item-card-{item_id}")
    nxt = (max([t.sort_order for t in item.deal_board], default=0) + 1) if item.deal_board else 1
    db.session.add(DealTerm(
        clearance_item_id=item.id, label=label,
        our_position=request.form.get("our_position", "").strip(),
        sort_order=nxt,
    ))
    db.session.commit()
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/board/<int:term_id>/update", methods=["POST"])
def track_board_update(token, item_id, term_id):
    sub, item = _board_item(token, item_id)
    term = DealTerm.query.get_or_404(term_id)
    if term.clearance_item_id != item.id:
        abort(403)
    term.our_position   = request.form.get("our_position", term.our_position)
    term.their_position = request.form.get("their_position", term.their_position)
    term.agreed         = request.form.get("agreed", term.agreed)
    term.status         = request.form.get("status", term.status)
    db.session.commit()
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/board/<int:term_id>/delete", methods=["POST"])
def track_board_delete(token, item_id, term_id):
    sub, item = _board_item(token, item_id)
    term = DealTerm.query.get_or_404(term_id)
    if term.clearance_item_id != item.id:
        abort(403)
    db.session.delete(term)
    db.session.commit()
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/board/<int:term_id>/suggest-counter", methods=["POST"])
def track_board_suggest_counter(token, item_id, term_id):
    sub, item = _board_item(token, item_id)
    term = DealTerm.query.get_or_404(term_id)
    if term.clearance_item_id != item.id:
        abort(403)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"ok": False, "error": "AI not configured."}), 503
    agreed_context = "\n".join(
        f"- {t.label}: {t.agreed}" for t in item.deal_board if t.agreed and t.id != term_id
    ) or "None agreed yet."
    system = (
        "You are an entertainment attorney advising the producer/submitter on deal negotiations. "
        "Be direct and specific — name figures, timeframes, or exact language. No disclaimers."
    )
    user = (
        f"Agreement: {item.item_label}\nProject: {sub.title} ({sub.project_type_label})\n\n"
        f"Term being negotiated: {term.label}\n"
        f"Our current position: {term.our_position or '(not set)'}\n"
        f"Their position: {term.their_position or '(not set)'}\n\n"
        f"Other terms already agreed:\n{agreed_context}\n\n"
        f"Suggest a specific counter-position for \"{term.label}\" that advances our client's interests, "
        f"is commercially reasonable and likely to close, and reflects market norms. Respond with ONLY:\n"
        f"COUNTER: [one clear sentence or figure]\nRATIONALE: [1-2 sentences]"
    )
    try:
        text = call_claude(system, user, max_tokens=400)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    counter = rationale = ""
    for line in text.splitlines():
        if line.startswith("COUNTER:"):
            counter = line[len("COUNTER:"):].strip()
        elif line.startswith("RATIONALE:"):
            rationale = line[len("RATIONALE:"):].strip()
    return jsonify({"ok": True, "counter": counter or text.strip(), "rationale": rationale})


@app.route("/track/<token>/item/<int:item_id>/submit-review", methods=["POST"])
def track_item_submit_review(token, item_id):
    sub  = _sub(token)
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
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    ai_only = bool(request.form.get("ai_only"))
    item.ai_draft = None
    db.session.commit()
    draft = generate_draft(sub, item, ai_only=ai_only)
    if draft:
        item.ai_draft = draft
        db.session.commit()
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/save-outreach", methods=["POST"])
def track_item_save_outreach(token, item_id):
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.ai_outreach_body = request.form.get("outreach_text", item.ai_outreach_body)
    db.session.commit()
    flash("Outreach email saved.", "success")
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/save-draft", methods=["POST"])
def track_item_save_draft(token, item_id):
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.ai_draft = request.form.get("draft_text", item.ai_draft)
    db.session.commit()
    flash("Draft saved.", "success")
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/set-contact", methods=["POST"])
def track_item_set_contact(token, item_id):
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.party_company = request.form.get("party_company", "").strip() or None
    item.party_name    = request.form.get("party_name", "").strip() or None
    item.party_email   = request.form.get("party_email", "").strip().lower() or None
    db.session.commit()
    flash("Contact saved.", "success")
    return _submitter_redirect(token, f"#item-card-{item_id}")


def _ai_contact_lookup(sub, item, company):
    """Research the correct rights-holder / licensing contact for an item.
    Returns a parsed dict (contact_name, contact_email, confidence, note,
    co_admins) or None. Shared by the manual route and the auto-stage agent."""
    company = (company or "").strip()
    if not company or not os.getenv("ANTHROPIC_API_KEY"):
        return None
    system = (
        "You are a music and entertainment industry clearance expert specializing in sync licensing. "
        "Your job is to identify the correct PUBLISHING ADMINISTRATOR or rights holder that must be "
        "contacted to obtain sync/master/clearance licenses. "
        "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
    )
    # Master vs publishing vs general — each names a different rights-holder ENTITY.
    is_master = "master" in (item.item_key or "").lower() or "master" in (item.item_label or "").lower()
    is_music  = any(k in (item.item_label or "").lower()
                    for k in ("sync", "music", "master", "publishing", "song", "track", "record"))
    if is_master:
        user = (
            f"Identify the MASTER RECORDING rights-holder licensing contact for:\n"
            f"Artist: {company}\n"
            f"Item type: {item.item_label}\n"
            f"Project: {sub.project_type_label} — {sub.title} on {sub.platform.name}\n\n"
            f"The master recording is controlled by the artist's RECORD LABEL — identify the label and its "
            f"film/TV (master-use) licensing contact. The licensor ENTITY is the LABEL, never the artist's name.\n\n"
            f"Return JSON:\n"
            f"  contact_company: string — the record label / master rights-holder ENTITY (e.g. "
            f"'Republic Records (Universal Music Group)') — NEVER the artist's personal name\n"
            f"  contact_name: string — the master / film-TV licensing department\n"
            f"  contact_email: string — the label's licensing email\n"
            f"  confidence: 'high' | 'medium' | 'low'\n"
            f"  note: string — note that a separate publishing/sync license is also required, plus any MFN considerations\n"
            f"  co_admins: array of {{company, contact_email}} — empty [] unless multiple labels control the master"
        )
    elif is_music:
        user = (
            f"Identify the publishing ADMINISTRATOR(S) that handle sync licensing for:\n"
            f"Artist / Rights Holder: {company}\n"
            f"Item type: {item.item_label}\n"
            f"Project: {sub.project_type_label} — {sub.title} on {sub.platform.name}\n\n"
            f"CRITICAL: Return the major publishing ADMINISTRATOR (Sony Music Publishing, UMPG, "
            f"Warner Chappell, Kobalt, BMG, etc.) — NOT a personal publishing entity, NOT the artist's name.\n"
            f"If the songs are CO-ADMINISTERED by multiple publishers, set co_admins to a list of all.\n\n"
            f"Return JSON:\n"
            f"  contact_company: string — the publishing administrator ENTITY to name as licensor "
            f"(e.g. 'Universal Music Publishing Group') — NEVER the artist's personal name\n"
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
            f"  contact_company: string — the rights-holder ENTITY to name as licensor (the company above, refined)\n"
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
        return None
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(clean)
        if "co_admins" not in data:
            data["co_admins"] = []
        # The licensor entity, never the artist. Fall back to the resolved rights
        # holder (label for master/label items) when the model omits it.
        if not (data.get("contact_company") or "").strip():
            data["contact_company"] = _item_rights_holder(sub, item)
        return data
    except Exception:
        return None


@app.route("/track/<token>/item/<int:item_id>/ai-suggest-contact", methods=["POST"])
def track_item_ai_suggest_contact(token, item_id):
    from flask import jsonify
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    company = request.form.get("company", "").strip()
    if not company:
        return jsonify({"error": "Enter a company name first."}), 400
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "AI unavailable."}), 503

    data = _ai_contact_lookup(sub, item, company)
    if data is None:
        return jsonify({"error": "AI did not respond or could not be parsed."}), 500
    # Auto-save primary contact to item if high confidence
    if data.get("confidence") == "high":
        item.party_company = company
        item.party_name    = data.get("contact_name") or item.party_name
        item.party_email   = (data.get("contact_email") or "").lower() or item.party_email
        db.session.commit()
    return jsonify(data)


@app.route("/track/<token>/item/<int:item_id>/ai-fill-vars", methods=["POST"])
def track_item_ai_fill_vars(token, item_id):
    from flask import jsonify
    import json as _json
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "AI unavailable"}), 503

    var_names = request.form.getlist("vars")
    if not var_names:
        return jsonify({}), 200

    dt = item.deal_terms
    rh = _item_rights_holder(sub, item)
    afee = _agreed_fee(_item_deal_points(item))
    cue_days = (dt or {}).get("cue_sheet_days") or 30
    amount_str = (f"${afee:,.0f} (agreed — use exactly)" if afee is not None
                  else (f"${dt.get('fee')} (proposed, not yet agreed)" if dt.get("fee")
                        else "not yet agreed"))
    system = (
        "You are a legal document specialist. Fill in contract variable fields with accurate, "
        "specific values based on the project context provided. "
        "Respond ONLY with valid JSON — no markdown, no explanation outside the JSON."
    )
    user = (
        f"Fill in the following contract variables for a {item.item_label} agreement.\n\n"
        f"Project context:\n{_sub_context(sub)}\n\n"
        f"Rights Holder / Licensor: {rh or 'Unknown'}\n"
        f"Rights Holder Email: {item.party_email or 'Unknown'}\n"
        f"Deal Terms: agreed_fee={amount_str}, fee_type={dt.get('fee_type') or 'TBD'}, "
        f"territory={dt.get('territory') or 'Worldwide'}, term={dt.get('term') or 'Perpetuity'}, "
        f"media_rights={', '.join(dt.get('media_rights') or ['Streaming'])}, cue_sheet_days={cue_days}\n\n"
        f"Variables to fill (return ONLY these keys in JSON):\n"
        + "\n".join(f"  - {v}" for v in var_names)
        + "\n\nFor each variable, provide a specific, accurate value from the project data above.\n"
        f"For RIGHTS HOLDER / LICENSOR: use '{rh or 'the rights holder'}'.\n"
        f"For AMOUNT / FEE: use the agreed fee ({amount_str}). If it is not yet agreed, return "
        f"'TBD — pending negotiation' and do NOT invent a market rate (the fee is set after negotiation).\n"
        f"For any NUMBER of days / NOTICE PERIOD / CURE PERIOD: use 5; for cue-sheet days use {cue_days}.\n"
        f"For STATE: the state where the rights holder/company is based. "
        f"For ENTITY TYPE AND STATE: e.g. 'a Delaware limited liability company'. "
        f"For PAYMENT SCHEDULE: standard terms like 'full upon execution'. "
        f"For DATE / EFFECTIVE DATE: use the event date.\n"
        f"Never leave a value as a bracket placeholder unless it is the fee and the fee is not yet agreed."
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
    sub  = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    if not item.ai_draft:
        flash("Generate the draft agreement first.", "danger")
        return _submitter_redirect(token, f"#item-card-{item_id}")
    if not item.party_email:
        flash("Add the rights holder email address first.", "danger")
        return _submitter_redirect(token, f"#item-card-{item_id}")
    # Deal terms default to the platform BA's primary position when unset, so
    # the submitter never has to re-enter what the platform already mandates.
    dt = _ensure_deal_terms(sub, item)
    db.session.commit()
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
    return _submitter_redirect(token, f"#item-card-{item_id}")


def _neg_redirect(token, item_id):
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/record-reply", methods=["POST"])
def track_item_record_reply(token, item_id):
    """Submitter brings the rights holder's reply into the platform; AI then analyzes it."""
    sub  = _sub(token)
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
    sub  = _sub(token)
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
    sub  = _sub(token)
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
    sub  = _sub(token)
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
    sub = _sub(token)
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
    sub  = _sub(token)
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
    return _submitter_redirect(token, f"#item-card-{item_id}")


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
    sub = _sub(token)
    _ai_fill_songs(sub.id)   # Phase 1: setlist titles only, synchronous
    # Phase 2 handled client-side via /fill-next-writers batched JSON calls
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/fill-next-writers", methods=["POST"])
def track_fill_next_writers(token):
    """Fill writers for a batch of songs. Called repeatedly by JS until done."""
    from flask import jsonify
    sub  = _sub(token)
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
    sub = _sub(token)
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
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/delete/<int:idx>", methods=["POST"])
def track_song_delete(token, idx):
    sub = _sub(token)
    songs = sub.songs
    if 0 <= idx < len(songs):
        songs.pop(idx)
        sub.songs_save(songs)
        db.session.commit()
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/update/<int:idx>", methods=["POST"])
def track_song_update(token, idx):
    sub = _sub(token)
    songs = sub.songs
    if 0 <= idx < len(songs):
        songs[idx]["title"]         = request.form.get("title", songs[idx].get("title", ""))
        songs[idx]["is_cover"]      = request.form.get("is_cover") == "1"
        songs[idx]["original_artist"] = request.form.get("original_artist", "") or None
        songs[idx]["status"]        = request.form.get("status", songs[idx].get("status", "pending"))
        sub.songs_save(songs)
        db.session.commit()
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/<int:idx>/writer/add", methods=["POST"])
def track_song_writer_add(token, idx):
    sub = _sub(token)
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
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/<int:idx>/writer/<int:widx>/delete", methods=["POST"])
def track_song_writer_delete(token, idx, widx):
    sub = _sub(token)
    songs = sub.songs
    if 0 <= idx < len(songs):
        writers = songs[idx].get("writers", [])
        if 0 <= widx < len(writers):
            writers.pop(widx)
            songs[idx]["writers"] = writers
            sub.songs_save(songs)
            db.session.commit()
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/<int:idx>/writer/<int:widx>/update", methods=["POST"])
def track_song_writer_update(token, idx, widx):
    sub = _sub(token)
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
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/<int:idx>/ai-fill-writers", methods=["POST"])
def track_song_ai_fill_writers(token, idx):
    sub = _sub(token)
    _ai_fill_song_writers(sub.id, idx)
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/pub-groups/generate", methods=["POST"])
def track_pub_groups_generate(token):
    sub = _sub(token)
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
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/contact", methods=["POST"])
def track_pub_groups_contact(token):
    from flask import jsonify
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return jsonify({"error": "Publisher group not found"}), 404
    g = groups[publisher]
    g["contact_name"]  = request.form.get("contact_name", "").strip()
    g["contact_email"] = request.form.get("contact_email", "").strip()
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return jsonify({
        "ok": True,
        "contact_name": g["contact_name"],
        "contact_email": g["contact_email"],
        # Can send once a draft exists, a contact email is set, and it's not already sent.
        "can_send": bool(g.get("ai_outreach") and g["contact_email"] and not g.get("outreach_sent_at")),
    })


@app.route("/track/<token>/pub-groups/suggest-contact", methods=["POST"])
def track_pub_groups_suggest_contact(token):
    """AI-research the sync licensing contact for a publisher clearance group."""
    from flask import jsonify
    from types import SimpleNamespace
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    if not publisher:
        return jsonify({"error": "Publisher name missing."}), 400
    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "AI unavailable."}), 503
    # Stub item so the lookup runs in music-publishing mode (it only reads item_label).
    item_stub = SimpleNamespace(item_label="Music Publishing / Sync Licensing")
    data = _ai_contact_lookup(sub, item_stub, publisher)
    if data is None:
        return jsonify({"error": "AI did not respond or could not be parsed."}), 500
    return jsonify(data)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _total_compositions(sub):
    """Number of distinct compositions in the project (for per-song math)."""
    try:
        return len(sub.songs or [])
    except Exception:
        return 0


def _group_share(group):
    """A publisher's aggregate catalog share in 'song-equivalents' — the sum of its
    songs' split %. Controlling 50% of 25 songs = 12.5 song-shares. This is the unit
    a blanket fee is pro-rated against, so co-publishers of the same song don't each
    get billed the full per-song rate."""
    total = 0.0
    for s in group.get("songs", []):
        sp = _num(s.get("split_pct"))
        if sp is not None:
            total += sp / 100.0
    return round(total, 4)


def _per_song_rate(terms, total_comps):
    """Canonical per-song (per-composition) rate from a deal-terms dict. A per-song
    fee_type means the fee already IS the rate; a flat fee is treated as an all-in
    publishing total and converted to a per-song rate by the number of compositions."""
    fee = _num((terms or {}).get("fee"))
    if fee is None:
        return None
    ft = ((terms or {}).get("fee_type") or "").lower()
    if "item" in ft or "song" in ft:
        return fee
    return (fee / total_comps) if total_comps else fee


def _group_offer_fee(sub, group):
    """(blanket_fee, per_song_rate, share) for a publisher group. The blanket fee for
    THAT publisher = per-song rate × the share of the catalog it controls — so a
    2-song publisher and a 25-song publisher get proportionate offers, not the same."""
    terms = group.get("deal_terms") or sub.deal_terms or {}
    rate = _per_song_rate(terms, _total_compositions(sub))
    share = _group_share(group)
    if rate is None or share <= 0:
        return None, rate, share
    return round(rate * share), rate, share


def _format_group_offer(sub, group, primary):
    """Return (offer_lines, fee_instruction, mfn_instruction) describing the
    submitter's proposed sync terms for a publisher group. The fee is a per-song
    rate pro-rated to THIS publisher's catalog share (not the whole-project figure)."""
    dt = (group.get("deal_terms") or sub.deal_terms or {})

    def _v(key, default):
        val = dt.get(key)
        return val if val not in (None, "", []) else default

    territory = _v("territory", primary.get("territory", "Worldwide"))
    term      = _v("term", primary.get("term", "Perpetuity"))
    uses      = dt.get("media_rights") or primary.get("uses", ["Streaming"])
    fee_type  = (dt.get("fee_type") or "").strip()
    mfn       = bool(dt.get("mfn"))
    notes     = (dt.get("notes") or "").strip()

    group_fee, rate, share = _group_offer_fee(sub, group)
    n_songs = len(group.get("songs", []))
    if str(dt.get("fee")) in ("0", "0.0") or fee_type.lower() == "gratis":
        fee_line = "Gratis — no license fee (promotional / festival use)"
        fee_instruction = "State clearly that the sender is requesting a gratis (no-fee) license."
    elif group_fee is not None and rate is not None:
        fee_line = (f"${group_fee:,} for this publisher's catalog — a blanket fee covering its "
                    f"{n_songs} song(s) on this project, priced at ${rate:,.0f} per composition "
                    f"(pro-rated to this publisher's {share:g} song-share)")
        fee_instruction = ("State the proposed blanket license fee for THIS publisher explicitly as the "
                           f"opening offer — ${group_fee:,} total for its songs. Do NOT quote the whole-"
                           "project figure; this offer covers this publisher's catalog only.")
    else:
        fee_line = "open — invite the publisher to quote their standard per-song sync rate"
        fee_instruction = ("No fee set; ask the publisher to quote their per-song sync rate for these songs.")

    mfn_line = ("Yes — most favored nations requested across all publishers (and masters) "
                "being cleared for this project") if mfn else "Not requested"
    mfn_instruction = ("Explicitly request Most Favored Nations (MFN) treatment in the email."
                       if mfn else
                       "Only mention MFN if the songs span multiple co-publishers.")

    lines = (
        f"  License fee: {fee_line}\n"
        f"  Territory: {territory}\n"
        f"  Term: {term}\n"
        f"  Media / uses: {', '.join(uses)}\n"
        f"  Most Favored Nations: {mfn_line}"
        + (f"\n  Additional notes: {notes}" if notes else "")
    )
    return lines, fee_instruction, mfn_instruction


def _mfn_ledger(sub):
    """Advisory Most-Favored-Nations view across the project's music deals
    (publisher groups + master recording license). Flag + suggest only — never
    changes terms. Returns a dict, or None when no deal is MFN-tagged."""
    positions = sub.platform.negotiation_positions if sub.platform else []
    primary = (positions or [{}])[0] if isinstance(positions, list) else {}
    deals = []
    total_comps = _total_compositions(sub)
    for name, g in (sub.publisher_clearances or {}).items():
        dt = (g.get("deal_terms") or sub.deal_terms or {})
        share = _group_share(g)
        # MFN compares the PER-SONG rate. An agreed amount is this publisher's blanket
        # (its catalog share), so the per-song rate = agreed / share; otherwise derive
        # the rate from the deal terms. Same rate across groups → no false "level up".
        agreed = _agreed_fee(_group_deal_points(sub, g))
        if agreed is not None and share > 0:
            per_song = agreed / share
            fee = agreed
        else:
            per_song = _per_song_rate(dt, total_comps)
            fee = (round(per_song * share) if (per_song is not None and share > 0)
                   else _num(dt.get("fee")))
        deals.append({
            "label": name, "kind": "publishing", "mfn": bool(dt.get("mfn")),
            "fee": fee, "per_song": per_song, "fee_type": dt.get("fee_type"),
            "territory": dt.get("territory") or primary.get("territory"),
            "term": dt.get("term") or primary.get("term"),
            "status": g.get("status"), "songs": len(g.get("songs", [])),
        })
    for it in sub.clearance_items:
        if is_music_item(it.item_key) and "master" in (it.item_key or ""):
            dt = it.deal_terms or {}
            mfee = _agreed_fee(_item_deal_points(it))
            if mfee is None:
                mfee = _num(dt.get("fee"))
            deals.append({
                "label": it.item_label, "kind": "master", "mfn": bool(dt.get("mfn")),
                "fee": mfee, "per_song": None, "fee_type": dt.get("fee_type"),
                "territory": dt.get("territory"), "term": dt.get("term"),
                "status": it.status, "songs": None,
            })

    mfn_deals = [d for d in deals if d["mfn"]]
    if not mfn_deals:
        return None

    pub = [d for d in mfn_deals if d["kind"] == "publishing" and d["per_song"] is not None]
    bench = max((d["per_song"] for d in pub), default=None)
    flags = []
    if bench is not None:
        leaders = [d["label"] for d in pub if d["per_song"] == bench]
        for d in pub:
            if d["per_song"] is not None and d["per_song"] < bench:
                flags.append(
                    f"{d['label']} is MFN-tagged at ${d['per_song']:,.0f}/song, but the MFN benchmark on "
                    f"this project is ${bench:,.0f}/song ({', '.join(leaders)}). Level it up to honor MFN, "
                    f"or remove its MFN flag.")
    if any(d["kind"] == "master" for d in mfn_deals):
        flags.append(
            "The master recording license is MFN-tagged — confirm its terms match the most favorable "
            "master deal granted on this project before signing.")
    if not flags:
        flags.append(
            f"MFN is in play across {len(mfn_deals)} deal(s) and current terms are consistent. Any new "
            "concession to one rights holder must be matched to the others.")
    return {"deals": deals, "mfn_deals": mfn_deals, "benchmark_per_song": bench, "flags": flags}


def _mfn_block(sub):
    """MFN-awareness paragraph for negotiation prompts. Empty string if no MFN."""
    led = _mfn_ledger(sub)
    if not led:
        return ""
    bench = led.get("benchmark_per_song")
    parts = ["\n\nMOST FAVORED NATIONS (MFN) — IN PLAY ON THIS PROJECT:"]
    if bench is not None:
        parts.append(f"  Current publishing MFN benchmark: ${bench:,.0f} per song.")
    parts.append(
        "  Because MFN is in play, do NOT agree terms MORE favorable to this rights holder than the benchmark "
        "without flagging it — any better term granted here must be matched to every other MFN-tagged rights "
        "holder. If they demand above-benchmark terms, recommend escalate_to_ba rather than silently conceding.")
    return "\n".join(parts)


# ── Structured deal points (PLB-style our/their/agreed grid), unified across deal types ──
_DEAL_POINT_SETS = {
    "publishing": ["License Fee", "Territory", "Term", "Media / Permitted Uses",
                   "Most Favored Nations", "Cue Sheet Deadline", "Credit"],
    "master":     ["License Fee", "Territory", "Term", "Media / Permitted Uses",
                   "Most Favored Nations", "Re-use / New Use Fees", "Credit"],
    "generic":    ["Fee", "Territory", "Term", "Media / Permitted Uses",
                   "Credit", "Most Favored Nations", "Indemnity"],
}


def _deal_type_for_item(item_key):
    if is_music_item(item_key) and "master" in (item_key or ""):
        return "master"
    if is_music_item(item_key):
        return "publishing"
    return "generic"


def _seed_deal_points(deal_type, terms=None):
    """Fresh deal-points list for a deal type, pre-filling 'our' position from any
    existing structured deal terms (fee/territory/term/media/MFN)."""
    terms = terms or {}
    labels = _DEAL_POINT_SETS.get(deal_type, _DEAL_POINT_SETS["generic"])
    fee, ft = terms.get("fee"), (terms.get("fee_type") or "").strip()
    if fee in (None, ""):
        fee_str = ""
    else:
        try:
            fee_str = f"${int(float(fee)):,} {ft}".strip()
        except (TypeError, ValueError):
            fee_str = f"${fee} {ft}".strip()
    our_for = {
        "License Fee": fee_str, "Fee": fee_str,
        "Territory": terms.get("territory") or "",
        "Term": terms.get("term") or "",
        "Media / Permitted Uses": ", ".join(terms.get("media_rights") or []),
        "Most Favored Nations": ("Requested" if terms.get("mfn") else ""),
    }
    return [{"label": l, "our": our_for.get(l, ""), "their": "", "agreed": "", "status": "open"}
            for l in labels]


def _item_deal_points(item):
    """Deal points for a clearance item, lazily seeded from its deal terms."""
    return item.deal_points or _seed_deal_points(_deal_type_for_item(item.item_key), item.deal_terms)


def _group_deal_points(sub, group):
    """Deal points for a publisher group. When seeding, the 'our' License Fee is this
    publisher's blanket (per-song rate × its catalog share), not the whole-project figure."""
    if group.get("deal_points"):
        return group["deal_points"]
    base = dict(group.get("deal_terms") or sub.deal_terms or {})
    gf, rate, share = _group_offer_fee(sub, group)
    if gf is not None:
        base["fee"], base["fee_type"] = gf, "Flat Fee"  # blanket amount for this publisher
    return _seed_deal_points("publishing", base)


def _agreed_points_block(points):
    """Render the agreed deal points for a prompt. Empty string if none agreed."""
    agreed = [p for p in (points or []) if (p.get("agreed") or "").strip()]
    return "\n".join(f"  - {p['label']}: {p['agreed']}" for p in agreed)


def _agreed_fee(points):
    """Numeric agreed fee parsed from the deal points' 'License Fee'/'Fee' row, or None."""
    for p in (points or []):
        if p.get("label") in ("License Fee", "Fee") and (p.get("agreed") or "").strip():
            m = re.search(r"[\d,]+(?:\.\d+)?", p["agreed"].replace(",", ""))
            if m:
                return _num(m.group(0))
    return None


def _parse_points_form(form):
    """Parse the parallel label[]/our[]/their[]/agreed[]/status[] arrays from a grid save."""
    labels = form.getlist("label"); our = form.getlist("our"); their = form.getlist("their")
    agreed = form.getlist("agreed"); status = form.getlist("status")
    pts = []
    for i, l in enumerate(labels):
        if not (l or "").strip():
            continue
        g = lambda arr: (arr[i] if i < len(arr) else "").strip()
        pts.append({"label": l.strip(), "our": g(our), "their": g(their),
                    "agreed": g(agreed), "status": g(status) or "open"})
    return pts


def _suggest_point_counter(sub, deal_label, point, all_points):
    """AI counter-position for one deal point, using already-agreed sibling terms as
    leverage (the PLB pattern). Returns {counter, rationale, raw} or None."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    agreed_context = _agreed_points_block(all_points) or "None agreed yet."
    prompt = (
        "You are a senior entertainment business-affairs attorney advising the producer on a rights deal.\n\n"
        f"Deal: {deal_label}\nProject: {sub.title} ({sub.project_type_label})\n\n"
        f"Term being negotiated: {point.get('label')}\n"
        f"Our current position: {point.get('our') or '(not set)'}\n"
        f"Their position: {point.get('their') or '(not set)'}\n\n"
        f"Other terms already agreed in this deal:\n{agreed_context}\n\n"
        "Suggest a specific counter-position that advances our interests, is commercially reasonable and likely "
        "to close, accounts for market norms, and uses leverage from the already-agreed terms.\n"
        "Respond with ONLY:\n- COUNTER: [one clear sentence or figure]\n- RATIONALE: [1-2 sentences]"
    )
    raw = call_claude("You are a senior entertainment business-affairs attorney.", prompt, max_tokens=400)
    if not raw:
        return None
    counter = rationale = ""
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("COUNTER:"):
            counter = s.split("COUNTER:", 1)[1].strip()
        elif s.startswith("RATIONALE:"):
            rationale = s.split("RATIONALE:", 1)[1].strip()
    return {"counter": counter, "rationale": rationale, "raw": raw}


app.jinja_env.globals.update(
    deal_points_for_item=_item_deal_points,
    deal_points_for_group=_group_deal_points,
    item_rights_holder=_item_rights_holder,
)


def _parse_neg_json(raw):
    """Extract the negotiation recommendation JSON from a model response."""
    import json as _json
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0]
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        return _json.loads(clean)
    except Exception:
        return {
            "classification": "unclear",
            "assessment": "The AI response could not be parsed. Review the publisher's "
                          "message and draft a reply manually, or regenerate.",
            "recommended_action": "send_reply", "draft_reply": "",
            "deal_term_changes": "none", "confidence": "low",
            "rationale": "Automatic parsing failed.", "raw": raw[:1500],
        }


def _run_group_negotiation(sub, group, publisher):
    """Analyze a publisher group's negotiation thread and draft the next move.
    Mirror of _run_negotiation, but for one blanket-sync publisher group."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    positions = sub.platform.negotiation_positions if sub.platform else []
    primary = (positions or [{}])[0] if isinstance(positions, list) else {}
    offer_lines, _, _ = _format_group_offer(sub, group, primary)
    songs = group.get("songs", [])
    song_str = "\n".join(
        f"  - \"{s.get('title','')}\" ({s.get('writer','')}, {s.get('split_pct','')}%)"
        for s in songs
    ) or "  (no songs)"
    thread = group.get("negotiation_log") or []
    thread_str = "\n\n".join(
        f"[{e.get('label') or e.get('role','message')}]\n{e.get('body','')}" for e in thread
    ) or "(no messages yet)"

    user = (
        f"BLANKET SYNC LICENSE NEGOTIATION — PUBLISHER: {publisher} ({group.get('pro','')})\n"
        f"PUBLISHER CONTACT: {group.get('contact_name') or '[unknown]'} "
        f"<{group.get('contact_email') or 'no email'}>\n\n"
        f"PROJECT:\n{_sub_context(sub)}\n\n"
        f"THIS PUBLISHER'S SONGS IN THE PROJECT ({len(songs)}), covered by ONE blanket license:\n{song_str}\n\n"
        f"DEAL TERMS WE ARE OFFERING:\n{offer_lines}\n\n"
        + (f"DEAL POINTS ALREADY AGREED (do not reopen these):\n{_agreed_points_block(_group_deal_points(sub, group))}\n\n"
           if _agreed_points_block(_group_deal_points(sub, group)) else "")
        + f"PLATFORM NEGOTIATION POSITIONS (primary first, then fallbacks):\n"
        + f"{_fmt_negotiation_positions(positions)}\n"
        + _mfn_block(sub) + "\n"
        + _guideline_block(sub) + "\n"
        f"NEGOTIATION THREAD SO FAR (oldest first):\n{thread_str}\n\n"
        "Analyze the publisher's most recent message and decide the next move for this blanket sync license. "
        "Return a JSON object with EXACTLY these fields:\n"
        '{\n'
        '  "classification": "accepted" | "counter" | "question" | "declined" | "unclear",\n'
        '  "assessment": "2-3 sentences: where the negotiation stands and what they want",\n'
        '  "recommended_action": "finalize" | "send_counter" | "answer_question" | "send_reply" | "escalate_to_ba",\n'
        '  "draft_reply": "the full email body to send next — no subject line, no placeholder brackets, real names. If escalating, a brief holding note.",\n'
        '  "deal_term_changes": "plain text describing any terms conceded or proposed this round, or \\"none\\"",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "rationale": "1-2 sentences on why this is the right move, referencing the platform positions"\n'
        '}\n'
        "Use recommended_action=finalize ONLY when the publisher has agreed the material terms (fee + scope) "
        "for the blanket license. Use escalate_to_ba when they demand something outside the platform positions "
        "or a clear deal-breaker."
    )
    raw = call_claude(_NEGOTIATION_SYSTEM, user, max_tokens=1500)
    return _parse_neg_json(raw) if raw else None


def _generate_group_license(sub, group, publisher):
    """Draft the BLANKET sync license covering this publisher's songs at the
    agreed terms. Returns the document text, or None."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    positions = sub.platform.negotiation_positions if sub.platform else []
    primary = (positions or [{}])[0] if isinstance(positions, list) else {}
    offer_lines, _, _ = _format_group_offer(sub, group, primary)
    songs = group.get("songs", [])
    song_str = "\n".join(
        f"  - \"{s.get('title','')}\" (writer {s.get('writer','')}, "
        f"{s.get('split_pct','')}% controlled by {publisher})"
        for s in songs
    ) or "  (no songs)"
    platform_name = sub.platform.name if sub.platform else "the platform"
    user = (
        f"Draft a BLANKET SYNCHRONIZATION LICENSE covering MULTIPLE musical compositions, "
        f"between the Producer (Licensee) and {publisher} (Licensor / music publisher).\n\n"
        f"LICENSEE (Producer/Submitter): {sub.submitter_company or sub.submitter_name}. "
        f"{platform_name} is named ONLY as permitted assignee/distributor of the finished program — it is NOT a "
        f"contracting party, and the Producer does NOT act 'on behalf of' {platform_name}.\n\n"
        f"LICENSOR (Music Publisher): {publisher}"
        + (f" — contact {group.get('contact_name')}" if group.get('contact_name') else "") + "\n"
        + (f"Performing Rights Org: {group.get('pro')}\n" if group.get('pro') else "")
        + f"\nPROJECT DETAILS:\n{_sub_context(sub)}\n\n"
        f"COMPOSITIONS COVERED BY THIS ONE BLANKET LICENSE ({len(songs)} — license ALL of them in a single agreement):\n{song_str}\n\n"
        f"AGREED DEAL TERMS (these are the ACTUAL agreed terms — incorporate them verbatim, do NOT use placeholders):\n{offer_lines}\n"
        + _guideline_block(sub) + "\n"
        "Draft the complete blanket synchronization license now. It must: identify the parties; grant a synchronization "
        "license for ALL listed compositions under one agreement; state the license fee, territory, term, and permitted "
        "media/uses exactly as agreed above; include Most Favored Nations language if MFN is agreed; permit "
        "assignment/distribution via the named platform; include standard representations & warranties, indemnity, and "
        "signature blocks for both parties. Use the real agreed values for fee, territory, and term — no bracketed placeholders."
    )
    return call_claude_document(_CLP_SYSTEM_PROMPT, user)


def _group_license_agent(sub_id, publisher):
    """Background: draft the blanket sync license for a publisher group and store it."""
    with app.app_context():
        sub = Submission.query.get(sub_id)
        if not sub:
            return
        groups = sub.publisher_clearances
        g = groups.get(publisher)
        if not g:
            return
        try:
            doc = _generate_group_license(sub, g, publisher)
        except Exception as e:
            app.logger.error(f"GROUP LICENSE ERROR — {type(e).__name__}: {e}")
            doc = None
        if doc:
            g["license_draft"] = doc
            g["license_generated_at"] = datetime.utcnow().isoformat()
            sub.publisher_clearances_save(groups)
            db.session.commit()


@app.route("/track/<token>/pub-groups/outreach", methods=["POST"])
def track_pub_groups_outreach(token):
    from flask import jsonify
    sub = _sub(token)
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
    platform_name = sub.platform.name if sub.platform else "the platform"

    # Build the OFFER from the submitter's saved deal terms so the email states a
    # real proposal (incl. the fee) instead of vaguely asking to "discuss terms".
    # Prefer this group's own terms, then the submission-level bulk terms, then the
    # platform's default position for territory/term/uses.
    offer_lines, fee_instruction, mfn_instruction = _format_group_offer(sub, g, primary)

    system = (
        "You are a music clearance professional helping a content producer draft sync license request emails. "
        "The email is sent BY the producer/submitter, in their own name and company — NOT by the platform. "
        "Reference the project and the platform it will stream on as context only; never write that the sender is "
        "contacting anyone 'on behalf of' the platform, and never imply the sender represents or works for the platform. "
        "Write professional, concise outreach. Do not use placeholders — write real content. "
        "State the proposed deal terms (including the fee) plainly as the sender's opening offer."
    )
    user = (
        f"Draft a sync license request email to {publisher}'s sync licensing department.\n\n"
        f"Sender (the requester making this request): {sub.submitter_name or 'Music Clearance Team'}"
        + (f", {sub.submitter_company}" if sub.submitter_company else "") + "\n"
        f"Project: {sub.project_type_label} — {sub.title}\n"
        f"Artist performing: {sub.artist_name or 'Unknown'}\n"
        f"Event: {sub.event_name or sub.title}\n"
        f"Venue: {sub.venue or 'TBD'}\n"
        f"Date: {sub.event_date or 'TBD'}\n"
        f"Distribution platform (context only — where the finished project will stream): {platform_name}\n\n"
        f"Songs requesting clearance ({len(g.get('songs', []))} total):\n{song_list}\n\n"
        f"Deal terms the sender is OFFERING — state these as the proposed terms, do not be vague:\n"
        + offer_lines + "\n\n"
        f"{fee_instruction} {mfn_instruction} "
        f"The sender is the producer making this request for their own project, which will stream on {platform_name}. "
        f"Reference {platform_name} only as the distribution outlet — do NOT write 'on behalf of {platform_name}' or "
        f"state that the sender represents {platform_name}. "
        f"Request that all songs be covered under one blanket sync license agreement for efficiency. "
        f"Sign off with just the sender's name and company. "
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


@app.route("/track/<token>/pub-groups/save-outreach", methods=["POST"])
def track_pub_groups_save_outreach(token):
    """Save a hand-edited grouped outreach draft (no AI regeneration)."""
    from flask import jsonify
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    body = request.form.get("outreach", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return jsonify({"error": "Publisher group not found"}), 404
    groups[publisher]["ai_outreach"] = body
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/track/<token>/pub-groups/send", methods=["POST"])
def track_pub_groups_send(token):
    from flask import jsonify
    import resend as _resend
    sub = _sub(token)
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
        groups[publisher]["outreach_sent_at"] = datetime.utcnow().isoformat()
        groups[publisher]["status"] = "in_progress"
        # Seed the negotiation thread so the back-and-forth console opens.
        groups[publisher].setdefault("negotiation_log", []).append({
            "role": "outbound", "label": "Sync request sent",
            "body": g["ai_outreach"], "ts": datetime.utcnow().isoformat(),
        })
        groups[publisher]["neg_state"] = "awaiting_reply"
        sub.publisher_clearances_save(groups)
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _maybe_advance_publishing_item(sub):
    """When every publisher clearance group has been accepted (status 'cleared'),
    move the submission's Publishing Clearance item into BA review so it enters
    the approval queue — the same sign-off path every other item follows."""
    groups = sub.publisher_clearances
    if not groups or not all(g.get("status") == "cleared" for g in groups.values()):
        return False
    advanced = False
    for it in sub.clearance_items:
        if "publish" in (it.item_label or "").lower() and it.status not in ("under_review", "cleared", "waived"):
            it.status = "under_review"
            advanced = True
    return advanced


@app.route("/track/<token>/pub-groups/response", methods=["POST"])
def track_pub_groups_response(token):
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
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
    # If that was the last publisher, route the Publishing Clearance item to BA sign-off.
    if resp == "accepted":
        _maybe_advance_publishing_item(sub)
    db.session.commit()
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


# ── Publisher-group AI negotiation (back-and-forth, mirrors the per-item loop) ──
@app.route("/track/<token>/pub-groups/record-reply", methods=["POST"])
def track_pub_groups_record_reply(token):
    """Submitter pastes the publisher's reply; AI analyzes it and drafts the next move."""
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    reply = request.form.get("reply_body", "").strip()
    if not reply:
        flash("Paste the publisher's reply before recording it.", "warning")
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    g = groups[publisher]
    g.setdefault("negotiation_log", []).append({
        "role": "inbound", "label": f"{publisher} reply",
        "body": reply, "ts": datetime.utcnow().isoformat(),
    })
    g["neg_state"] = "analyzing"
    sub.publisher_clearances_save(groups)
    db.session.commit()
    # Run synchronously — consistent with how this section's outreach is drafted.
    rec = None
    try:
        rec = _run_group_negotiation(sub, g, publisher)
    except Exception as e:
        app.logger.error(f"GROUP NEG ERROR — {type(e).__name__}: {e}")
    if rec:
        g["ai_recommendation"] = rec
        g["neg_state"] = "needs_approval"
        flash("Reply recorded — Cleared.live drafted the next move below.", "info")
    else:
        g["neg_state"] = "awaiting_reply"
        flash("Reply recorded, but the AI couldn't draft a response. Try Regenerate.", "warning")
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/regenerate", methods=["POST"])
def track_pub_groups_regenerate(token):
    """Re-run the group negotiation AI, optionally with submitter guidance."""
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    g = groups[publisher]
    guidance = request.form.get("guidance", "").strip()
    if guidance:
        g.setdefault("negotiation_log", []).append({
            "role": "system", "label": "Submitter guidance to AI",
            "body": guidance, "ts": datetime.utcnow().isoformat(),
        })
    g["neg_state"] = "analyzing"
    sub.publisher_clearances_save(groups)
    db.session.commit()
    rec = None
    try:
        rec = _run_group_negotiation(sub, g, publisher)
    except Exception as e:
        app.logger.error(f"GROUP NEG REGEN ERROR — {type(e).__name__}: {e}")
    g["ai_recommendation"] = rec or None
    g["neg_state"] = "needs_approval" if rec else "awaiting_reply"
    sub.publisher_clearances_save(groups)
    db.session.commit()
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/approve-send", methods=["POST"])
def track_pub_groups_approve_send(token):
    """Submitter approves the AI's drafted move. Either finalize (terms agreed) or
    send the reply to the publisher and loop for the next round."""
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    g = groups[publisher]
    rec = g.get("ai_recommendation") or {}
    body = request.form.get("draft_reply", "").strip() or rec.get("draft_reply", "")
    action = rec.get("recommended_action", "send_reply")

    # --- Terms agreed → clear the group (Phase 3 will draft the blanket license here) ---
    if action == "finalize":
        g.setdefault("negotiation_log", []).append({
            "role": "system", "label": "Terms agreed",
            "body": body or "Material terms agreed for the blanket sync license.",
            "ts": datetime.utcnow().isoformat(),
        })
        g["neg_state"] = "agreed"
        g["status"] = "cleared"
        g["ai_recommendation"] = None
        sub.publisher_clearances_save(groups)
        _maybe_advance_publishing_item(sub)
        db.session.commit()
        # Draft the blanket sync license in the background (it's a long 2-pass call).
        threading.Thread(target=_group_license_agent, args=(sub.id, publisher), daemon=True).start()
        flash(f"{publisher}: terms agreed — drafting the blanket sync license (refresh in ~30–60s).", "success")
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)

    # --- Otherwise send the drafted reply and wait for the next round ---
    sent = False
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key and g.get("contact_email") and body:
        try:
            import resend as _resend
            _resend.api_key = resend_key
            _resend.Emails.send({
                "from": f"{sub.submitter_name or sub.submitter_company or 'Clearance Team'} <clear@cleared.live>",
                "to": [g["contact_email"]],
                "subject": f"Re: Sync License — {sub.title} ({publisher})",
                "text": body,
            })
            sent = True
        except Exception as e:
            app.logger.error(f"GROUP NEG SEND ERROR — {type(e).__name__}: {e}")
    g.setdefault("negotiation_log", []).append({
        "role": "outbound",
        "label": "Reply sent to publisher" if sent else "Reply (Resend unavailable — copy & send manually)",
        "body": body, "ts": datetime.utcnow().isoformat(),
    })
    g["neg_state"] = "awaiting_reply"
    g["ai_recommendation"] = None
    sub.publisher_clearances_save(groups)
    db.session.commit()
    flash("Sent — record the publisher's next reply when it arrives." if sent
          else "Drafted, but Resend isn't configured — copy the reply and send it manually.",
          "success" if sent else "warning")
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/gen-license", methods=["POST"])
def track_pub_groups_gen_license(token):
    """Manually (re)generate the blanket sync license for a publisher group."""
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    threading.Thread(target=_group_license_agent, args=(sub.id, publisher), daemon=True).start()
    flash(f"Drafting the blanket sync license for {publisher} — refresh in ~30–60 seconds.", "info")
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/license.txt")
def track_pub_groups_license_download(token):
    """Download a publisher group's blanket sync license as plain text."""
    from flask import Response
    sub = _sub(token)
    publisher = request.args.get("publisher", "").strip()
    g = (sub.publisher_clearances or {}).get(publisher) or {}
    doc = g.get("license_draft") or ""
    fname = (f"{publisher} - Blanket Sync License.txt").replace("/", "-")
    return Response(doc, mimetype="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── Structured deal-points grid (our / their / agreed) — works for items AND groups ──
@app.route("/track/<token>/item/<int:item_id>/deal-points", methods=["POST"])
def track_item_deal_points(token, item_id):
    sub = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    item.deal_points_save(_parse_points_form(request.form))
    db.session.commit()
    flash("Deal points saved.", "success")
    return _submitter_redirect(token, f"#item-card-{item_id}")


@app.route("/track/<token>/item/<int:item_id>/point-counter", methods=["POST"])
def track_item_point_counter(token, item_id):
    from flask import jsonify
    sub = _sub(token)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    pts = _item_deal_points(item)
    try:
        idx = int(request.form.get("idx", -1))
    except (TypeError, ValueError):
        idx = -1
    if not (0 <= idx < len(pts)):
        return jsonify({"error": "Bad point index"}), 400
    res = _suggest_point_counter(sub, item.item_label, pts[idx], pts)
    if not res:
        return jsonify({"error": "AI unavailable"}), 503
    return jsonify(res)


@app.route("/track/<token>/pub-groups/deal-points", methods=["POST"])
def track_pub_groups_deal_points(token):
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    groups = sub.publisher_clearances
    if publisher not in groups:
        return _submitter_redirect(token, "#pub-clearance-section", music_only=True)
    groups[publisher]["deal_points"] = _parse_points_form(request.form)
    sub.publisher_clearances_save(groups)
    db.session.commit()
    flash("Deal points saved.", "success")
    return _submitter_redirect(token, "#pub-clearance-section", music_only=True)


@app.route("/track/<token>/pub-groups/point-counter", methods=["POST"])
def track_pub_groups_point_counter(token):
    from flask import jsonify
    sub = _sub(token)
    publisher = request.form.get("publisher", "").strip()
    g = (sub.publisher_clearances or {}).get(publisher) or {}
    pts = _group_deal_points(sub, g)
    try:
        idx = int(request.form.get("idx", -1))
    except (TypeError, ValueError):
        idx = -1
    if not (0 <= idx < len(pts)):
        return jsonify({"error": "Bad point index"}), 400
    res = _suggest_point_counter(sub, f"Sync license — {publisher}", pts[idx], pts)
    if not res:
        return jsonify({"error": "AI unavailable"}), 503
    return jsonify(res)


@app.route("/track/<token>/songs/<int:idx>/deal-terms", methods=["POST"])
def track_song_deal_terms(token, idx):
    sub = _sub(token)
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
    return _submitter_redirect(token, "#songs-section", music_only=True)


@app.route("/track/<token>/songs/bulk-deal-terms", methods=["POST"])
def track_song_bulk_deal_terms(token):
    sub = _sub(token)
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
    return _submitter_redirect(token, "#songs-section", music_only=True)


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
                "from": "Cleared.live <clear@cleared.live>",  # TODO: swap to clear@cleared.live once domain verified
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
        pending_count=len(_pending_approvals(platform)),
    )


def _pending_approvals(platform):
    """(submission, item) pairs awaiting BA sign-off — submitter has uploaded
    documents and moved the item to under_review — across the whole platform."""
    pending = []
    subs = (Submission.query.filter_by(platform_id=platform.id)
            .order_by(Submission.created_at.desc()).all())
    for sub in subs:
        for it in sub.clearance_items:
            if it.status == "under_review":
                pending.append((sub, it))
    return pending


@app.route("/platform/approvals")
@require_platform
def platform_approvals():
    user     = current_platform_user()
    platform = user.platform
    pending  = _pending_approvals(platform)
    return render_template(
        "platform/approvals.html",
        platform=platform,
        pending=pending,
        pending_count=len(pending),
    )


def _safe_next():
    """Return the posted `next` URL only if it's a safe local platform path."""
    nxt = (request.form.get("next") or "").strip()
    if nxt.startswith("/platform/") and "//" not in nxt[1:]:
        return nxt
    return None


def _send_reservation_email(sub, item, ba_user):
    """On BA approval, email the submitter a reservation-of-rights / continuing
    indemnity notice: the platform's sign-off is administrative, made in reliance
    on the submitter, who remains responsible for proper clearance and continues
    to indemnify the platform. Sent to the submitter, cc Cleared.live + the BA."""
    platform = sub.platform
    pname    = platform.name if platform else "the platform"
    party    = sub.submitter_company or sub.submitter_name or "the submitter"
    when     = datetime.utcnow().strftime("%B %d, %Y")
    body = (
        f"Dear {sub.submitter_name or 'Submitter'},\n\n"
        f"{pname} has recorded its clearance sign-off on the following item:\n\n"
        f"  Item:    {item.item_label}\n"
        f"  Project: {sub.title}" + (f" — {sub.artist_name}" if sub.artist_name else "") + "\n"
        f"  Sign-off date: {when}\n\n"
        f"This sign-off is administrative and is provided on the following express terms:\n\n"
        f"1. Reliance on Submitter. {pname}'s acceptance is made in reliance on the "
        f"representations, documentation, and clearances provided by {party}. {pname} has not "
        f"independently verified the underlying rights and assumes no responsibility for the "
        f"accuracy or completeness of the clearance materials.\n\n"
        f"2. Continuing Indemnity. {party} remains responsible for ensuring that all rights, "
        f"licenses, consents, and releases required for the use of the materials have been fully and "
        f"properly obtained, and continues to indemnify, defend, and hold harmless {pname} and its "
        f"affiliates from and against any claims, damages, liabilities, costs, and expenses "
        f"(including reasonable attorneys' fees) arising out of or relating to any actual or alleged "
        f"failure to secure such rights or any breach of the foregoing.\n\n"
        f"3. Reservation of Rights. Nothing in this sign-off limits or waives any right or remedy "
        f"available to {pname}, all of which are expressly reserved.\n\n"
        f"This notice is provided for clearance-coordination purposes and does not constitute legal advice.\n\n"
        f"Business Affairs\n{pname}\nvia Cleared.live"
    )
    resend_key = os.getenv("RESEND_API_KEY")
    if not (resend_key and sub.submitter_email):
        return False
    cc = ["clear@cleared.live"]
    if ba_user and ba_user.email and ba_user.email not in cc:
        cc.append(ba_user.email)
    try:
        import resend as _resend
        _resend.api_key = resend_key
        _resend.Emails.send({
            "from": f"{pname} Business Affairs <clear@cleared.live>",
            "to": [sub.submitter_email],
            "cc": cc,
            "reply_to": "clear@cleared.live",
            "subject": f"Clearance Sign-Off — Reservation of Rights & Continuing Indemnity — {item.item_label} | {sub.title}",
            "text": body,
        })
        return True
    except Exception as e:
        app.logger.error(f"RESERVATION EMAIL ERROR — item={item.id} error={e}")
        return False


_RESERVATION_LOG_LABEL = "Reservation-of-rights & indemnity notice sent on approval"


def _reservation_already_sent(item):
    """True if a reservation-of-rights notice was already logged for this item,
    so clearing it again (via a different route) doesn't double-email."""
    for turn in (item.negotiation_log or []):
        if (turn.get("label") or "").startswith("Reservation-of-rights"):
            return True
    return False


def _notify_on_clear(sub, item, ba_user):
    """Send the reservation-of-rights / continuing-indemnity notice once, when an
    item is cleared — regardless of whether it was cleared via the Approval Queue
    or the project status dropdown. No-op if already sent for this item."""
    if _reservation_already_sent(item):
        return False
    if not _send_reservation_email(sub, item, ba_user):
        return False
    item.negotiation_log_add({
        "role": "system", "label": _RESERVATION_LOG_LABEL,
        "body": f"Sign-off recorded by {ba_user.username}. Reservation-of-rights / continuing-indemnity "
                f"notice emailed to {sub.submitter_email} (cc clear@cleared.live).",
        "ts": datetime.utcnow().isoformat(),
    })
    return True


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


def _project_paper_trail(sub):
    """Flatten every clearance item's negotiation thread into one chronological
    list for the project — the audit trail of all negotiations in one place."""
    trail = []
    for item in sub.clearance_items:
        for turn in item.negotiation_log:
            ts = turn.get("ts")
            when = None
            if ts:
                try:
                    when = datetime.fromisoformat(ts)
                except Exception:
                    when = None
            trail.append({
                "item_id":    item.id,
                "item_label": item.item_label,
                "item_key":   item.item_key,
                "role":       turn.get("role", "system"),
                "label":      turn.get("label", ""),
                "body":       turn.get("body", ""),
                "ts":         ts,
                "when":       when,
            })
    # Newest first; entries without a timestamp sink to the bottom.
    trail.sort(key=lambda e: (e["when"] is not None, e["when"] or datetime.min), reverse=True)
    return trail


@app.route("/platform/project/<int:sub_id>/agreements")
@require_platform
def platform_agreements(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    # Surface every agreement, most-advanced + most-recently-active first.
    items = sorted(
        sub.clearance_items,
        key=lambda it: (it.agreement_stage_order, it.agreement_last_activity or datetime.min),
        reverse=True,
    )
    return render_template(
        "platform/agreements.html",
        sub=sub,
        platform=user.platform,
        items=items,
        paper_trail=_project_paper_trail(sub),
    )


@app.route("/platform/project/<int:sub_id>/item/<int:item_id>/agreement.docx")
@require_platform
def platform_item_agreement_docx(sub_id, item_id):
    """BA-side download of an item's AI-drafted agreement as a Word .docx."""
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    item = ClearanceItem.query.get_or_404(item_id)
    if item.submission_id != sub.id:
        abort(403)
    draft_text = item.ai_draft or f"[Draft pending for {item.item_label}]"
    doc_bytes  = build_docx(_DocxProxy(title=item.item_label, content=draft_text))
    safe = re.sub(r"[^A-Za-z0-9]+", "-", item.item_label).strip("-").lower() or "agreement"
    return send_file(
        io.BytesIO(doc_bytes),
        as_attachment=True,
        download_name=f"{safe}-draft.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
        # Sign-off via the status dropdown sends the same reservation-of-rights
        # notice as the Approval Queue (guarded so it never double-sends).
        if new_status == "cleared":
            _notify_on_clear(sub, item, user)
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

    # Auto-send the reservation-of-rights / continuing-indemnity notice to the
    # submitter (cc Cleared.live + the approving BA) and record it on the item.
    _notify_on_clear(sub, item, user)
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

    return redirect(_safe_next() or url_for("platform_project", sub_id=sub_id))


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
    return redirect(_safe_next() or url_for("platform_project", sub_id=sub_id))


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
        # Capture plain values NOW, while the session is live. Passing the ORM
        # objects (item/sub) into the thread fails: after the request closes,
        # they're detached/expired and any attribute access raises
        # DetachedInstanceError, killing the thread before it drafts.
        item_id   = item.id
        prompt = (
            f"Draft a {category} agreement for: {label}.\n"
            f"Project: {sub.title} ({sub.project_type}) for {sub.platform.name}.\n"
            f"Territory: {sub.territory}. BA notes: {notes or 'none'}.\n"
            f"Use [BRACKETS] for party names, dates, and amounts to fill in. "
            f"Be concise and legally precise."
        )

        def _draft(item_id=item_id, prompt=prompt):
            with app.app_context():
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    resp = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1500,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    it = ClearanceItem.query.get(item_id)   # re-query in this session
                    if it:
                        it.ai_draft = resp.content[0].text
                        db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"AI draft for custom item failed: {e}")

        threading.Thread(target=_draft, daemon=True).start()
        flash(f"'{label}' added — draft generating in background (~30 sec).", "success")
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
    # ?inline=1 serves the file for in-browser preview (e.g. PDF in an iframe);
    # default is a download attachment.
    inline = request.args.get("inline") == "1"
    return send_file(
        __import__("io").BytesIO(doc.file_data),
        download_name=doc.filename,
        as_attachment=not inline,
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
            platform_mode   = request.form.get("platform_mode", "clearance"),
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
        p.platform_mode  = request.form.get("platform_mode", p.platform_mode or "clearance")
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
    flash(f"Regenerating {len(sub.clearance_items)} drafts in background — refresh in ~60 seconds.", "info")
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
        flash(f"Draft generated for {item.item_label}.", "success")
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


@app.route("/platform/project/<int:sub_id>/docusign-sync", methods=["POST"])
@require_platform
def platform_docusign_sync(sub_id):
    """Poll fallback: check every pending envelope on this project and pull down
    any that have completed — complements the automatic Connect webhook."""
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    if not docusign_configured():
        flash("DocuSign is not configured.", "warning")
        return redirect(url_for("platform_agreements", sub_id=sub_id))
    pending = [it for it in sub.clearance_items
               if it.docusign_envelope_id and not it.executed_documents]
    stored = 0
    for it in pending:
        ok, _ = fetch_executed_envelope(it)
        if ok:
            stored += 1
    db.session.commit()
    if not pending:
        flash("No pending DocuSign envelopes to sync.", "info")
    elif stored:
        flash(f"Synced {len(pending)} envelope(s) — {stored} executed agreement(s) "
              f"downloaded and added to the record.", "success")
    else:
        flash(f"Checked {len(pending)} envelope(s) — none are completed yet.", "info")
    return redirect(url_for("platform_agreements", sub_id=sub_id))


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


_GUIDELINE_PUBLIC_SYSTEM = """You translate a streaming platform's INTERNAL clearance guidelines into a plain-English preparation guide for the SUBMITTER (the content producer). Write what the submitter must do to get cleared: documents to gather, rights and consents to confirm, parties to contact, and what to prepare before and during submission. Friendly, practical, concise. Do NOT include anything internal: no deal strategy, negotiation leverage, fallback positions, pricing, what to 'push back on', or anything the platform would not want a counterparty to read. No legal boilerplate."""

def _guideline_public_user_prompt(project_type, platform_name, internal_content):
    return (
        f"Platform: {platform_name}\n"
        f"Project type: {project_type.replace('_', ' ').title()}\n\n"
        f"INTERNAL BA GUIDELINES (source material — strip out all internal-only strategy):\n"
        f"{internal_content}\n\n"
        f"Write the submitter-facing version as a clear preparation checklist, grouped by clearance "
        f"item with a short heading each. Focus only on what the submitter needs to gather, confirm, "
        f"and do. Omit internal strategy, pricing, fallback positions, and platform negotiating leverage."
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
                    continue_on_truncation=True,
                )
            except Exception as e:
                flash(f"Draft generation failed: {e}", "danger")
                return redirect(url_for("platform_guideline_detail", project_type=project_type))
            if not g:
                g = ClearanceGuideline(platform_id=user.platform_id, project_type=project_type)
                db.session.add(g)
            g.content = content
            g.status = "draft"
            db.session.commit()
            flash("Draft generated. Review and approve when ready.", "success")

        elif action == "ai_public_draft":
            # Draft a plain-English submitter-facing version from the internal guidelines.
            source = request.form.get("content", "").strip() or (g.content if g else "")
            if not source:
                flash("Generate or save the internal guidelines first.", "warning")
                return redirect(url_for("platform_guideline_detail", project_type=project_type))
            try:
                public = call_claude(
                    _GUIDELINE_PUBLIC_SYSTEM,
                    _guideline_public_user_prompt(project_type, platform.name, source),
                    max_tokens=4000,
                    continue_on_truncation=True,
                )
            except Exception as e:
                flash(f"Submitter draft failed: {e}", "danger")
                return redirect(url_for("platform_guideline_detail", project_type=project_type))
            if not g:
                g = ClearanceGuideline(platform_id=user.platform_id, project_type=project_type)
                db.session.add(g)
            g.content = source           # keep internal in sync with what we drafted from
            g.public_content = public
            g.status = "draft"
            db.session.commit()
            flash("Submitter-facing draft generated. Review it, tick 'Show to submitters', then Save.", "success")

        elif action == "save":
            if not g:
                g = ClearanceGuideline(platform_id=user.platform_id, project_type=project_type)
                db.session.add(g)
            # Each editor section saves independently — only touch the fields the
            # submitted form actually carries, so saving one section never wipes
            # the other's content or the visibility toggle.
            if "content" in request.form:
                g.content = request.form.get("content", "").strip()
            if "public_content" in request.form:
                g.public_content = request.form.get("public_content", "").strip()
            if request.form.get("submitter_settings") == "1":
                g.show_to_submitters = request.form.get("show_to_submitters") == "1"
            # Preserve approval across edits — saving must not silently un-publish.
            if not g.status:
                g.status = "draft"
            db.session.commit()
            flash("Guidelines saved.", "success")

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
    for it in sub.submitter_items:
        if it.status in ("cleared", "waived", "n_a", "under_review"):
            continue
        if it.neg_state == "needs_approval":
            rec = it.ai_recommendation or {}
            if rec.get("recommended_action") == "send_for_signature":
                actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "high",
                                "action": "Approve & send for signature",
                                "detail": "AI says terms are agreed — one click to send the agreement."})
            else:
                actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "high",
                                "action": "Approve the AI's drafted reply",
                                "detail": rec.get("assessment") or "Cleared.live drafted your next move."})
        elif it.neg_state == "awaiting_reply":
            last = _last_outbound_at(it)
            if last and (datetime.utcnow() - last) > timedelta(days=STALL_DAYS):
                days = (datetime.utcnow() - last).days
                actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "medium",
                                "action": "Follow up — no reply",
                                "detail": f"No response in {days} days. Record a reply or send a nudge."})
        elif it.status == "pending":
            actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "low",
                            "action": "Start clearance", "detail": "Not started yet."})
        elif it.status == "in_progress" and not it.ai_outreach_sent_at:
            if it.party_email and it.ai_outreach_body:
                actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "medium",
                                "action": "Send outreach",
                                "detail": "Draft and contact are ready — one click to send."})
            else:
                actions.append({"item_id": it.id, "label": it.submitter_label, "item_key": it.item_key, "urgency": "medium",
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


@app.route("/docusign/connect", methods=["POST"])
def docusign_connect():
    """DocuSign Connect webhook → when an envelope completes, store the executed
    PDF automatically. Configure a Connect listener in DocuSign Admin pointing
    here; for a signed payload set DOCUSIGN_CONNECT_HMAC_KEY to your Connect key."""
    raw = request.get_data()
    key = (os.getenv("DOCUSIGN_CONNECT_HMAC_KEY") or "").strip()
    if key:
        import hmac, hashlib, base64 as _b64
        expected = _b64.b64encode(
            hmac.new(key.encode("utf-8"), raw, hashlib.sha256).digest()).decode()
        # DocuSign sends one signature header per account Connect key
        # (X-DocuSign-Signature-1, -2, ...). Accept if ANY of them matches, so a
        # second/rotated key doesn't lock us out.
        provided = [v for h, v in request.headers.items()
                    if h.lower().startswith("x-docusign-signature-")]
        if not any(hmac.compare_digest(p.strip(), expected) for p in provided):
            app.logger.warning(
                "DocuSign Connect HMAC mismatch — provided=%r expected=%r body_len=%d",
                provided, expected, len(raw))
            abort(403)
    env_id, status = _parse_connect_payload(request)
    if not env_id:
        return ("", 200)   # ack payloads we can't parse so DocuSign won't retry
    item = ClearanceItem.query.filter_by(docusign_envelope_id=env_id).first()
    if not item:
        return ("", 200)
    if status:
        item.docusign_status = status
        db.session.commit()
    if status == "completed":
        # Pull the executed PDF synchronously before acking. Fire-and-forget
        # threads are unreliable on a sync gunicorn worker (the request returns
        # before the thread stores the doc), so do it inline — the fetch takes a
        # few seconds and DocuSign Connect's delivery timeout is generous.
        try:
            fetch_executed_envelope(item)
            db.session.commit()
        except Exception:
            db.session.rollback()
    return ("", 200)


@app.route("/inbound/email", methods=["POST"])
def inbound_email():
    """Inbound-email webhook → append the reply to the thread and run the AI agent.

    Tolerant of three shapes:
      • SendGrid Inbound Parse — multipart/form-data: `to`, `from`, `subject`,
        `text`/`html`, `envelope` (JSON with the real RCPT TO).
      • Mailgun Routes — multipart/form-data: `recipient`, `sender`,
        `body-plain`/`stripped-text`, `To`.
      • JSON (e.g. Resend, or manual/test posts): {data:{to,text,...}} or flat.
    """
    secret = request.args.get("secret")
    if os.getenv("INBOUND_SECRET") and secret != os.getenv("INBOUND_SECRET"):
        abort(403)

    # JSON payloads (Resend / manual test) ...
    data = request.get_json(silent=True) or {}
    payload = data.get("data", data) if isinstance(data, dict) else {}
    # ... merged with form fields (SendGrid Inbound Parse / Mailgun Routes).
    form = request.form

    def _f(*keys):
        for k in keys:
            v = payload.get(k) if isinstance(payload, dict) else None
            if v:
                return v
        for k in keys:
            v = form.get(k)
            if v:
                return v
        return ""

    # Recipient: SendGrid `to`/`To`, Mailgun `recipient`, JSON `to`/`to_address`.
    to_field = _f("to", "To", "recipient", "to_address")
    token = _extract_reply_token(to_field)

    # SendGrid puts the true RCPT TO in `envelope` (JSON) — fall back to it.
    if not token:
        env_raw = _f("envelope")
        if env_raw:
            try:
                env = env_raw if isinstance(env_raw, dict) else json.loads(env_raw)
                token = _extract_reply_token(env.get("to") or "")
            except (ValueError, TypeError):
                pass

    # Body: prefer plain text, drop to HTML last. Mailgun uses `body-plain`/`stripped-text`.
    text = _f("text", "stripped-text", "body-plain", "body", "html", "body-html")
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
    seed_templates()

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



@app.cli.command("send-invite")
@click.argument("platform_slug")
@click.argument("email")
@click.argument("name", required=False)
def send_invite_cmd(platform_slug, email, name=None):
    """Send a submitter invite as a platform's BA. Usage: flask send-invite <slug> <email> [name]"""
    p = Platform.query.filter_by(slug=platform_slug).first()
    if not p:
        print(f"Platform '{platform_slug}' not found.")
        return
    invite = Invite(platform_id=p.id, email=email.strip().lower(), name=name or None)
    db.session.add(invite)
    db.session.commit()

    base       = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    invite_url = f"{base}/submit/{p.slug}?invite={invite.token}" if base \
                 else f"/submit/{p.slug}?invite={invite.token}"

    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        import resend as _resend
        _resend.api_key = resend_key
        with app.test_request_context():
            body = render_template("email/invite.html",
                platform_name=p.name, platform_color=p.primary_color or "#0d3b6e",
                name=name or None, project_hint=None, invite_url=invite_url)
        _resend.Emails.send({
            "from": "Cleared.live <clear@cleared.live>",
            "to": email,
            "subject": f"You've been invited to submit a clearance request — {p.name}",
            "html": body,
        })
        print(f"Invite emailed to {email} from {p.name}.")
    else:
        print("RESEND_API_KEY not set — no email sent.")
    print(f"Invite link: {invite_url}")


def _run_release_reminders():
    """Send automated follow-ups for unsigned releases (day 3 / 6 / 9, then stop).
    Idempotent: the 3-day gap guard means running it more than once a day sends nothing
    extra, so it's safe to drive from either the CLI or the in-app scheduler."""
    now = datetime.utcnow()
    due = ReleaseRequest.query.filter(
        ReleaseRequest.status.in_(["sent", "viewed"]),
        ReleaseRequest.reminders_sent < 3,
    ).all()
    sent_n = flagged_n = 0
    for rr in due:
        anchor = rr.last_reminder_at or rr.sent_at or rr.created_at
        if not anchor or (now - anchor).days < 3:
            continue
        sub = rr.submission
        ok = _send_release_email(sub, rr, reminder=True)
        rr.reminders_sent   = (rr.reminders_sent or 0) + 1
        rr.last_reminder_at = now
        rr.log_add("reminder", f"Auto reminder #{rr.reminders_sent} "
                               f"({'sent' if ok else 'no email configured'})")
        if rr.reminders_sent >= 3:
            rr.log_add("reminders_exhausted", "3 reminders sent — needs manual follow-up")
            flagged_n += 1
        sent_n += 1
    db.session.commit()
    return sent_n, flagged_n


def _release_reminder_scheduler():
    """Background daemon: sweep for due release reminders a few times a day.
    No external cron needed — runs inside the web process. The reminder sweep's own
    day-gap guard makes repeated runs safe."""
    import time
    # Small startup delay so the first sweep doesn't race app boot / migrations.
    time.sleep(60)
    while True:
        try:
            with app.app_context():
                sent_n, flagged_n = _run_release_reminders()
                if sent_n:
                    app.logger.info(f"Release reminders: {sent_n} sent, {flagged_n} flagged")
        except Exception as e:
            app.logger.error(f"Release reminder sweep failed: {type(e).__name__}: {e}")
        time.sleep(6 * 60 * 60)   # every 6 hours


@app.cli.command("release-reminders")
def release_reminders_cmd():
    """Send automated follow-ups for unsigned releases (day 3 / 6 / 9, then stop)."""
    sent_n, flagged_n = _run_release_reminders()
    print(f"Release reminders: {sent_n} sent, {flagged_n} flagged for manual follow-up")


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
        ("deal_points_json",     "TEXT"),
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
        # Add release_template to submissions (custom general-release text)
        try:
            conn.execute(sa_text(
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS release_template TEXT"
            ))
            conn.commit()
            print("  submissions.release_template OK")
        except Exception as exc:
            conn.rollback()
            print(f"  submissions.release_template: {exc}")
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
        for col_name, col_type in [
            ("music_access_token", "VARCHAR(40)"),
            ("music_contact_name", "VARCHAR(200)"),
            ("music_contact_email", "VARCHAR(200)"),
        ]:
            try:
                conn.execute(sa_text(f"ALTER TABLE submissions ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                conn.commit()
                print(f"  submissions.{col_name} OK")
            except Exception as exc:
                conn.rollback()
                print(f"  submissions.{col_name}: {exc}")

    # Backfill: ensure every existing submission carries the E&O item its template
    # requires. E&O was removed from the creator types (live_music, festival, documentary,
    # social, podcast) — those have no eo_def, so they're skipped here. Only the non-creator
    # types that still require E&O (unscripted, label review, feature_film, tv_series, branded)
    # are backfilled. Idempotent; only adds, never removes.
    eo_defs = {}
    for tkey, items in CLEARANCE_TEMPLATES.items():
        for it in items:
            if it["key"].startswith("eo_"):
                eo_defs[tkey] = it
    added = 0
    for s in Submission.query.all():
        tkey = "live_music_label" if (s.platform and s.platform.platform_mode == "label_waiver") else s.project_type
        eo = eo_defs.get(tkey)
        if not eo:
            continue  # e.g. UGC has no E&O item
        if not any(ci.item_key == eo["key"] for ci in s.clearance_items):
            db.session.add(ClearanceItem(
                submission_id=s.id, item_key=eo["key"], item_label=eo["label"],
                priority=eo["priority"], status="pending",
            ))
            added += 1
    db.session.commit()
    print(f"  E&O backfill: added {added} item(s) to existing submissions")

    # Backfill: ensure every existing submission carries the Master Recording License
    # item its template now requires (live_music, unscripted, social, podcast,
    # documentary, and the label-waiver review flow). Idempotent. UGC is excluded.
    master_defs = {}
    for tkey, items in CLEARANCE_TEMPLATES.items():
        for it in items:
            if it["key"].startswith("master_"):
                master_defs[tkey] = it
    added = 0
    for s in Submission.query.all():
        tkey = "live_music_label" if (s.platform and s.platform.platform_mode == "label_waiver") else s.project_type
        m = master_defs.get(tkey)
        if not m:
            continue  # e.g. UGC has no master recording item
        if not any(ci.item_key == m["key"] for ci in s.clearance_items):
            db.session.add(ClearanceItem(
                submission_id=s.id, item_key=m["key"], item_label=m["label"],
                priority=m["priority"], status="pending",
            ))
            added += 1
    db.session.commit()
    print(f"  Master Recording License backfill: added {added} item(s) to existing submissions")

    # Remove the misplaced Platform Distribution Agreement item from existing live_music
    # submissions (it's the platform deal, not a third-party clearance). Preserve any
    # that already have uploaded documents or reached cleared/waived, to avoid data loss.
    removed = skipped = 0
    for ci in ClearanceItem.query.filter_by(item_key="platform_agreement").all():
        if ci.documents or ci.status in ("cleared", "waived", "under_review"):
            skipped += 1
            continue
        db.session.delete(ci)
        removed += 1
    db.session.commit()
    print(f"  platform_agreement cleanup: removed {removed}, preserved {skipped} (had docs/were completed)")
    # Create new tables (templates, deal_terms_board, festival_artists) — cross-DB safe.
    try:
        db.create_all()
        print("  templates + deal_terms_board + festival_artists tables OK")
    except Exception as exc:
        print(f"  create_all: {exc}")

    # Enable the 'festival' project type on distributor platforms so promoters can pick
    # it at intake (label_waiver platforms stay live-music-only). Idempotent.
    fest_enabled = 0
    for p in Platform.query.filter(Platform.platform_mode != "label_waiver").all():
        types = p.accepted_types_list
        if "festival" not in types:
            idx = types.index("live_music") + 1 if "live_music" in types else len(types)
            types.insert(idx, "festival")
            p.accepted_types = ",".join(types)
            fest_enabled += 1
    db.session.commit()
    print(f"  festival project type enabled on {fest_enabled} distributor platform(s)")
    n = seed_templates()
    print(f"  templates seeded/updated: {n}")
    print("Migration complete.")


def seed_templates():
    """Load the firm-approved agreement templates (folded in from PLB) into the DB.
    Idempotent — inserts missing doc_types, refreshes content on existing ones."""
    try:
        from entertainment_templates import ENTERTAINMENT_TEMPLATES
    except Exception as exc:
        print(f"  seed_templates: could not import templates ({exc})")
        return 0
    count = 0
    for t in ENTERTAINMENT_TEMPLATES:
        row = Template.query.filter_by(doc_type=t["doc_type"]).first()
        if row is None:
            row = Template(doc_type=t["doc_type"])
            db.session.add(row)
        row.name        = t.get("name", t["doc_type"])
        row.description = t.get("description", "")
        row.content     = t.get("content", "")
        row.is_active   = True
        count += 1
    db.session.commit()
    return count


@app.cli.command("seed-templates")
def seed_templates_cmd():
    """Seed/refresh the firm-approved agreement template library. Safe to re-run."""
    n = seed_templates()
    print(f"Seeded/updated {n} templates.")


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
                    continue_on_truncation=True,
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


def _ensure_foldin_schema():
    """On boot, make sure the PLB fold-in tables exist and templates are seeded.
    Idempotent and safe on both SQLite and Postgres — create_all() only creates
    missing tables and never alters existing ones. Guarded so a transient DB error
    at startup never takes the app down (manual `flask migrate-db` remains the path
    for column changes on existing tables)."""
    try:
        with app.app_context():
            db.create_all()
            seed_templates()
    except Exception as exc:
        print(f"[startup] fold-in schema check skipped: {exc}")


_ensure_foldin_schema()


# Start the in-process release-reminder scheduler (replaces the external Render cron).
# Daemon thread; the 60s startup delay means short-lived CLI commands exit before the
# first sweep, so this never races migrations. Disable with ENABLE_REMINDER_SCHEDULER=0.
_reminder_thread_started = False

def _start_reminder_scheduler():
    global _reminder_thread_started
    if _reminder_thread_started or os.getenv("ENABLE_REMINDER_SCHEDULER", "1") != "1":
        return
    _reminder_thread_started = True
    threading.Thread(target=_release_reminder_scheduler, daemon=True).start()

_start_reminder_scheduler()


if __name__ == "__main__":
    app.run(debug=True, port=5002)
