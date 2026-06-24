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
    "festival":    "Festival / Multi-Artist Event",
    "documentary": "Documentary / Film",
    "unscripted":  "Unscripted / Reality TV",
    "podcast":     "Podcast / Audio",
    "social":      "Social Media Campaign",
    "ugc":         "User-Generated Content",
    # Production-legal intakes (folded in from Production Legal Binder) — these spin up
    # the full production-legal document package (crew, talent, releases, E&O, chain of title)
    # alongside rights clearance, so the platform is the system of record for the whole project.
    "feature_film": "Feature Film (Narrative)",
    "tv_series":    "TV / Streaming Series",
    "branded":      "Commercial / Branded Content",
}

CLEARANCE_TEMPLATES = {
    "live_music": [
        {"key": "promoter_consent",   "label": "Promoter Filming Rights Consent",  "priority": 1},
        {"key": "label_waiver",       "label": "Label Waiver",                     "priority": 2},
        {"key": "master_license",     "label": "Master Recording License(s)",      "priority": 3},
        {"key": "performer_release",  "label": "Performer Releases",               "priority": 4},
        {"key": "venue_license",      "label": "Venue Filming License",            "priority": 5},
        {"key": "crowd_release",      "label": "Crowd / Audience Release",         "priority": 6},
        {"key": "eo_documentation",   "label": "E&O Insurance Documentation",      "priority": 7},
    ],
    # Festival = event-level clearances only. Per-artist music/master/label clearance
    # fans out to each artist's own thread via the festival artist roster.
    "festival": [
        {"key": "promoter_consent",  "label": "Promoter Filming Rights Consent", "priority": 1},
        {"key": "venue_license",     "label": "Venue Filming License",           "priority": 2},
        {"key": "crowd_release",     "label": "Crowd / Audience Release",        "priority": 3},
        {"key": "eo_documentation",  "label": "E&O Insurance Documentation",     "priority": 4},
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
        {"key": "master_license",      "label": "Master Recording License(s)",              "priority": 2},
        {"key": "talent_releases",     "label": "Talent / Participant Releases",            "priority": 3},
        {"key": "location_releases",   "label": "Location Releases",                        "priority": 4},
        {"key": "appearance_releases", "label": "Non-Talent Appearance Releases",           "priority": 5},
        {"key": "brand_clearance",     "label": "Brand / Product Clearance",               "priority": 6},
        {"key": "social_clearance",    "label": "Participant Social Media Clearance",       "priority": 7},
        {"key": "eo_documentation",    "label": "E&O Insurance Documentation",              "priority": 8},
    ],
    "social": [
        {"key": "music_license",      "label": "Music License",              "priority": 1},
        {"key": "master_license",     "label": "Master Recording License(s)","priority": 2},
        {"key": "performer_consent",  "label": "Performer / Talent Consent", "priority": 3},
        {"key": "ugc_clearance",      "label": "UGC Rights Clearance",       "priority": 4},
        {"key": "brand_clearance",    "label": "Brand / Trademark Clearance","priority": 5},
        {"key": "eo_documentation",   "label": "E&O Insurance Documentation","priority": 6},
    ],
    "podcast": [
        {"key": "guest_release",       "label": "Guest / Interview Release",          "priority": 1},
        {"key": "music_license",       "label": "Background Music License",           "priority": 2},
        {"key": "master_license",      "label": "Master Recording License(s)",        "priority": 3},
        {"key": "cohost_agreement",    "label": "Co-Host Agreement",                  "priority": 4},
        {"key": "sponsor_agreement",   "label": "Sponsor / Ad Read Agreement",        "priority": 5},
        {"key": "sample_clearance",    "label": "Audio Sample / Clip Clearance",      "priority": 6},
        {"key": "distributor_license", "label": "Platform Distribution License",      "priority": 7},
        {"key": "eo_documentation",    "label": "E&O Insurance Documentation",        "priority": 8},
    ],
    # Label waiver mode: label reviews submitter's completed clearances, then issues conditional waiver
    "live_music_label": [
        {"key": "promoter_consent_review",   "label": "Promoter Consent — Verify & Review",          "priority": 1},
        {"key": "publishing_review",         "label": "Publishing Clearance — Verify & Review",       "priority": 2},
        {"key": "master_license_review",     "label": "Master Recording License — Verify & Review",   "priority": 3},
        {"key": "performer_releases_review", "label": "Performer Releases — Verify & Review",         "priority": 4},
        {"key": "venue_license_review",      "label": "Venue Filming License — Verify & Review",      "priority": 5},
        {"key": "crowd_release_review",      "label": "Crowd / Audience Release — Verify & Review",   "priority": 6},
        {"key": "eo_documentation_review",   "label": "E&O Insurance — Verify & Review",              "priority": 7},
        {"key": "conditional_label_waiver",  "label": "Conditional Label Waiver — Issue",             "priority": 8},
    ],
    "ugc": [
        {"key": "content_license",    "label": "Content License",           "priority": 1},
        {"key": "music_license",      "label": "Music License",             "priority": 2},
        {"key": "appearance_consent", "label": "Appearance Consent",        "priority": 3},
        {"key": "platform_terms",     "label": "Platform Terms Compliance", "priority": 4},
    ],
    # ── Production-legal packages folded in from Production Legal Binder (PLB) ──
    # Each item is an agreement the platform's system of record can AI-draft, route for
    # signature (DocuSign or on-site), and track to delivery — combining production paperwork
    # with rights clearance in one workspace.
    "feature_film": [
        {"key": "option_purchase_agreement", "label": "Option / Purchase Agreement",        "priority": 1},
        {"key": "writer_agreement",          "label": "Writer Agreement (WGA-compliant)",   "priority": 2},
        {"key": "director_agreement",        "label": "Director Agreement (DGA-compliant)",  "priority": 3},
        {"key": "talent_agreement",          "label": "Talent Agreements",                   "priority": 4},
        {"key": "crew_deal_memo",            "label": "Crew Deal Memos",                     "priority": 5},
        {"key": "location_release",          "label": "Location Releases",                   "priority": 6},
        {"key": "appearance_release",        "label": "Appearance / Extra Releases",         "priority": 7},
        {"key": "music_clearance",           "label": "Music Clearance (Sync + Master)",     "priority": 8},
        {"key": "chain_of_title",            "label": "Chain of Title",                      "priority": 9},
        {"key": "eo_schedule",               "label": "E&O Insurance Schedule",              "priority": 10},
    ],
    "tv_series": [
        {"key": "series_talent_agreement", "label": "Series Talent Agreements",          "priority": 1},
        {"key": "ep_agreement",            "label": "Executive Producer Agreements",      "priority": 2},
        {"key": "writer_agreement",        "label": "Writer Agreements (WGA-compliant)",  "priority": 3},
        {"key": "director_agreement",      "label": "Director Agreements (DGA-compliant)", "priority": 4},
        {"key": "crew_deal_memo",          "label": "Crew Deal Memos",                    "priority": 5},
        {"key": "location_release",        "label": "Location Releases",                  "priority": 6},
        {"key": "appearance_release",      "label": "Appearance / Guest Releases",        "priority": 7},
        {"key": "music_clearance",         "label": "Music Clearance (Sync + Master)",    "priority": 8},
        {"key": "chain_of_title",          "label": "Chain of Title",                     "priority": 9},
        {"key": "eo_schedule",             "label": "E&O Insurance Schedule",             "priority": 10},
    ],
    "branded": [
        {"key": "crew_deal_memo",     "label": "Crew Deal Memos",              "priority": 1},
        {"key": "talent_agreement",   "label": "Talent / Performer Agreements", "priority": 2},
        {"key": "appearance_release", "label": "Appearance Releases",          "priority": 3},
        {"key": "location_release",   "label": "Location Releases",            "priority": 4},
        {"key": "music_license",      "label": "Music License",                "priority": 5},
        {"key": "brand_clearance",    "label": "Brand / Trademark Clearance",  "priority": 6},
        {"key": "eo_documentation",   "label": "E&O Insurance Documentation",  "priority": 7},
    ],
}

# Clearance item keys that belong to the "Music Clearance" group on the submitter
# workspace (sync, master, and general music items + the label-waiver review steps).
# Single source of truth — used for grouping, music progress, and delegated access.
MUSIC_ITEM_KEYS = {
    "sync_license", "master_license", "music_license",
    "music_clearance", "sample_clearance", "label_waiver",
    "publishing_review", "master_license_review",
}


def is_music_item(item_key):
    """True if a clearance item belongs to the Music Clearance group."""
    return (item_key or "") in MUSIC_ITEM_KEYS


PRICING_TIERS = {
    "basic":    {"label": "Basic",    "price": 500,  "desc": "Up to 5 clearance items. Single event or content piece."},
    "standard": {"label": "Standard", "price": 1000, "desc": "6–15 clearance items. Most film, series, and live content."},
    "complex":  {"label": "Complex",  "price": 2000, "desc": "16+ items. Multi-territory, multi-format, or complex rights stacks."},
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
    platform_mode   = db.Column(db.String(20), default="clearance")  # clearance | label_waiver
    is_active       = db.Column(db.Boolean, default=True)
    accepted_types         = db.Column(db.String(300), default="live_music,documentary,unscripted,social,ugc")
    created_at             = db.Column(db.DateTime, default=datetime.utcnow)

    # Form configuration — what the platform mandates on every submission
    form_territory           = db.Column(db.String(50))
    form_territory_locked    = db.Column(db.Boolean, default=False)
    form_intended_use        = db.Column(db.String(300))  # comma-separated
    form_intended_use_locked = db.Column(db.Boolean, default=False)
    # Negotiation positions — JSON array of {rank, label, territory, uses, term, notes}
    negotiation_positions_json = db.Column(db.Text)

    submissions = db.relationship("Submission", backref="platform", lazy="dynamic")
    users       = db.relationship("PlatformUser", backref="platform", lazy=True)
    deliveries  = db.relationship("WebhookDelivery", backref="platform", lazy=True)

    @property
    def accepted_types_list(self):
        return [t.strip() for t in (self.accepted_types or "").split(",") if t.strip()]

    @property
    def form_intended_use_list(self):
        return [u.strip() for u in (self.form_intended_use or "").split(",") if u.strip()]

    @property
    def negotiation_positions(self):
        import json
        try:
            return json.loads(self.negotiation_positions_json or "[]")
        except Exception:
            return []

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
    songs_json          = db.Column(db.Text)    # JSON list of song dicts for live_music
    deal_terms_json     = db.Column(db.Text)    # JSON dict of bulk deal terms
    publisher_clearances_json = db.Column(db.Text)  # JSON dict of publisher clearance groups

    # Delegated music-contact access: a separate scoped token that grants a music
    # supervisor access to ONLY the Music Clearance section of this submission.
    music_access_token  = db.Column(db.String(40), unique=True)
    music_contact_name  = db.Column(db.String(200))
    music_contact_email = db.Column(db.String(200))

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
    def songs(self):
        import json
        if not self.songs_json:
            return []
        try:
            raw = json.loads(self.songs_json)
        except Exception:
            return []
        # Backward compat: convert old single-writer format to writers array
        converted = []
        for s in raw:
            if "writer" in s and "writers" not in s:
                s = dict(s)
                writer_entry = {
                    "name": s.pop("writer", "") or "",
                    "publisher": s.pop("publisher", "") or "",
                    "pro": s.pop("pro", "") or "",
                    "split_pct": s.pop("split_pct", 100),
                }
                s["writers"] = [writer_entry] if writer_entry["name"] else []
            if "deal_terms" not in s:
                s["deal_terms"] = {
                    "fee": None, "fee_type": None, "territory": None,
                    "term": None, "mfn": False, "cue_sheet_days": 30,
                    "media_rights": [], "notes": ""
                }
            converted.append(s)
        return converted

    def songs_save(self, songs_list):
        import json
        self.songs_json = json.dumps(songs_list)

    @property
    def deal_terms(self):
        import json
        try:
            return json.loads(self.deal_terms_json or "{}")
        except Exception:
            return {}

    def deal_terms_save(self, terms_dict):
        import json
        self.deal_terms_json = json.dumps(terms_dict)

    @property
    def publisher_clearances(self):
        import json as _j
        try:
            return _j.loads(self.publisher_clearances_json or '{}')
        except:
            return {}

    def publisher_clearances_save(self, data):
        import json as _j
        self.publisher_clearances_json = _j.dumps(data)

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
    def music_clearance_counts(self):
        """(done, total) for the Music Clearance group: music clearance items plus
        publisher clearance groups (sync per publisher). Used for music-only progress."""
        items = [i for i in self.clearance_items if is_music_item(i.item_key)]
        done = sum(1 for i in items if i.status in ("cleared", "waived", "n_a"))
        total = len(items)
        for grp in (self.publisher_clearances or {}).values():
            total += 1
            if grp.get("status") == "cleared":
                done += 1
        return done, total

    @property
    def music_progress_pct(self):
        done, total = self.music_clearance_counts
        return round(done / total * 100) if total else 0

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
    # pending | in_progress | under_review | cleared | waived | n_a
    party_company = db.Column(db.String(200))
    party_name    = db.Column(db.String(200))
    party_email   = db.Column(db.String(200))
    assigned_to   = db.Column(db.String(200))
    notes         = db.Column(db.Text)
    cleared_at    = db.Column(db.DateTime)
    cleared_by    = db.Column(db.String(100))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    ai_draft             = db.Column(db.Text)
    ai_deal_points       = db.Column(db.Text)
    ai_outreach_body     = db.Column(db.Text)
    ai_outreach_sent_at  = db.Column(db.DateTime)
    docusign_envelope_id = db.Column(db.String(100))
    docusign_status      = db.Column(db.String(50))

    rh_response       = db.Column(db.String(20))   # accepted | counter | declined
    rh_response_notes = db.Column(db.Text)
    rh_response_at    = db.Column(db.DateTime)

    # AI negotiation agent
    reply_token            = db.Column(db.String(60))   # per-item inbound Reply-To token
    neg_state              = db.Column(db.String(30))
    # awaiting_reply | analyzing | needs_approval | signature_sent | agreed | stalled
    negotiation_log_json   = db.Column(db.Text)   # JSON list of thread turns
    ai_recommendation_json = db.Column(db.Text)   # JSON dict — AI's latest move

    deal_terms_json = db.Column(db.Text)
    deal_points_json = db.Column(db.Text)   # JSON list — structured deal points (our/their/agreed grid)

    documents = db.relationship("SubmissionDocument", backref="clearance_item", lazy=True)

    @property
    def deal_terms(self):
        import json
        return json.loads(self.deal_terms_json or "{}")

    def deal_terms_save(self, terms_dict):
        import json
        self.deal_terms_json = json.dumps(terms_dict)

    @property
    def deal_points(self):
        """Structured negotiable points: list of {label, our, their, agreed, status}."""
        import json
        try:
            return json.loads(self.deal_points_json or "[]")
        except Exception:
            return []

    def deal_points_save(self, points):
        import json
        self.deal_points_json = json.dumps(points)

    @property
    def negotiation_log(self):
        import json
        try:
            return json.loads(self.negotiation_log_json or "[]")
        except Exception:
            return []

    def negotiation_log_add(self, entry):
        import json
        log = self.negotiation_log
        log.append(entry)
        self.negotiation_log_json = json.dumps(log)

    @property
    def ai_recommendation(self):
        import json
        try:
            return json.loads(self.ai_recommendation_json or "{}")
        except Exception:
            return {}

    def ai_recommendation_save(self, data):
        import json
        self.ai_recommendation_json = json.dumps(data) if data else None

    @property
    def status_label(self):
        return {
            "pending":          "Pending",
            "in_progress":      "In Progress",
            "under_review":     "Under Review",
            "cleared":          "Cleared",
            "waived":           "Waived",
            "n_a":              "N/A",
            "docusign_pending": "DocuSign Pending",
        }.get(self.status, self.status.title())

    @property
    def status_color(self):
        return {
            "pending":          "warning",
            "in_progress":      "info",
            "under_review":     "primary",
            "cleared":          "success",
            "waived":           "secondary",
            "n_a":              "light",
            "docusign_pending": "dark",
        }.get(self.status, "secondary")

    @property
    def status_icon(self):
        return {
            "pending":          "bi-clock",
            "in_progress":      "bi-arrow-repeat",
            "under_review":     "bi-hourglass-split",
            "cleared":          "bi-check-circle-fill",
            "waived":           "bi-slash-circle",
            "n_a":              "bi-dash-circle",
            "docusign_pending": "bi-pen",
        }.get(self.status, "bi-circle")

    @property
    def is_done(self):
        return self.status in ("cleared", "waived", "n_a")

    # ----- Agreement lifecycle (derived from existing fields — no schema change) -----
    # not_started → draft → negotiating → out_for_signature → signed_pending_copy → executed
    # Doc types that count as a fully counter-signed agreement on file.
    EXECUTED_DOC_TYPES = (
        "signed_document", "onsite_signature", "executed",
        "countersigned", "fully_executed",
    )

    @property
    def executed_documents(self):
        return [d for d in self.documents
                if (d.doc_type or "") in self.EXECUTED_DOC_TYPES]

    @property
    def agreement_stage(self):
        """Where this item's agreement sits in its lifecycle, inferred from
        docusign_status, neg_state, status, and attached documents.

        STRICT execution rule: an agreement is 'executed' ONLY when a
        counter-signed document is actually on file. If the system believes
        signing happened (BA cleared it, DocuSign reports completed, or the
        negotiation agreed) but no executed copy is stored, it is flagged
        'signed_pending_copy' so the missing final document is visible."""
        if self.status == "n_a":
            return "n_a"
        if self.status == "waived":
            return "waived"
        # Fully executed — a counter-signed document must be on file.
        if self.executed_documents:
            return "executed"
        ds = (self.docusign_status or "").lower()
        ns = (self.neg_state or "")
        # Signing is believed complete, but the executed copy isn't on file yet.
        if (self.status == "cleared"
                or ds in ("completed", "signed", "signed_onsite")
                or ns == "agreed"):
            return "signed_pending_copy"
        # Out for signature
        if (ds in ("sent", "delivered")
                or self.status == "docusign_pending"
                or ns == "signature_sent"):
            return "out_for_signature"
        # Negotiating — outreach went out, or a thread exists
        if (ns in ("awaiting_reply", "analyzing", "needs_approval", "stalled")
                or self.ai_outreach_sent_at
                or self.negotiation_log):
            return "negotiating"
        # Draft generated / work started
        if self.ai_draft or self.status == "in_progress":
            return "draft"
        return "not_started"

    @property
    def agreement_stage_label(self):
        return {
            "not_started":         "Not Started",
            "draft":               "Draft",
            "negotiating":         "Negotiating",
            "out_for_signature":   "Out for Signature",
            "signed_pending_copy": "Signed — Awaiting Copy",
            "executed":            "Fully Executed",
            "waived":              "Waived",
            "n_a":                 "N/A",
        }.get(self.agreement_stage, self.agreement_stage)

    @property
    def agreement_stage_color(self):
        return {
            "not_started":         "light",
            "draft":               "secondary",
            "negotiating":         "info",
            "out_for_signature":   "primary",
            "signed_pending_copy": "warning",
            "executed":            "success",
            "waived":              "light",
            "n_a":                 "light",
        }.get(self.agreement_stage, "secondary")

    @property
    def agreement_stage_order(self):
        return {
            "not_started": 0, "draft": 1, "negotiating": 2,
            "out_for_signature": 3, "signed_pending_copy": 4, "executed": 5,
            "waived": -1, "n_a": -1,
        }.get(self.agreement_stage, 0)

    @property
    def needs_executed_copy(self):
        """True when signing is believed done but no counter-signed file is stored."""
        return self.agreement_stage == "signed_pending_copy"

    @property
    def agreement_last_activity(self):
        """Most recent timestamp across clearance, outreach, replies, docs, and thread."""
        import json as _json
        cands = [self.created_at, self.ai_outreach_sent_at, self.rh_response_at, self.cleared_at]
        for d in self.documents:
            cands.append(d.created_at)
        try:
            for turn in _json.loads(self.negotiation_log_json or "[]"):
                ts = turn.get("ts")
                if ts:
                    try:
                        cands.append(datetime.fromisoformat(ts))
                    except Exception:
                        pass
        except Exception:
            pass
        cands = [c for c in cands if c]
        return max(cands) if cands else None

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


class Invite(db.Model):
    __tablename__ = "invites"
    id            = db.Column(db.Integer, primary_key=True)
    platform_id   = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    email         = db.Column(db.String(200), nullable=False)
    name          = db.Column(db.String(200))           # submitter name (optional hint)
    project_hint  = db.Column(db.String(300))           # project name hint (optional)
    token         = db.Column(db.String(100), unique=True, nullable=False, default=_gen_token)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    used_at       = db.Column(db.DateTime)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"))

    platform   = db.relationship("Platform", backref="invites")
    submission = db.relationship("Submission", backref="invite", uselist=False)

    @property
    def is_used(self):
        return self.used_at is not None


class Template(db.Model):
    """Firm-approved agreement template (folded in from Production Legal Binder).
    The AI drafter uses the matching template (by doc_type == clearance item key) as the
    structural basis for a generated agreement."""
    __tablename__ = "templates"
    id          = db.Column(db.Integer, primary_key=True)
    doc_type    = db.Column(db.String(100), unique=True, nullable=False)
    name        = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    content     = db.Column(db.Text)
    is_active   = db.Column(db.Boolean, default=True)
    times_used  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DealTerm(db.Model):
    """A single negotiable clause on a clearance item's deal (folded in from PLB's
    DealTerm board). Tracks our position vs. theirs vs. the agreed value, per clause."""
    __tablename__ = "deal_terms_board"
    id                = db.Column(db.Integer, primary_key=True)
    clearance_item_id = db.Column(db.Integer, db.ForeignKey("clearance_items.id"), nullable=False)
    label             = db.Column(db.String(200), nullable=False)   # e.g. "Fee", "Term", "Territory"
    our_position      = db.Column(db.Text)
    their_position    = db.Column(db.Text)
    agreed            = db.Column(db.Text)
    status            = db.Column(db.String(20), default="open")    # open | agreed | deadlocked
    sort_order        = db.Column(db.Integer, default=0)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at        = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    item = db.relationship("ClearanceItem", backref=db.backref("deal_board", lazy=True,
                                                               cascade="all, delete-orphan",
                                                               order_by="DealTerm.sort_order"))

    @property
    def status_color(self):
        return {"open": "warning", "agreed": "success", "deadlocked": "danger"}.get(self.status, "secondary")


class ClearanceGuideline(db.Model):
    """One set of clearance guidelines per platform per project type."""
    __tablename__ = "clearance_guidelines"
    id           = db.Column(db.Integer, primary_key=True)
    platform_id  = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    project_type = db.Column(db.String(30), nullable=False)   # live_music | documentary | etc.
    content           = db.Column(db.Text)           # internal BA view
    public_content    = db.Column(db.Text)           # shown to submitters
    show_to_submitters= db.Column(db.Boolean, default=False)
    status       = db.Column(db.String(20), default="draft")  # draft | approved
    approved_by  = db.Column(db.String(100))
    approved_at  = db.Column(db.DateTime)
    version      = db.Column(db.Integer, default=1)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("platform_id", "project_type", name="uq_guideline_platform_type"),)


class FestivalArtist(db.Model):
    """One artist on a festival lineup. A festival is a parent Submission (project_type
    'festival') submitted by a promoter; each artist fans out to its own clearance thread —
    routed into the artist's label BA queue (a child Submission on that label Platform) if
    the artist is signed, or handled directly / handed off to management if not."""
    __tablename__ = "festival_artists"
    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)  # parent festival
    artist_name   = db.Column(db.String(200), nullable=False)
    label_name    = db.Column(db.String(200))           # free text from the promoter
    is_signed     = db.Column(db.Boolean, default=True)  # signed to a label vs independent
    contact_name  = db.Column(db.String(200))           # artist mgmt / label contact
    contact_email = db.Column(db.String(200))
    notes         = db.Column(db.Text)

    # Routing result
    routed_platform_id  = db.Column(db.Integer, db.ForeignKey("platforms.id"))   # label BA, if routed there
    child_submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id")) # the artist's clearance thread
    status        = db.Column(db.String(30), default="pending")
    # pending | routed_label | routed_direct | handed_off | cleared
    handed_off_to = db.Column(db.String(200))           # email the clearance was handed off to
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    festival        = db.relationship("Submission", foreign_keys=[submission_id], backref="festival_artists")
    routed_platform = db.relationship("Platform", foreign_keys=[routed_platform_id])
    child_submission= db.relationship("Submission", foreign_keys=[child_submission_id])

    @property
    def status_label(self):
        return {
            "pending":       "Not routed",
            "routed_label":  "In label BA queue",
            "routed_direct": "Direct clearance",
            "handed_off":    "Handed off",
            "cleared":       "Cleared",
        }.get(self.status, self.status.replace("_", " ").title())

    @property
    def status_color(self):
        return {
            "pending":       "secondary",
            "routed_label":  "info",
            "routed_direct": "warning",
            "handed_off":    "primary",
            "cleared":       "success",
        }.get(self.status, "secondary")


# Project types that get the Cast & Crew tab (talent/crew releases apply).
PRODUCTION_PROJECT_TYPES = {"documentary", "feature_film", "tv_series", "unscripted", "branded"}

# Cast & Crew roles, grouped for display order.
CREW_ROLES = [
    ("talent",             "Talent / Cast"),
    ("director",           "Director"),
    ("cinematographer",    "Cinematographer / DP"),
    ("writer",             "Writer"),
    ("producer",           "Producer"),
    ("executive_producer", "Executive Producer"),
    ("crew",               "Crew"),
    ("company",            "Company / Vendor"),
    ("other",              "Other"),
]
CREW_ROLE_LABELS = dict(CREW_ROLES)


class ProjectContact(db.Model):
    """A person or company involved in a production. The submitter's contact registry —
    the source of signers for releases. Tax IDs are NOT stored here; they're collected
    only at signing, on the release document itself."""
    __tablename__ = "project_contacts"
    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    kind          = db.Column(db.String(20), default="person")   # person | company
    name          = db.Column(db.String(200), nullable=False)
    company       = db.Column(db.String(200))                    # affiliation for a person
    role          = db.Column(db.String(40), default="talent")
    email         = db.Column(db.String(200))
    phone         = db.Column(db.String(50))
    website       = db.Column(db.String(300))
    credit_requirements = db.Column(db.Text)                     # how they must be credited
    notes         = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    submission = db.relationship("Submission", backref="contacts")
    releases   = db.relationship("ReleaseRequest", backref="contact", lazy=True,
                                 cascade="all, delete-orphan")

    @property
    def role_label(self):
        return CREW_ROLE_LABELS.get(self.role, (self.role or "").replace("_", " ").title())

    @property
    def latest_release(self):
        rs = sorted(self.releases, key=lambda r: r.created_at or datetime.min)
        return rs[-1] if rs else None


class ReleaseRequest(db.Model):
    """A general release sent to one individual for signature, with a public signing link,
    an event log, and an automated follow-up cadence (day 3 / 6 / 9, then flag)."""
    __tablename__ = "release_requests"
    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    contact_id    = db.Column(db.Integer, db.ForeignKey("project_contacts.id"))
    token         = db.Column(db.String(60), unique=True, nullable=False, default=_gen_token)
    release_type  = db.Column(db.String(50), default="general_release")
    signer_name   = db.Column(db.String(200))
    signer_email  = db.Column(db.String(200))
    status        = db.Column(db.String(20), default="created")
    # created | sent | viewed | signed | declined
    docusign_envelope_id = db.Column(db.String(100))

    sent_at         = db.Column(db.DateTime)
    viewed_at       = db.Column(db.DateTime)
    signed_at       = db.Column(db.DateTime)
    reminders_sent  = db.Column(db.Integer, default=0)
    last_reminder_at= db.Column(db.DateTime)
    log_json        = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    submission = db.relationship("Submission", backref="release_requests")

    @property
    def log(self):
        import json
        try:
            return json.loads(self.log_json or "[]")
        except Exception:
            return []

    def log_add(self, event, detail=""):
        import json
        entries = self.log
        entries.append({"ts": datetime.utcnow().isoformat(), "event": event, "detail": detail})
        self.log_json = json.dumps(entries)

    @property
    def status_label(self):
        return {
            "created":  "Not sent",
            "sent":     "Sent — awaiting signature",
            "viewed":   "Opened",
            "signed":   "Signed",
            "declined": "Declined",
        }.get(self.status, self.status.title())

    @property
    def status_color(self):
        return {
            "created":  "secondary",
            "sent":     "warning",
            "viewed":   "info",
            "signed":   "success",
            "declined": "danger",
        }.get(self.status, "secondary")
