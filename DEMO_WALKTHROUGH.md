# Cleared.live — End-to-End Demo Walkthrough (with Mara)

**Goal:** Show Mara the full clearance flow on the live site, you driving, simplest clean path.
**Project:** A throwaway **DEMO** project on production (Apple TV+). Safe to ignore/delete after.
**Time:** ~20–25 min.

> Routes/labels in this plan were mapped from the codebase (`app.py`, `templates/`, `models.py`).
> Production base URL: `https://cleared-live-platform.onrender.com`

---

## ⚠️ Safety notes (read first)
- **Emails are real** if `RESEND_API_KEY` is set in Render. To keep the demo self-contained,
  use **your own email (`basquared@gmail.com`) for BOTH the submitter and the rights-holder
  contact** — every email then lands in your inbox, never a real third party.
- Title the project **"DEMO — …"** so it's obviously a test in the BA dashboard.
- The simplest way to show AI negotiation **without sending anything externally** is the
  manual path: paste a pretend reply into the console and click **Record reply & run AI**.

---

## ✅ Pre-flight (do BEFORE Mara joins — 5 min)
1. **Confirm BA login works:** go to `/platform/login` and sign in as the Apple TV+ BA.
   - If you don't have/forgot creds, create one from the Render shell:
     `flask create-ba-user apple-tv <username> <password>`
2. **Confirm `flask migrate-db` has been run** (it has, per this session) — so all items/columns exist.
3. **Open two browser tabs:**
   - Tab A — **BA**: `/platform/dashboard` (logged in)
   - Tab B — **Submitter**: blank for now (you'll paste the invite link here)
4. **Have a dummy PDF handy** to "upload" as a signed document (any small PDF).
5. Optional: keep the existing **Noah Kahan – Live at Fenway Park** workspace link open for the
   music-page showcase (Act 6).

---

## The script

### Act 1 — The invite gate (Tab A, BA) · 2 min
Submitting requires an invite, so start as the platform.
1. In the BA dashboard go to **Invites** (`/platform/invites`) → **send/create an invite**
   (`/platform/invite`). Use `basquared@gmail.com`.
2. Copy the invite link: `…/submit/apple-tv?invite=<token>`.
- **Talking point:** platforms control who can submit; every project is tied to a single-use invite.

### Act 2 — Create the project (Tab B, Submitter) · 3 min
1. Paste the invite link. The intake form loads (published guidelines show collapsed at top).
2. Fill the **simplest** path:
   - **Project type:** Documentary / Film (clean, no 25-song setlist research to wait on).
     *(If you'd rather showcase the music features, pick Live Music — but it's heavier.)*
   - **Title:** `DEMO — Mara Walkthrough`
   - Submitter name/company + **email = `basquared@gmail.com`**
   - Territory + intended use, **tier = Standard**, submit.
3. Land on the **confirmation page** → click **Open Clearance Workspace** (`/track/<token>`).
- **Talking point:** one form spins up a full, itemized clearance workspace + AI drafts in the background.

### Act 3 — Workspace tour (Tab B) · 3 min  ← *shows the layout work from this session*
Point out, top to bottom:
- **Two-column desktop layout** using the full width (no more narrow centered column).
- **Left:** the clearance items. **Right sidebar:** Your Progress, **Needs your attention** queue,
  Your Submission, Setlist.
- **Guidelines** sit collapsed at the very top (click to expand — "Start here" house rules).
- Resize the window narrow once to show it **collapses cleanly to one column on phone/tablet**
  (then back to wide).
- **Talking point:** the "Needs your attention" queue is an AI orchestrator telling the producer the next action on every item.

### Act 4 — Work ONE item end-to-end (Tab B) · 6 min  ← *the core value loop*
Pick one item (e.g. **Location Releases** or **Interview Subject Releases**).
1. **Start Working on This Item** → it flips to *in progress* (AI auto-drafts agreement + outreach in background; refresh once if needed).
2. **AI Draft Agreement** → expand to show the full generated agreement; mention inline **Edit** + variable-fill.
3. **Rights Holder Contact** → click **AI Fill Contact** (or type one). **Set the email to `basquared@gmail.com`.** Save.
4. **Outreach Email Draft** → expand to show the AI-written outreach.
5. **Send for Clearance** → sends the outreach to your own inbox; opens the **AI Negotiation Console**.
6. **Negotiation (the wow moment):** in the console, paste a pretend reply, e.g.
   *"We're open to it but need the fee raised to $2,500 and worldwide limited to 5 years."*
   → **Record reply & run AI**.
   - AI classifies it (counter), assesses, and **drafts your next move**.
7. Show the recommendation → **Approve & Send Reply** (or edit first). Loop once more if you want, ending in agreement.
8. **Upload Signed Document** → upload your dummy PDF.
9. **Submit for BA Review** → item goes *under review*; the submission status moves to *in review*.
- **Talking point:** the producer never writes a contract or an email — AI drafts, negotiates, and the human just approves.

*(Optional: quickly mark one or two other items **waived** from the BA tab to fill the progress bar for a tidier "almost done" look.)*

### Act 5 — BA approves → cleared (Tab A, BA) · 3 min
1. In the BA dashboard, open **Approvals** (`/platform/approvals`) — the item you submitted is queued.
2. Open the project, review the uploaded doc, click **Approve**.
   - Submitter gets a reservation-of-rights email; item turns **green / cleared**.
3. Back in Tab B (submitter), refresh → show the **cleared** state. When all items are done the whole submission auto-marks **cleared**.
- **Talking point:** the platform stays in control — nothing clears without BA sign-off; status + webhooks keep their systems in sync.

### Act 6 — (Optional) Music showcase · 4 min  ← *the deepest recent feature*
Open the existing **Noah Kahan – Live at Fenway Park** workspace, then click **Open →** on the
**Music Clearance** card.
- Show the **dedicated music page** (`/track/<token>/music`): the full **Songs & Publishing**
  table (25 songs, writers / publisher / PRO / split, AI-filled) and the **Publisher Clearance
  Groups** (one grouped sync request per publisher).
- Show **"Hand music clearance to someone else"** → generates a scoped link that opens *only* the
  music section for a music supervisor.
- **Talking point:** music is the hardest part of clearance; we split it onto its own page and can hand it to a specialist without exposing the rest of the project.

### Act 7 — Wrap · 1 min
Recap the loop: **invite → submit → AI-drafted workspace → approve AI's negotiation → BA clears → done**,
across submitter, platform BA, and (optionally) a delegated music supervisor.

---

## After the demo (cleanup)
- The DEMO project can be left (clearly labeled) or set aside from the BA dashboard.
- No destructive deletion needed; it won't affect real projects.

## Open items to confirm before the session
- [ ] Apple TV+ **BA login** credentials in hand (or create via `create-ba-user`).
- [ ] `RESEND_API_KEY` set in Render? If **yes**, only your own inbox is emailed (we used your address).
      If **no**, "Send for Clearance" still advances state; use the manual reply path in Act 4.
- [ ] (Optional) Decide Documentary (simplest) vs Live Music (best music showcase) for Act 2.
