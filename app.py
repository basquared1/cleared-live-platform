import os
import json
import hmac
import hashlib
import threading
from datetime import datetime, timedelta
from functools import wraps

import base64
import anthropic as _anthropic
import requests as http_requests
from dotenv import load_dotenv
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
    WebhookDelivery, PlatformUser, AdminUser,
    CLEARANCE_TEMPLATES, PRICING_TIERS, PROJECT_TYPE_LABELS,
    TERRITORY_LABELS, INTENDED_USE_OPTIONS,
)

load_dotenv()

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

def _ai_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    return _anthropic.Anthropic(api_key=key) if key else None


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
        f"Submitter: {sub.submitter_name} ({sub.submitter_company or 'N/A'})"
    )


def generate_draft(sub, item):
    client = _ai_client()
    if not client:
        return None
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": (
            f"You are a senior business affairs attorney specializing in entertainment clearances for streaming platforms.\n\n"
            f"Generate a professional {item.item_label} for:\n{_sub_context(sub)}\n\n"
            f"Structure your response as:\n"
            f"## DEAL POINTS\n- [4–6 key terms, specific to this project and rights type]\n\n"
            f"## DRAFT AGREEMENT\n[200–350 word professional draft. Use [RIGHTS HOLDER] and [PLATFORM] as party placeholders. "
            f"Include grant of rights, territory, term, compensation basis, representations & warranties, and signature blocks. "
            f"Be specific to the project details above.]"
        )}],
    )
    return msg.content[0].text


def generate_outreach(sub, item):
    client = _ai_client()
    if not client:
        return None
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": (
            f"You are a business affairs professional at {sub.platform.name}.\n\n"
            f"Write a professional clearance outreach email requesting a {item.item_label} for:\n{_sub_context(sub)}\n\n"
            f"Write 175–225 words. Start with 'Dear [Rights Holder],'. Do NOT include a subject line. "
            f"State exactly what rights are being requested, for which project and platform, reference event details, "
            f"request a response within 5 business days, and close professionally from the {sub.platform.name} Business Affairs team."
        )}],
    )
    return msg.content[0].text


def send_to_docusign(sub, item):
    account_id = os.getenv("DOCUSIGN_ACCOUNT_ID")
    token      = os.getenv("DOCUSIGN_ACCESS_TOKEN")
    base_url   = os.getenv("DOCUSIGN_BASE_URL", "https://demo.docusign.net/restapi")
    if not account_id or not token:
        return None, "DocuSign not configured — set DOCUSIGN_ACCOUNT_ID and DOCUSIGN_ACCESS_TOKEN in Render environment."

    draft = item.ai_draft or f"[AI draft pending for {item.item_label}]"
    html_doc = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:760px;margin:2rem auto;padding:1rem;">
<h2 style="color:#1a3a5c;">{item.item_label}</h2>
<table style="width:100%;border-collapse:collapse;margin-bottom:1.5rem;font-size:.9rem;">
<tr><td style="padding:4px 8px;color:#666;width:160px;">Project</td><td style="padding:4px 8px;font-weight:bold;">{sub.title}</td></tr>
<tr><td style="padding:4px 8px;color:#666;">Platform</td><td style="padding:4px 8px;">{sub.platform.name}</td></tr>
<tr><td style="padding:4px 8px;color:#666;">Artist</td><td style="padding:4px 8px;">{sub.artist_name or 'N/A'}</td></tr>
<tr><td style="padding:4px 8px;color:#666;">Territory</td><td style="padding:4px 8px;">{sub.territory_label}</td></tr>
<tr><td style="padding:4px 8px;color:#666;">Intended Use</td><td style="padding:4px 8px;">{', '.join(sub.intended_use_list) if sub.intended_use_list else 'Streaming'}</td></tr>
</table>
<hr style="margin:1.5rem 0;">
<div style="white-space:pre-wrap;font-family:Georgia,serif;line-height:1.7;font-size:.95rem;">{draft}</div>
<div style="margin-top:4rem;">
<p style="font-weight:bold;">AGREED AND ACCEPTED:</p>
<br>
<p>Submitter Signature: <span style="font-size:1.1em;">/s1e1/</span></p>
<p>Date: /d1e1/</p>
<br>
<p>Authorized Signatory: <span style="font-size:1.1em;">/s2e1/</span></p>
<p>Date: /d2e1/</p>
</div></body></html>"""

    doc_b64 = base64.b64encode(html_doc.encode()).decode()
    envelope = {
        "emailSubject": f"Please sign: {item.item_label} — {sub.title} ({sub.platform.name})",
        "documents": [{"documentBase64": doc_b64, "name": f"{item.item_label}.html",
                        "fileExtension": "html", "documentId": "1"}],
        "recipients": {"signers": [{
            "email": sub.submitter_email,
            "name": sub.submitter_name,
            "recipientId": "1",
            "routingOrder": "1",
            "tabs": {
                "signHereTabs": [{"anchorString": "/s1e1/", "anchorUnits": "pixels"}],
                "dateSignedTabs": [{"anchorString": "/d1e1/", "anchorUnits": "pixels"}],
            }
        }]},
        "status": "sent",
    }
    resp = http_requests.post(
        f"{base_url}/v2.1/accounts/{account_id}/envelopes",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=envelope, timeout=15,
    )
    if resp.status_code == 201:
        return resp.json().get("envelopeId"), None
    return None, f"DocuSign API error {resp.status_code}: {resp.text[:300]}"


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

        for item_def in CLEARANCE_TEMPLATES.get(ptype, CLEARANCE_TEMPLATES["live_music"]):
            db.session.add(ClearanceItem(
                submission_id = sub.id,
                item_key      = item_def["key"],
                item_label    = item_def["label"],
                priority      = item_def["priority"],
                status        = "pending",
            ))

        db.session.commit()
        return redirect(url_for("submit_confirm", token=sub.token))

    return render_template(
        "submit.html",
        platform=platform,
        pricing_tiers=PRICING_TIERS,
        project_type_labels=PROJECT_TYPE_LABELS,
        territory_labels=TERRITORY_LABELS,
        intended_use_options=INTENDED_USE_OPTIONS,
        clearance_templates=CLEARANCE_TEMPLATES,
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
    return render_template("track.html", sub=sub)


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
        item.status     = new_status
        item.notes      = request.form.get("notes", item.notes or "").strip() or item.notes
        item.party_name = request.form.get("party_name", item.party_name or "").strip() or item.party_name
        if new_status in ("cleared", "waived"):
            item.cleared_at = datetime.utcnow()
            item.cleared_by = user.username
        db.session.commit()

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


@app.route("/platform/project/<int:sub_id>/notes", methods=["POST"])
@require_platform
def platform_save_notes(sub_id):
    user = current_platform_user()
    sub  = Submission.query.get_or_404(sub_id)
    if sub.platform_id != user.platform_id:
        abort(403)
    sub.ba_notes   = request.form.get("ba_notes", "").strip()
    sub.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Notes saved.", "success")
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
    if not _ai_client():
        flash("ANTHROPIC_API_KEY not configured in Render environment.", "danger")
        return redirect(url_for("platform_project", sub_id=sub_id))
    for item in sub.clearance_items:
        item.ai_draft = generate_draft(sub, item)
    db.session.commit()
    flash(f"AI drafts generated for all {len(sub.clearance_items)} clearance items.", "success")
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
        db.session.commit()
        flash(f"DocuSign envelope sent for {item.item_label}. ID: {envelope_id[:12]}…", "success")
    else:
        flash(f"DocuSign: {error}", "danger")
    return redirect(url_for("platform_project", sub_id=sub_id))


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
        ("Netflix", "netflix",     "Netflix",  "#E50914", "standard"),
        ("YouTube", "youtube",     "YouTube",  "#FF0000", "standard"),
        ("HBO",     "hbo",         "HBO",      "#1E1E1E", "standard"),
        ("UMG",     "umg",         "UMG",      "#003087", "enterprise"),
    ]
    for name, slug, logo, color, tier in demos:
        if not Platform.query.filter_by(slug=slug).first():
            db.session.add(Platform(
                name=name, slug=slug, logo_text=logo,
                tier=tier, primary_color=color,
                accepted_types="live_music,documentary,unscripted,social,ugc",
            ))
    db.session.commit()
    print("Demo platforms created: Netflix, YouTube, HBO, UMG")
    print("\nDatabase ready.")


@app.cli.command("migrate-db")
def migrate_db_cmd():
    """Add AI + DocuSign columns to clearance_items (safe to re-run)."""
    cols = [
        ("ai_draft",             "TEXT"),
        ("ai_deal_points",       "TEXT"),
        ("ai_outreach_body",     "TEXT"),
        ("ai_outreach_sent_at",  "TIMESTAMP"),
        ("docusign_envelope_id", "VARCHAR(100)"),
        ("docusign_status",      "VARCHAR(50)"),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in cols:
            try:
                conn.execute(sa_text(
                    f"ALTER TABLE clearance_items ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                conn.commit()
                print(f"  + {col_name}")
            except Exception as exc:
                conn.rollback()
                print(f"  ~ {col_name}: {exc}")
    print("Migration complete.")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
