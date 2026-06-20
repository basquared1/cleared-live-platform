from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import secrets

db = SQLAlchemy()


def _gen_token():
    return secrets.token_urlsafe(24)


def _gen_api_key():
    return "clp_" + secrets.token_urlsafe(32)


PROJECT_TYPE_LABELS = {
    "live_music":  "Live Music / Concert",
    "documentary": "Documentary / Film",
    "unscripted":  "Unscripted / Reality TV",
    "social":      "Social Media Campaign",
    "ugc":         "User-Generated Content",
}

CLEARANCE_TEMPLATES = {
    "live_music": [
        {"key": "promoter_consent",   "label": "Promoter Filming Rights Consent",  "priority": 1},
        {"key": "label_waiver",       "label": "Label Waiver",                     "priority": 2},
        {"key": "publishing",         "label": "Publishing Clearance",             "priority": 3},
        {"key": "performer_release",  "label": "Performer Releases",               "priority": 4},
        {"key": "venue_license",      "label": "Venue Filming License",            "priority": 5},
        {"key": "crowd_release",      "label": "Crowd / Audience Release",         "priority": 6},
        {"key": "platform_agreement", "label": "Platform Distribution Agreement",  "priority": 7},
    ],
    "documentary": [
        {"key": "sync_license",        "label": "Music Sync License(s)",           "priority": 1},
        {"key": "master_license",      "label": "Master Recording License(s)",     "priority": 2},
        {"key": "footage_rights",      "label": "Archival Footage Rights",         "priority": 3},
        {"key": "photo_rights",        "label": "Photo / Still Image Rights",      "priority": 4},
        {"key": "interview_releases",  "label": "Interview Subject Releases",      "priority": 5},
        {"key": "location_releases",   "label": "Location Releases",               "priority": 6},
        {"key": "trademark_clearance", "label": "Brand / Trademark Clearance",    "priority": 7},
        {"key": "eo_documentation",    "label": "E&O Insurance Documentation",     "priority": 8},
    ],
    "unscripted": [
        {"key": "music_clearance",     "label": "Music Clearance",                          "priority": 1},
        {"key": "talent_releases",     "label": "Talent / Participant Releases",            "priority": 2},
        {"key": "location_releases",   "label": "Location Releases",                        "priority": 3},
        {"key": "appearance_releases", "label": "Non-Talent Appearance Releases",           "priority": 4},
        {"key": "brand_clearance",     "label": "Brand / Product Clearance",               "priority": 5},
        {"key": "social_clearance",    "label": "Participant Social Media Clearance",       "priority": 6},
        {"key": "eo_documentation",    "label": "E&O Insurance Documentation",              "priority": 7},
    ],
    "social": [
        {"key": "music_license",      "label": "Music License",              "priority": 1},
        {"key": "performer_consent",  "label": "Performer / Talent Consent", "priority": 2},
        {"key": "ugc_clearance",      "label": "UGC Rights Clearance",       "priority": 3},
        {"key": "brand_clearance",    "label": "Brand / Trademark Clearance","priority": 4},
    ],
    "ugc": [
        {"key": "content_license",    "label": "Content License",           "priority": 1},
        {"key": "music_license",      "label": "Music License",             "priority": 2},
        {"key": "appearance_consent", "label": "Appearance Consent",        "priority": 3},
        {"key": "platform_terms",     "label": "Platform Terms Compliance", "priority": 4},
    ],
}

PRICING_TIERS = {
    "basic":    {"label": "Basic",    "price": 500,  "desc": "Up to 5 clearance items. Single event or content piece."},
    "standard": {"label": "Standard", "price": 1000, "desc": "6–15 clearance items. Live music or documentary."},
    "complex":  {"label": "Complex",  "price": 2000, "desc": "16+ items. Major label, multi-territory, or multi-format."},
}

TERRITORY_LABELS = {
    "us": "United States", "north_america": "North America",
    "worldwide": "Worldwide", "europe": "Europe",
}

INTENDED_USE_OPTIONS = [
    ("streaming", "Streaming"),
    ("broadcast", "Broadcast / TV"),
    ("theatrical", "Theatrical"),
    ("social", "Social Media"),
    ("home_video", "Home Video / VOD"),
    ("promotional", "Promotional / Marketing"),
    ("all", "All Media"),
]


class Platform(db.Model):
    __tablename__ = "platforms"
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(100), unique=True, nullable=False)
    primary_color   = db.Column(db.String(20), default="#0d3b6e")
    logo_text       = db.Column(db.String(100))            # e.g. "Amazon" for text logo
    ba_contact_name = db.Column(db.String(200))
    ba_contact_email= db.Column(db.String(200))
    api_key         = db.Column(db.String(100), default=_gen_api_key, unique=True)
    webhook_url     = db.Column(db.String(500))
    webhook_secret  = db.Column(db.String(100), default=lambda: secrets.token_urlsafe(20))
    tier            = db.Column(db.String(20), default="standard")  # trial | standard | enterprise
    is_active       = db.Column(db.Boolean, default=True)
    accepted_types  = db.Column(db.String(300), default="live_music,documentary,unscripted,social,ugc")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    submissions = db.relationship("Submission", backref="platform", lazy="dynamic")
    users       = db.relationship("PlatformUser", backref="platform", lazy=True)
    deliveries  = db.relationship("WebhookDelivery", backref="platform", lazy=True)

    @property
    def accepted_types_list(self):
        return [t.strip() for t in (self.accepted_types or "").split(",") if t.strip()]

    @property
    def total_count(self):
        return self.submissions.count()

    @property
    def cleared_count(self):
        return self.submissions.filter_by(status="cleared").count()

    @property
    def pending_count(self):
        return self.submissions.filter_by(status="submitted").count()

    @property
    def tier_label(self):
        return {"trial": "Trial", "standard": "Standard", "enterprise": "Enterprise"}.get(self.tier, self.tier.title())


class Submission(db.Model):
    __tablename__ = "submissions"
    id                  = db.Column(db.Integer, primary_key=True)
    token               = db.Column(db.String(40), unique=True, nullable=False, default=_gen_token)
    platform_id         = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)

    # Project details
    project_type        = db.Column(db.String(30), nullable=False, default="live_music")
    title               = db.Column(db.String(300), nullable=False)
    artist_name         = db.Column(db.String(200))
    event_name          = db.Column(db.String(200))
    venue               = db.Column(db.String(200))
    event_date          = db.Column(db.String(50))
    setlist             = db.Column(db.Text)
    label               = db.Column(db.String(200))
    publisher           = db.Column(db.String(200))
    production_company  = db.Column(db.String(200))
    director            = db.Column(db.String(200))
    intended_use        = db.Column(db.String(300))      # comma-separated
    territory           = db.Column(db.String(50), default="us")
    notes               = db.Column(db.Text)

    # Submitter
    submitter_name      = db.Column(db.String(200), nullable=False)
    submitter_company   = db.Column(db.String(200))
    submitter_email     = db.Column(db.String(200), nullable=False)
    submitter_phone     = db.Column(db.String(50))

    # Pricing
    pricing_tier        = db.Column(db.String(20), default="standard")
    price_cents         = db.Column(db.Integer, default=100000)
    payment_status      = db.Column(db.String(20), default="pending")  # pending | invoiced | paid | waived

    # Status
    status              = db.Column(db.String(30), default="submitted")
    # submitted | in_review | in_clearance | cleared | rejected
    ba_notes            = db.Column(db.Text)    # internal only

    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cleared_at          = db.Column(db.DateTime)

    clearance_items = db.relationship(
        "ClearanceItem", backref="submission", lazy=True,
        order_by="ClearanceItem.priority", cascade="all, delete-orphan"
    )
    documents = db.relationship(
        "SubmissionDocument", backref="submission", lazy=True, cascade="all, delete-orphan"
    )
    deliveries = db.relationship("WebhookDelivery", backref="submission", lazy=True)

    @property
    def project_type_label(self):
        return PROJECT_TYPE_LABELS.get(self.project_type, self.project_type.replace("_", " ").title())

    @property
    def status_label(self):
        return {
            "submitted":    "Submitted",
            "in_review":    "Under Review",
            "in_clearance": "Clearance In Progress",
            "cleared":      "Fully Cleared",
            "rejected":     "Rejected",
        }.get(self.status, self.status.title())

    @property
    def status_color(self):
        return {
            "submitted":    "secondary",
            "in_review":    "info",
            "in_clearance": "warning",
            "cleared":      "success",
            "rejected":     "danger",
        }.get(self.status, "secondary")

    @property
    def progress_pct(self):
        total = len(self.clearance_items)
        if total == 0:
            return 0
        done = sum(1 for i in self.clearance_items if i.status in ("cleared", "waived", "n_a"))
        return round(done / total * 100)

    @property
    def is_fully_cleared(self):
        return self.clearance_items and all(
            i.status in ("cleared", "waived", "n_a") for i in self.clearance_items
        )

    @property
    def blocking_items(self):
        return [i for i in self.clearance_items if i.status == "pending"]

    @property
    def setlist_list(self):
        return [s.strip() for s in (self.setlist or "").splitlines() if s.strip()]

    @property
    def intended_use_list(self):
        return [u.strip() for u in (self.intended_use or "").split(",") if u.strip()]

    @property
    def territory_label(self):
        return TERRITORY_LABELS.get(self.territory, self.territory)

    @property
    def price_display(self):
        return f"${self.price_cents // 100:,}"

    @property
    def pricing_tier_info(self):
        return PRICING_TIERS.get(self.pricing_tier, PRICING_TIERS["standard"])

    def to_api_dict(self):
        return {
            "token": self.token,
            "title": self.title,
            "project_type": self.project_type,
            "status": self.status,
            "status_label": self.status_label,
            "progress_pct": self.progress_pct,
            "submitter_email": self.submitter_email,
            "cleared_at": self.cleared_at.isoformat() if self.cleared_at else None,
            "created_at": self.created_at.isoformat(),
            "clearance_items": [i.to_api_dict() for i in self.clearance_items],
        }


class ClearanceItem(db.Model):
    __tablename__ = "clearance_items"
    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    item_key      = db.Column(db.String(100), nullable=False)
    item_label    = db.Column(db.String(300), nullable=False)
    priority      = db.Column(db.Integer, default=99)
    status        = db.Column(db.String(30), default="pending")
    # pending | in_progress | cleared | waived | n_a
    party_name    = db.Column(db.String(200))
    assigned_to   = db.Column(db.String(200))
    notes         = db.Column(db.Text)
    cleared_at    = db.Column(db.DateTime)
    cleared_by    = db.Column(db.String(100))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship("SubmissionDocument", backref="clearance_item", lazy=True)

    @property
    def status_label(self):
        return {
            "pending":     "Pending",
            "in_progress": "In Progress",
            "cleared":     "Cleared",
            "waived":      "Waived",
            "n_a":         "N/A",
        }.get(self.status, self.status.title())

    @property
    def status_color(self):
        return {
            "pending":     "warning",
            "in_progress": "info",
            "cleared":     "success",
            "waived":      "secondary",
            "n_a":         "light",
        }.get(self.status, "secondary")

    @property
    def status_icon(self):
        return {
            "pending":     "bi-clock",
            "in_progress": "bi-arrow-repeat",
            "cleared":     "bi-check-circle-fill",
            "waived":      "bi-slash-circle",
            "n_a":         "bi-dash-circle",
        }.get(self.status, "bi-circle")

    @property
    def is_done(self):
        return self.status in ("cleared", "waived", "n_a")

    def to_api_dict(self):
        return {
            "key": self.item_key,
            "label": self.item_label,
            "status": self.status,
            "status_label": self.status_label,
            "party_name": self.party_name,
            "cleared_at": self.cleared_at.isoformat() if self.cleared_at else None,
        }


class SubmissionDocument(db.Model):
    __tablename__ = "submission_documents"
    id                = db.Column(db.Integer, primary_key=True)
    submission_id     = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    clearance_item_id = db.Column(db.Integer, db.ForeignKey("clearance_items.id"), nullable=True)
    title             = db.Column(db.String(300), nullable=False)
    doc_type          = db.Column(db.String(100), default="other")
    filename          = db.Column(db.String(300))
    file_data         = db.Column(db.LargeBinary)
    mimetype          = db.Column(db.String(100))
    notes             = db.Column(db.Text)
    uploaded_by       = db.Column(db.String(100))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"
    id              = db.Column(db.Integer, primary_key=True)
    platform_id     = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    submission_id   = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=True)
    event_type      = db.Column(db.String(50), nullable=False)
    payload         = db.Column(db.Text)
    response_status = db.Column(db.Integer)
    response_body   = db.Column(db.Text)
    success         = db.Column(db.Boolean)
    attempts        = db.Column(db.Integer, default=1)
    delivered_at    = db.Column(db.DateTime, default=datetime.utcnow)


class PlatformUser(db.Model):
    __tablename__ = "platform_users"
    id            = db.Column(db.Integer, primary_key=True)
    platform_id   = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(200))
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default="viewer")  # admin | viewer
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(200))
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
