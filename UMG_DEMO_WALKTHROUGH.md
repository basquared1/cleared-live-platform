# UMG Demo — Label Waiver Flow (Mara driving the GC)

**Goal:** Mara walks the UMG General Counsel through Cleared.live in **Label · Issuer mode** on the live site — how a major label reviews a producer's clearances and **issues a conditional label waiver** for a filmed live performance, in one rail, with AI doing the drafting.

**Driver:** Mara (relationship owner). **Setup:** Brian (pre-flight, before the call).
**Product:** the deployed unified rail — `https://cleared-live-platform.onrender.com`
**Time:** ~15 min + Q&A.

> Routes/labels below were mapped from the live codebase (`app.py`, `models.py`, `templates/`). This is the **issuer** counterpart to the producer-side `DEMO_WALKTHROUGH.md`.

---

## ⚠️ Frame it right (read first — from the council)

- **Mara leads.** The warm relationship (Mara ↔ GC) is the asset. Open as colleagues solving a real UMG pain, not as a cold vendor.
- **Conflicts, pre-cleared in one breath.** Say it before the GC's team wonders: *"The software is built and sold by **Bliss Tech LLC** — a separate company from our law practice. Brian and I are entertainment attorneys, which is why the work product is sound, but you're evaluating a tech product, not retaining counsel."* That turns the founder credentials into trust instead of a flag.
- **Demo what exists; name what's next.** Be precise about live-vs-roadmap (section at the end). Don't oversell.
- **One project, pre-baked.** No live AI spinners in front of the GC. Brian generates the drafts the day before.

---

## ✅ Pre-flight (Brian, before the call — ~15 min)

1. **Confirm a UMG tenant exists in Issuer mode.**
   - Log into `/admin` → **Platforms**. If there's no UMG label tenant, **Add Platform**:
     - Name `UMG`, slug `umg-label`, **Tenant Mode = Label · Issuer**, tier Enterprise.
   - If a `UMG` tenant already exists in *Intake* mode, open **Edit Platform** and flip **Tenant Mode → Label · Issuer**. (This toggle is the thing we just shipped — it's what makes one rail serve both labels and platforms.)
2. **Create a UMG BA login:** Render shell → `flask create-ba-user umg-label umg_ba <password>` (or via admin if a UI exists). Confirm sign-in at `/platform/login`.
3. **Pre-bake the demo project** so all drafts exist (no spinner live):
   - In the UMG BA dashboard → **Invites** → send an invite to **your own email** (`basquared@gmail.com`).
   - Open the invite link, submit a **Live Music** project, e.g. *"DEMO — [UMG Artist] Live at [Venue]"*, submitter = your own name/email.
   - Because the tenant is in Issuer mode, the workspace auto-builds the **review + waiver** package and AI drafts the **Conditional Label Waiver** in the background. **Refresh once after ~30s** and confirm the waiver draft is present.
   - Optionally mark a couple of the "Verify & Review" items complete so the project looks mid-flight, not empty.
4. **Open two tabs:** (A) UMG BA dashboard `/platform/dashboard`; (B) the project workspace `/track/<token>`.
5. Keep the producer-side `DEMO_WALKTHROUGH.md` handy in case the GC asks "what does the producer see?"

---

## The script (Mara driving) · ~15 min

### Act 1 — The pain UMG already feels · 1 min
Every time a third party films a UMG artist's live performance — a promoter, a streamer, a doc crew — UMG has to decide whether to **waive** and on what conditions. Today that's manual: emails, Word docs, chasing whether the producer actually cleared the promoter, publishing, performers, venue. **Talking point:** *"You're the gate. Nothing ships without your waiver — and right now that gate runs on email."*

### Act 2 — UMG on the rail (Tab A) · 2 min
Show the **UMG portal** (issuer mode). One dashboard, every incoming request to use a UMG live performance. **Talking point:** *"This is your system of record — every producer's request to use UMG content, in one place, instead of scattered inboxes."*

### Act 3 — The review queue (Tab B) · 4 min
Open the project. Point out the **Verify & Review** checklist the rail builds automatically for a label:
1. Promoter Consent — Verify & Review
2. Publishing Clearance — Verify & Review
3. Master Recording License — Verify & Review
4. Performer Releases — Verify & Review
5. Venue Filming License — Verify & Review
6. Crowd / Audience Release — Verify & Review
7. E&O Insurance — Verify & Review

**Talking point:** *"UMG isn't doing the clearing — the producer is. UMG verifies it's all actually in place before waiving. The rail makes the producer show their work."*

### Act 4 — Issue the Conditional Label Waiver (the moment) · 4 min
Open the final item, **Conditional Label Waiver — Issue**, and expand the **AI-drafted** waiver. Read the spine aloud (it's already in the draft):
- UMG waives **only** for this specific use, **conditioned on** the producer having obtained all promoter/publishing/performer/venue clearances;
- producer must **carry E&O + name UMG as additional insured**;
- producer **indemnifies** UMG for any third-party claim;
- the waiver is **revocable** if the producer's representations are false;
- it assigns **no** rights beyond the limited waiver.

**Talking point (Mara, as the attorney in the room):** *"I'd send this. It keeps UMG as the rights-holder, conditional and revocable — the AI drafted it; I just approved it. That's the model: AI does the drafting, an attorney signs off."*

### Act 5 — Control + the record (Tab A) · 2 min
Back in the BA dashboard: **nothing waives without UMG sign-off** (the approval gate), and every approval + document is tracked. **Webhooks + REST API** can push status back into UMG's own systems. **Talking point:** *"UMG stays in control and gets a clean record — the opposite of an email thread."*

### Act 6 — Where it goes · 1 min
Be honest about the roadmap (see below): immutable audit log, provisional → final waiver lifecycle, reusable venue/promoter master lists, then the same rail across all the majors. **Talking point:** *"You'd be the first label on the rail — and the rail the platforms plug into on the other side."*

### Close · 1 min
*"It's live in production today. The fastest path is a small paid pilot on a handful of real requests — we onboard UMG as the first label tenant and measure weeks-to-waiver."*

---

## Talking points tuned for a label GC
- **Control:** the waiver is conditional and revocable; UMG never stops being the rights-holder.
- **Compliance / record:** every approval and document tracked in one place (vs. discoverable email threads).
- **Speed:** weeks of back-and-forth → days; requests move in parallel.
- **No manual drafting:** the conditional waiver and the producer-facing agreements are AI-drafted, attorney-approved.
- **Leverage:** the producer does the clearing and proves it; UMG just verifies and waives.

---

## Live today vs. roadmap (don't blur these)
**Live on the deployed rail:**
- Per-tenant **Issuer mode** (UMG) vs. Intake mode (platforms) — the toggle we just shipped.
- Auto-built **Verify & Review** checklist + **AI-drafted Conditional Label Waiver**.
- BA approval gate, document upload / on-site signing, **.docx** export, webhooks + REST API.
- Template-backed AI drafting (firm-approved templates) and a deal-term board.

**Roadmap (built in the separate label-enterprise codebase; to fold into the rail):**
- **Immutable AuditLog** (tamper-evident compliance trail).
- **Provisional → Final** waiver lifecycle with cure deadlines.
- Reusable **Venue / Promoter** master lists.
- Multi-major rollout (Sony, Warner) on the same rail.

---

## After the call
- Leave the DEMO project clearly labeled; no destructive cleanup needed.
- If the GC is warm: propose a **paid pilot** scope (N real requests, success metric = weeks-to-waiver), and get their procurement/security contact so the enterprise motion starts. (Per the council: neither founder has run that motion — line up help before signature.)
