# Domain cutover — make `cleared.live` the new build; move the original to `v1.cleared.live`

**Goal:** point `cleared.live` (+ `www`) at the **new** build (`cleared-live-platform`), and relocate the
**original** Cleared.live (`live-rights-hub` / LRH) to **`v1.cleared.live`**. The new build will become the
combined PLB + LRH product.

## Current state (verified 2026-06-24)
- **Registrar / DNS:** GoDaddy (nameservers `ns41.domaincontrol.com`, `ns42.domaincontrol.com`).
- **`cleared.live` + `www.cleared.live`** → Render service **`live-rights-hub`** (the original LRH app).
  - apex `cleared.live` = A record → `216.24.57.1` (a Render IP)
  - `www.cleared.live` = CNAME → `live-rights-hub.onrender.com`
  - Homepage shows "Coming Soon" splash; the real app is at `cleared.live/login`.
- **New build** = Render service **`cleared-live-platform`** → `cleared-live-platform.onrender.com` (no custom domain yet).

You do all of this in **two dashboards: Render + GoDaddy.** Nothing here is a code change.

---

## ⚠️ Render custom-domain limit (2026-06-24)

The Render **workspace plan includes only 2 custom domains**, and both are used:
`production-legal-hub` and `live-rights-hub` (= cleared.live). So you **cannot add a new custom
domain** (e.g. `app.cleared.live` or `v1.cleared.live`) without freeing a slot or upgrading.

**What this means:**
- **Staging / sharing does NOT need a custom domain.** The new build is already public at
  `https://cleared-live-platform.onrender.com` (walkthroughs at `…/walkthroughs`). Share that link as-is.
- **The apex cutover can be done with ZERO new slots** *if* you let the old LRH app stay at
  `live-rights-hub.onrender.com` (skip `v1.cleared.live`): in Render, **remove** `cleared.live`/`www`
  from `live-rights-hub` and **add** them to `cleared-live-platform` — same slot, reassigned.
- **`v1.cleared.live` is the only piece that needs an extra slot.** Add it only if you want a pretty URL
  for the old app — which requires freeing a slot (drop PLB's or LRH's domain) or upgrading the plan.

So: **Part A (v1) below is OPTIONAL and slot-costly. The slot-free cutover = just Part B**, but in
Part B step 5 you remove cleared.live/www from LRH first (LRH then lives at its onrender.com URL).

---

## ✅ CHOSEN PATH (2026-06-24): STAGE FIRST — share the onrender URL (no custom domain)

Because of the 2-domain limit, staging is simply: **share `https://cleared-live-platform.onrender.com`
(and `…/walkthroughs`)** with reviewers. No Render/GoDaddy changes needed right now.

When ready for the real `cleared.live` cutover, use the **slot-free path**: skip Part A, do Part B but
remove cleared.live/www from `live-rights-hub` before adding them to `cleared-live-platform`.

<details><summary>Original "stage at app.cleared.live" steps (needs a free custom-domain slot — not available now)</summary>

Do **only this** for now. It adds the new build at `app.cleared.live` and **changes nothing** about the
live `cleared.live` (the original LRH app stays exactly as-is — zero risk). Promote the apex later
(Parts A & B below) once you're happy.

1. **Render → `cleared-live-platform` service → Settings → Custom Domains → Add Custom Domain:**
   `app.cleared.live`
   - Render shows a **CNAME** target — it will be **`cleared-live-platform.onrender.com`**. Copy it exactly.
2. **GoDaddy → cleared.live → DNS → Add record:**
   - Type **CNAME**, Name **`app`**, Value **`cleared-live-platform.onrender.com`**, TTL default.
3. Back in Render, wait until `app.cleared.live` shows **Verified / Certificate Issued** (minutes–1 hr).
4. Test **`https://app.cleared.live`** → you should see the **new build**. The walkthroughs are then at
   **`https://app.cleared.live/walkthroughs`** — a clean link you can share with Mara.

That's it for staging. The live `cleared.live` and its `/login` app are unaffected. When you're ready to
make the new build the *real* `cleared.live`, run **Part A** then **Part B** below (and you can remove the
`app.cleared.live` domain afterward, or keep it).

</details>

---

## Order of operations (no-downtime)

Do **Part A first** (old app keeps working at its new v1 address), then **Part B** (move cleared.live to the new build).

### Part A — give the original app its `v1` home (do this first)
1. **Render → `live-rights-hub` service → Settings → Custom Domains → Add Custom Domain:** `v1.cleared.live`
   - Render shows a verification target — for a subdomain it's a **CNAME** (typically `live-rights-hub.onrender.com`). Note exactly what it shows.
2. **GoDaddy → your domain (cleared.live) → DNS → Add record:**
   - Type **CNAME**, Name **`v1`**, Value **`live-rights-hub.onrender.com`** (or whatever Render showed), TTL default.
3. Back in Render, wait until `v1.cleared.live` shows **Verified / Certificate Issued** (minutes–1hr).
4. Test: open **`https://v1.cleared.live/login`** — you should see the original app. ✅ Old app now lives at v1.

### Part B — point `cleared.live` at the new build
5. **Render → `live-rights-hub` → Custom Domains → Remove** `cleared.live` **and** `www.cleared.live`.
   *(Render won't let two services claim the same domain, so the old service must release it first.)*
6. **Render → `cleared-live-platform` service → Settings → Custom Domains → Add Custom Domain:**
   add **`cleared.live`** and **`www.cleared.live`**. Render shows targets:
   - apex `cleared.live` → an **A record IP** (Render anycast; may be `216.24.57.1` or another — use what it shows)
   - `www.cleared.live` → a **CNAME** → `cleared-live-platform.onrender.com`
7. **GoDaddy → DNS → edit the existing records:**
   - **A** record, Name **`@`** (apex): set Value to the **A IP Render shows** for `cleared.live` (if it's the same `216.24.57.1`, no change needed).
   - **CNAME** record, Name **`www`**: change Value from `live-rights-hub.onrender.com` → **`cleared-live-platform.onrender.com`**.
8. Back in Render (`cleared-live-platform`), wait for both domains to show **Verified / Certificate Issued**.
9. Test: **`https://cleared.live`** and **`https://www.cleared.live`** now show the **new build**. ✅

---

## Notes & gotchas
- **GoDaddy apex can't be a CNAME.** That's fine — Render gives an **A record IP** for the apex; GoDaddy supports A records. Use Render's IP. (Don't use GoDaddy "Domain Forwarding" — use the A record.)
- **SSL is automatic.** Render issues Let's Encrypt certs once DNS verifies; no cert work for you.
- **Propagation:** usually minutes, up to ~1 hr (TTL dependent). Lowering TTL to 600s a day before helps.
- **Keep `*.onrender.com` URLs working** the whole time — they're independent of custom domains, so both apps stay reachable at their `onrender.com` addresses throughout.
- **The new build's homepage becomes public the moment Part B DNS verifies.** Confirm it's ready to *be* cleared.live first.

### Safer alternative — stage before flipping the apex
If you want to preview the new build on the domain **before** taking over `cleared.live`:
- In Part B step 6, add **`app.cleared.live`** to `cleared-live-platform` instead of the apex.
- GoDaddy: CNAME `app` → `cleared-live-platform.onrender.com`.
- Test at `https://app.cleared.live`. When happy, repeat steps 5–9 to move the apex + www.

---

## Optional cleanup after cutover
- Update **LRH's `PUBLIC_URL`** env var (currently `https://hub.blisslegalstudio.com`) if you want it to reflect `v1.cleared.live` (affects DocuSign webhooks/links). Render → `live-rights-hub` → Environment.
- Remove LRH's "Coming Soon" splash route (or repurpose) so `v1.cleared.live` root shows the app, if desired.
- Add `cleared.live` to any OAuth/DocuSign/Stripe **allowed-redirect/callback** lists on the new build.
