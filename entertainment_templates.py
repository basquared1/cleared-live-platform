"""
Entertainment-specific template definitions for Production Legal Binder.
Called from app.py at startup via seed_entertainment_templates().
Each template is idempotent — skipped if doc_type already exists in the DB.
"""

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

ENTERTAINMENT_TEMPLATES = [

# ── 1. ARTIST DEAL MEMO ─────────────────────────────────────────────────────
{
"name": "Artist Deal Memo",
"doc_type": "artist_deal_memo",
"attorney_only": False,
"description": "Engagement terms for a recording or performing artist on a music video, short film, or branded content production.",
"content": """\
ARTIST / PERFORMER DEAL MEMO

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Production Title ("Production"): [PRODUCTION TITLE]

Artist / Performer ("Artist"): [ARTIST LEGAL NAME]
Artist p/k/a: [PROFESSIONAL NAME]
Loan-Out Corporation (if any): [LOANOUT ENTITY]  SSN / EIN: [EIN — W-9 required]

ROLE & SERVICES
Role/Capacity: [CHARACTER NAME / CAPACITY — e.g. "Principal Performer, Lead Vocals"]
Services: [DESCRIBE SERVICES]
Shoot / Service Dates: [START DATE] – [END DATE]
Location(s): [PRIMARY SHOOT LOCATION(S)]

COMPENSATION
Fee: $[AMOUNT] flat, all-in, non-deferrable.
Payment: [e.g. "50% on execution; 50% on final day of services"]
Expenses: [Per Company policy / itemized in Exhibit A]
Per Diem (if applicable): $[AMOUNT]/day

RIGHTS GRANT
Artist grants Company the perpetual, worldwide, irrevocable right to use, reproduce,
distribute, synchronize, publicly perform, display, and create derivatives of Artist's
name, likeness, voice, performance, and biography in connection with the Production in
all media now known or hereafter devised, including theatrical, streaming, broadcast,
digital, social media, and marketing. No additional compensation is due for any
exploitation within this grant.

CREDIT
Screen credit: [CREDIT FORM — e.g. "Separate card, main titles"]
Marketing: Where feasible, at Company's sole discretion.
Credit obligations are waived if technically impractical.

EXCLUSIVITY
[ ] Non-exclusive during engagement.
[ ] Exclusive — Artist shall not render services for competing [productions / brands]
    during: [EXCLUSIVITY PERIOD]. Competing means: [DEFINITION].

WORK FOR HIRE / IP ASSIGNMENT
All results and proceeds of Artist's services are a "work made for hire" (17 U.S.C. § 101).
To the extent any results do not qualify, Artist irrevocably assigns all right, title, and
interest (including all copyrights) to Company, in perpetuity, throughout the universe.

UNION / GUILD
[ ] Non-Union production.
[ ] SAG-AFTRA — Scale [ ] Scale+[__]% [ ] Negotiated: $[AMOUNT]
    H&W contributions: 18.5% (theatrical) / 17.3% (television), per applicable Basic Agreement.
    Residuals payable per applicable SAG-AFTRA schedule.
[ ] AFM — session rate per applicable CBA.

NOTE: If this Production is a SAG-AFTRA signatory production, all guild minimums,
residual obligations, and health & pension contributions apply regardless of this memo.

REPRESENTATIONS & WARRANTIES
Artist: (a) has full authority to enter this agreement; (b) performance will not infringe
any third-party rights; (c) no conflicting agreements exist; (d) will comply with all
applicable law and Company on-set policies.

CONDUCT
Company may suspend or terminate without further obligation if Artist's conduct
reasonably threatens the Production's commercial value or creates legal exposure.

GOVERNING LAW: State of California, Los Angeles County venue.

This Deal Memo constitutes the parties' agreement on the subject matter hereof.
A long-form agreement may follow; in any conflict, the long form controls.

COMPANY:                              ARTIST:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [ARTIST LEGAL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 2. TALENT AGREEMENT (NON-UNION, SINGLE PICTURE) ─────────────────────────
{
"name": "Talent Agreement — Non-Union, Single Picture",
"doc_type": "talent_agreement",
"attorney_only": False,
"description": "Actor/performer engagement for a single non-union film, commercial, or digital production.",
"content": """\
TALENT AGREEMENT — NON-UNION, SINGLE PICTURE

This Talent Agreement ("Agreement") is entered into as of [DATE] between:

PRODUCTION COMPANY: [PRODUCTION COMPANY NAME], a [STATE] [entity type] ("Company"), and
TALENT: [TALENT LEGAL NAME], p/k/a "[PROFESSIONAL NAME]" ("Talent").
Loan-Out: [LOANOUT ENTITY, if applicable]

1. ENGAGEMENT
Company engages Talent to portray the role of "[CHARACTER NAME]" in the motion picture
tentatively titled "[PRODUCTION TITLE]" (the "Picture").

2. SERVICES & SCHEDULE
2.1 Start Date: On or about [START DATE].
2.2 Guaranteed Days: [NUMBER] consecutive days, subject to standard production
    postponement (up to [X] business days' notice).
2.3 Option Days: Company has [NUMBER] additional option day(s) at [$ / day].
2.4 Location(s): [PRIMARY LOCATION(S)]. Travel and accommodation per Company policy.

3. COMPENSATION
3.1 Fee: $[AMOUNT] per [day / week / flat], all-in, non-deferrable.
    [ ] Overscale — no further compensation due.
    [ ] Deferred — $[AMOUNT] payable from first net receipts per Exhibit A.
3.2 Screen Test / Makeup Test (if any): $[AMOUNT] (applicable toward guarantee).
3.3 Expenses: Company reimburses pre-approved, documented expenses.

4. GRANT OF RIGHTS
Talent grants Company the perpetual, worldwide, irrevocable, sublicensable right to:
(a) record, reproduce, distribute, publicly perform, and display Talent's performance
    in the Picture in all media and formats;
(b) use Talent's name, approved likeness, and biography in connection with the
    distribution, exhibition, and promotion of the Picture;
(c) create clips and excerpts for promotional use;
(d) dub, subtitle, or edit Talent's performance as Company deems appropriate,
    subject to applicable guild rules if any apply.

5. WORK FOR HIRE
All results and proceeds of Talent's services constitute a "work made for hire"
(17 U.S.C. § 101). To the extent any such material does not qualify, Talent
irrevocably assigns to Company all copyright and related rights therein,
in perpetuity, throughout the universe.

6. CREDIT
6.1 On-screen: [CREDIT FORM AND PLACEMENT — e.g. "Separate card, main titles, 'Talent Name'"]
6.2 Paid advertising: [WHERE FEASIBLE — specify minimum billing block if agreed]
6.3 No casual or inadvertent failure to provide credit shall constitute a breach.
6.4 Remedy: Prospective cure only; no right to injunctive relief or rescission.

7. EXCLUSIVITY & HOLDBACK
7.1 During production: Talent shall not render competitive services.
7.2 Post-production holdback: [NONE / "[X] weeks after Picture's commercial release
    from rendering similar services in a competing production"].

8. MORALS & CONDUCT
Company may suspend or terminate (without further obligation) upon: (a) Talent's material
breach; (b) force majeure exceeding [X] consecutive days; (c) conduct that Company
reasonably concludes would materially impair the Picture's commercial value.

9. REPRESENTATIONS & WARRANTIES
Talent represents and warrants: (a) full right and authority to enter this Agreement;
(b) no existing obligation conflicts herewith; (c) performance will not infringe
third-party rights; (d) Talent is not a minor (or, if a minor, this Agreement has been
approved by a court of competent jurisdiction per California Family Code § 6750 et seq.).

10. UNION STATUS
This is a [ ] non-union production / [ ] SAG-AFTRA signatory production.
If SAG-AFTRA: Scale/overscale rate applies; H&W contributions (18.5% theatrical /
17.3% TV) and pension contributions are payable per the applicable MBA; residuals
are due and payable in accordance with the applicable SAG-AFTRA agreement.

11. GENERAL
11.1 Governing law: California, Los Angeles County venue.
11.2 Entire Agreement: This Agreement supersedes all prior discussions.
    Long-form agreement may follow; in any conflict, long-form controls.
11.3 Severability; waiver provisions standard.

COMPANY:                              TALENT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [TALENT LEGAL NAME]
Title: [TITLE]                        SSN (last 4): ___-___-____
Date: _______________                 Date: _______________
""",
},

# ── 3. GUEST STAR AGREEMENT ──────────────────────────────────────────────────
{
"name": "Guest Star Agreement — Television / Streaming Episode",
"doc_type": "guest_star_agreement",
"attorney_only": False,
"description": "Guest star engagement for a single episode or limited arc of a scripted or unscripted series.",
"content": """\
GUEST STAR AGREEMENT

Date: [DATE]
Series Title: [SERIES TITLE] ("Series")
Episode(s): [EPISODE TITLE(S) / NUMBER(S)]
Network / Platform: [NETWORK / STREAMING PLATFORM]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Performer ("Talent"): [TALENT LEGAL NAME], p/k/a "[PROFESSIONAL NAME]"
Loan-Out (if any): [LOANOUT ENTITY]

CHARACTER: [CHARACTER NAME], described as: [BRIEF CHARACTER DESCRIPTION]

1. SERVICES & SCHEDULE
Talent shall render services as directed for the Episode(s) listed above.
First Day On: On or about [DATE].
Guaranteed Days: [NUMBER] day(s). Option days: [NUMBER] at same rate.
Location: [SHOOTING LOCATION(S)].

2. COMPENSATION
2.1 Rate: $[AMOUNT] per [day / episode], all-in.
    [ ] SAG-AFTRA Day Player — Scale ($[CURRENT SCALE]/day)
    [ ] SAG-AFTRA Three-Day Player — $[RATE]
    [ ] SAG-AFTRA Weekly — $[RATE]/week
    [ ] Non-Union — $[RATE] flat
2.2 Travel / Expenses: Per Company policy; coach air for domestic travel
    [unless otherwise agreed in writing].

3. RIGHTS GRANT
Company may exploit Talent's performance in the Episode(s) in all media worldwide in
perpetuity, including: initial broadcast/streaming, repeat telecasts, home video, SVOD,
AVOD, FAST, clips, recaps, promotional materials, and ancillary uses.
Talent grants Company the right to use Talent's name, approved likeness, and biography
in connection with the promotion and exploitation of the Series.

4. OPTION FOR ADDITIONAL EPISODES
Company has [NUMBER] options to engage Talent for additional episode(s) of the Series
at the same rate, exercisable by written notice within [X] days of the preceding
episode's wrap.

5. WORK FOR HIRE / IP ASSIGNMENT
Standard work-for-hire and irrevocable assignment language (same as Talent Agreement § 5).

6. CREDIT
Billing: "[BILLING — e.g. 'Guest Starring']" — [placement on-screen].
No casual or inadvertent failure shall constitute a breach; remedy is prospective cure only.

7. SAG-AFTRA COMPLIANCE
If this is a SAG-AFTRA signatory production:
- H&W contributions: 18.5% (theatrical) / 17.3% (primetime/TV) per applicable MBA.
- Pension contributions per applicable SAG-AFTRA schedule.
- Residuals (domestic, foreign, supplemental markets) per applicable SAG-AFTRA agreement.
- Dressing room/trailer accommodations per applicable SAG-AFTRA rider.
- Meals, turnaround, consecutive employment rules apply per applicable SAG-AFTRA agreement.

NOTE TO DRAFTING ATTORNEY: Confirm whether SAG-AFTRA Modified Low Budget, Low Budget,
Basic Cable, New Media, or Theatrical agreement applies. Adjust residual schedules accordingly.

8. GOVERNING LAW
California; Los Angeles County venue.

COMPANY:                              TALENT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [TALENT LEGAL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 4. PRE-PUBLICATION REVIEW AGREEMENT ──────────────────────────────────────
{
"name": "Pre-Publication Review Agreement (Documentary Subject)",
"doc_type": "pre_publication_review",
"attorney_only": False,
"description": "Agreement granting a documentary subject limited factual-accuracy review rights — not editorial approval.",
"content": """\
PRE-PUBLICATION / PRE-RELEASE REVIEW AGREEMENT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Documentary Subject ("Subject"): [SUBJECT FULL NAME]
Production Title ("Documentary"): [DOCUMENTARY TITLE]

RECITALS
Company is producing the Documentary in which Subject appears. Subject has requested an
opportunity to review factual statements made about Subject prior to public release.
Company is willing to provide a limited review right solely for factual accuracy, on the
terms below.

1. REVIEW RIGHT — SCOPE (FACTUAL ACCURACY ONLY)
Company will make available to Subject, no later than [X] business days before the
Documentary's first public exhibition, either: (a) a near-final cut of the Documentary, or
(b) a written summary of material factual statements concerning Subject.

Subject's review right is LIMITED TO: identifying factual inaccuracies (verifiable errors
of fact, such as incorrect dates, names, or descriptions of documented events).

Subject's review right DOES NOT INCLUDE: editorial decisions, creative choices,
narrative framing, point of view, interview order, the use or non-use of any footage,
the selection or omission of Subject's own statements, or any other matter of editorial
judgment. Company retains sole and final editorial control over the Documentary in all respects.

2. SUBJECT'S RESPONSE
Subject shall provide any factual-accuracy comments to Company in writing within
[X] business days of receiving the review materials. Failure to provide timely written
comments constitutes Subject's waiver of the review right for that version.

3. COMPANY'S OBLIGATIONS
Company shall review Subject's written factual-accuracy comments in good faith.
Company has no obligation to make any changes requested by Subject. Any changes made
are solely at Company's discretion.

4. CONFIDENTIALITY
Subject agrees to keep the review materials strictly confidential and shall not share,
reproduce, or disclose any portion of the Documentary or summary to any third party.

5. NO APPROVAL RIGHT
For the avoidance of doubt, this Agreement does not grant Subject any right of approval
over the Documentary's content, release, distribution, or exploitation. Subject's sole
remedy for any dispute regarding this Agreement is a claim for breach of this Agreement;
Subject shall have no right to seek injunctive relief to prevent the Documentary's
distribution or exhibition.

6. RELEASE
In consideration of the rights granted herein, Subject releases and discharges Company
and its successors, licensees, and assigns from any claim arising out of Company's
exercise of its editorial discretion in connection with the Documentary, except for claims
of defamation, false light, or intentional misrepresentation of verifiable facts.

7. GOVERNING LAW
California; Los Angeles County venue.

COMPANY:                              SUBJECT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [SUBJECT FULL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 5. ARCHIVAL LICENSE / BASIC MATERIALS RELEASE ───────────────────────────
{
"name": "Archival License — Basic Materials Release",
"doc_type": "archival_license",
"attorney_only": False,
"description": "License for use of archival footage, photographs, documents, or audio recordings in a production.",
"content": """\
ARCHIVAL MATERIALS LICENSE AGREEMENT

Date: [DATE]
Licensor ("Owner"): [RIGHTS HOLDER NAME / ENTITY]
Address: [LICENSOR ADDRESS]
Licensee ("Company"): [PRODUCTION COMPANY NAME]
Production Title ("Production"): [PRODUCTION TITLE]

LICENSED MATERIALS
The following archival materials (collectively, "Materials"):

  Description: [DETAILED DESCRIPTION — e.g. "Approximately [X] minutes of 16mm footage
                depicting [DESCRIPTION], dated [DATE RANGE], held at [ARCHIVE/COLLECTION]"]
  Identifying Reference: [CATALOG NO. / REEL NO. / PHOTO ID / OTHER IDENTIFIER]
  Format: [FORMAT — e.g. film, digital file, photograph, audio recording, document]
  Duration / Quantity: [LENGTH / NUMBER OF ITEMS]

1. GRANT OF LICENSE
Owner grants Company a [non-exclusive / exclusive], worldwide, perpetual license to:
(a) reproduce, synchronize, incorporate, edit, and display the Materials in the Production;
(b) distribute and exploit the Production containing the Materials in all media now known
    or hereafter devised, including theatrical, broadcast, cable, streaming/SVOD/AVOD,
    home video, digital download, educational, and promotional uses;
(c) use clips from the Production containing Materials in trailers and promotional content.

2. TERRITORY: Worldwide.
3. TERM: Perpetual (or: [X] years from [DATE], with [renewal option]).

4. LICENSE FEE
$[AMOUNT] [flat / per use / per minute], payable [on execution / upon delivery].
[ ] No fee — materials provided as courtesy (documentary/educational use).
[ ] Deferred — $[AMOUNT] payable from [first revenues / net receipts].

5. CREDIT
Company shall include the following on-screen credit where reasonable and customary:
"[CREDIT LINE AS SPECIFIED BY OWNER — e.g. 'Archival footage courtesy of [OWNER]']"
Casual or inadvertent omission shall not constitute a breach; remedy is prospective cure.

6. DELIVERY OF MATERIALS
Owner shall deliver (or make available for duplication at Company's cost) the Materials
in [FORMAT] within [X] business days of execution.

7. OWNER'S WARRANTIES
Owner represents and warrants: (a) Owner is the sole owner or authorized licensor of all
rights in the Materials; (b) the Materials do not infringe any third-party copyright,
right of publicity, defamation, or privacy right; (c) no third-party consents are required
for the use licensed herein (or, if required, Owner will obtain them at Owner's expense).

8. COMPANY'S WARRANTIES
Company: (a) will use the Materials solely as described herein; (b) will not transfer or
sublicense the Materials independently (only as embedded in the Production).

9. INDEMNIFICATION
Each party shall indemnify, defend, and hold harmless the other from third-party claims
arising out of the indemnifying party's breach of its representations and warranties.

10. E&O INSURANCE
Company agrees to include Owner as an additional insured on its E&O insurance policy,
minimum coverage $[AMOUNT] per occurrence / $[AMOUNT] aggregate.

11. MORAL RIGHTS / INTEGRITY
Company may edit, cut, and adapt the Materials as reasonably necessary for editorial
purposes without additional consent from Owner, subject to any applicable moral rights
that cannot be waived under applicable law.

12. GOVERNING LAW: [STATE] law; [COUNTY] venue.

OWNER:                                COMPANY:
By: ___________________________       By: ___________________________
Name: [OWNER SIGNATORY]              Name: [AUTHORIZED SIGNATORY]
Title: [TITLE]                        Title: [TITLE]
Date: _______________                 Date: _______________
""",
},

# ── 6. OPTION / PURCHASE AGREEMENT (UNDERLYING RIGHTS) ──────────────────────
{
"name": "Option / Purchase Agreement — Underlying Rights",
"doc_type": "option_purchase_agreement",
"attorney_only": False,
"description": "Option and purchase of underlying rights including Life Rights, Book, Format, Short Story, Short Film, and similar properties.",
"content": """\
OPTION AND PURCHASE AGREEMENT — UNDERLYING RIGHTS

Date: [DATE]
Owner ("Seller"): [RIGHTS OWNER FULL LEGAL NAME / ENTITY]
Address: [SELLER ADDRESS]
Production Company ("Buyer"): [PRODUCTION COMPANY NAME / ENTITY]

Property Description ("Property"):
  Title: [TITLE OF UNDERLYING WORK]
  Type: [ ] Book  [ ] Life Rights  [ ] Format  [ ] Short Story  [ ] Short Film  [ ] Other: ______
  Written by / Owned by: [AUTHOR / OWNER]
  Registration: [WGA/Copyright Registration No., if applicable]
  Description: [BRIEF SYNOPSIS / DESCRIPTION OF PROPERTY]

NOTE TO ATTORNEY: Confirm chain of title before execution. For Life Rights, confirm no
competing rights exist and that subject has capacity to contract. For published works,
confirm copyright ownership and any publisher assignment of rights.

─────────────────────────────────────────────────────────────────────────────

PART I — OPTION

1. GRANT OF OPTION
Seller grants Buyer the exclusive, irrevocable option to purchase the rights set forth in
Part II for the Option Period and in consideration of the Option Fee.

2. OPTION FEE
Initial Option: $[AMOUNT], payable upon execution, applicable against the Purchase Price.
First Extension Option: $[AMOUNT] ([ ] applicable / [ ] not applicable against Purchase Price).

3. OPTION PERIOD
3.1 Initial Option Period: [X] months from the date hereof.
3.2 Extension: Buyer may extend for [X] additional months upon payment of $[AMOUNT].
3.3 Maximum Option Period: [X] total months.
3.4 Development Period: The Option Period(s) run concurrently with active development.

4. EXERCISE OF OPTION
Buyer may exercise the Option at any time during the Option Period by written notice to
Seller accompanied by payment of the Purchase Price (less Option Fee(s) paid and
designated as applicable).

5. RIGHTS RESERVED DURING OPTION
Seller shall not grant any rights in the Property to any third party, and shall not
encumber the Property in any way that would impair Buyer's rights hereunder during any
Option Period.

─────────────────────────────────────────────────────────────────────────────

PART II — PURCHASE / RIGHTS GRANT

6. PURCHASE PRICE
$[AMOUNT] total (less applicable Option Fee(s)), payable upon exercise of Option or
commencement of principal photography, whichever is earlier.
Contingent Additional Payment (if applicable): $[AMOUNT] upon [theatrical release /
streaming premiere / award nomination — specify].

7. RIGHTS GRANTED (upon exercise of Option)
Seller grants Buyer the exclusive, irrevocable, worldwide, perpetual right to:

(a) Produce, develop, and release one (1) [feature film / television series / limited series /
    mini-series / podcast / stage adaptation — circle applicable] based upon the Property
    and all sequels, prequels, remakes, series, and spin-offs therefrom;

(b) Adapt, translate, abridge, modify, and create derivative works of the Property;

(c) Use the title, characters, storylines, themes, plots, and all other elements of the
    Property in any and all media now known or hereafter devised, including theatrical,
    home video, streaming, broadcast, cable, digital, interactive/gaming, and merchandising;

(d) Use Seller's name and approved biography (where applicable) in connection with
    promotion and exploitation of the production.

8. RESERVED RIGHTS
The following rights are reserved by Seller: [LIST RESERVED RIGHTS — e.g. "Stage rights
for [X] years," "Novelization rights," "Original work rights if option lapses"].
Publication rights in the original work: [ ] Reserved  [ ] Included

9. SEQUEL / REMAKE RIGHTS
Buyer has the exclusive right to produce sequels, prequels, and remakes. Seller shall
receive [X]% of the Purchase Price per sequel/remake, payable upon commencement of
principal photography.

10. SEPARATED RIGHTS (WGA — If Applicable)
NOTE TO ATTORNEY: If this is a WGA signatory production, confirm WGA separation of
rights provisions under the applicable WGA MBA. The WGA separated rights scheme
provides certain minimal rights to the writer of a spec script in addition to any
underlying rights acquired herein. These are distinct from the underlying rights
being acquired from Seller.

11. CREDIT
11.1 Source material credit: "Based on [TYPE — e.g. 'the novel'] '[TITLE]' by [AUTHOR]"
    [in the manner mutually agreed / per WGA credit determination].
11.2 If Life Rights: "[SUBJECT NAME]'s story" or as agreed.
11.3 Credit placement: [Main titles / end titles / on a separate card — specify].
11.4 Credit applies to all copies exploited; casual omission is not a breach.

12. NET PROFITS PARTICIPATION
If applicable: Seller shall receive [X]% of [100% of / Buyer's share of] Net Proceeds,
as defined in Exhibit A attached hereto (Polygram-style definition).

─────────────────────────────────────────────────────────────────────────────

PART III — ADDITIONAL PROVISIONS

13. SELLER'S WARRANTIES
Seller represents and warrants: (a) Seller solely and exclusively owns all rights granted;
(b) the Property is original and does not infringe any third-party copyright; (c) no
third-party consent is required; (d) no agreements encumbering the rights exist;
(e) for Life Rights — Seller is the person described and has full capacity to contract;
(f) for Published Works — all publisher grants/reversions have been secured.

14. REVERSION
If Buyer fails to commence principal photography within [X] years of exercising the Option,
all rights shall revert to Seller upon written notice and return of any production materials
containing Seller's intellectual property, subject to Buyer's right to retain a completed
production if one has been released commercially.

15. E&O INSURANCE
Buyer agrees to name Seller as an additional insured on its E&O policy upon exercise of
the Option. Minimum coverage: $[AMOUNT]/occurrence, $[AMOUNT]/aggregate.

16. GOVERNING LAW
[STATE] law; [COUNTY] venue. Disputes to be resolved by [arbitration per JAMS / litigation].

SELLER:                               BUYER:
By: ___________________________       By: ___________________________
Name: [SELLER LEGAL NAME]            Name: [AUTHORIZED SIGNATORY]
Title (if entity): [TITLE]            Title: [TITLE]
Date: _______________                 Date: _______________
""",
},

# ── 7. E&O INSURANCE SCHEDULE ─────────────────────────────────────────────────
{
"name": "E&O Insurance Schedule — Production Document Checklist",
"doc_type": "eo_schedule",
"attorney_only": False,
"description": "Errors & Omissions insurance document schedule listing required clearance materials for E&O application and distributor delivery.",
"content": """\
ERRORS & OMISSIONS (E&O) INSURANCE SCHEDULE
Production Legal Binder — Document Delivery Checklist

Production Title: [PRODUCTION TITLE]
Production Company: [PRODUCTION COMPANY]
E&O Carrier / Broker: [CARRIER NAME / BROKER]
Policy Period: [START DATE] – [END DATE]
Coverage: $[AMOUNT] per occurrence / $[AMOUNT] aggregate
Deductible: $[AMOUNT]

This schedule identifies all documents required for E&O insurance application and
distributor delivery. Check each item as secured and filed in the Production Binder.

─────────────────────────────────────────────────────────────────────────────
SECTION 1 — CHAIN OF TITLE
─────────────────────────────────────────────────────────────────────────────
[ ] Option / Purchase Agreement (Underlying Rights) — executed copy
[ ] Copyright Registration of Screenplay (WGA registration acceptable as supplement)
[ ] Copyright Assignment or Work-for-hire Agreement (all writers)
[ ] Title search report (covering screenplay title and all similar titles)
[ ] Chain of Title Opinion Letter from cleared entertainment attorney

─────────────────────────────────────────────────────────────────────────────
SECTION 2 — TALENT CLEARANCES
─────────────────────────────────────────────────────────────────────────────
[ ] Lead Talent Agreements (signed) — all principal cast
[ ] Guest Star / Day Player Agreements — all episodic / featured performers
[ ] Appearance Releases — all non-speaking participants captured on camera
[ ] Celebrity / Notable Person Releases — all public figures appearing on camera
[ ] Life Rights Agreement (if applicable — for biographical productions)
[ ] Access Agreement — Living Subject (if applicable)
[ ] Minor's Coogan/Trust Accounts (California) — all performers under 18
[ ] SAG-AFTRA Taft-Hartley Reports (if applicable)

─────────────────────────────────────────────────────────────────────────────
SECTION 3 — LOCATION & PROPERTY
─────────────────────────────────────────────────────────────────────────────
[ ] Location Releases — all recognizable private/commercial locations
[ ] Property Releases — all identifiable personal property / art
[ ] Public Location Permits — all permits issued by applicable authorities
[ ] Crowd/Area Release Signage — documentation of signage placement

─────────────────────────────────────────────────────────────────────────────
SECTION 4 — MUSIC CLEARANCES
─────────────────────────────────────────────────────────────────────────────
[ ] Sync License (Publisher) — each pre-existing musical composition
[ ] Master Use License (Record Label / Owner) — each pre-existing sound recording
[ ] Composer Agreement / Work-for-hire — all original score
[ ] Music Cue Sheet — completed and submitted to applicable PRO(s)
[ ] Side Artist Consents (SAG-AFTRA or applicable) — all session musicians if applicable

─────────────────────────────────────────────────────────────────────────────
SECTION 5 — ARCHIVAL / THIRD-PARTY CONTENT
─────────────────────────────────────────────────────────────────────────────
[ ] Archival Licenses — all third-party footage / photographs / documents
[ ] Materials License Agreements — all archival materials from subjects/estates
[ ] Fair Use Analysis / Clearance Opinion (if applicable)
[ ] Artwork / Trademark Releases (all third-party IP visible on screen)
[ ] News Clip / Stock Footage Licenses

─────────────────────────────────────────────────────────────────────────────
SECTION 6 — CREW / SERVICE AGREEMENTS
─────────────────────────────────────────────────────────────────────────────
[ ] Crew Deal Memos — all key department heads (Director, DP, Editor, Composer, etc.)
[ ] Director Agreement (signed)
[ ] Writer Agreement(s) (signed)
[ ] EP Agreement(s) (signed)
[ ] Production Services Agreement (PSA) — if applicable
[ ] Independent Contractor Agreements — all freelance crew
[ ] Vendor / Facility Agreements (post, VFX, studio)

─────────────────────────────────────────────────────────────────────────────
SECTION 7 — CORPORATE / PRODUCTION ENTITY
─────────────────────────────────────────────────────────────────────────────
[ ] Certificate of Incorporation / LLC Formation Documents
[ ] Producer / Financing Agreement (if co-production)
[ ] Distribution Agreement (if pre-sold)
[ ] Net Proceeds Definition (Exhibit A — attached to applicable agreements)
[ ] Insurance Certificates (production, GL, workers' comp, equipment)

─────────────────────────────────────────────────────────────────────────────
SECTION 8 — CONTENT REVIEW
─────────────────────────────────────────────────────────────────────────────
[ ] Script clearance report (from qualified clearance service or attorney)
[ ] Title search / availability report
[ ] Defamation / privacy review opinion (if applicable — documentary, biopic)
[ ] Pre-publication review agreements (documentary subjects — if granted)
[ ] Disclaimers added: "Any resemblance to actual persons..." / "Based on a true story..." etc.

─────────────────────────────────────────────────────────────────────────────
NOTES / OUTSTANDING ITEMS
─────────────────────────────────────────────────────────────────────────────
[Use this section to track any outstanding items, expected delivery dates, or
items being handled by outside counsel.]

Prepared by: [ATTORNEY / BLA NAME]    Date: [DATE]
""",
},

# ── 8. MULTI-EPISODE TALENT AGREEMENT ──────────────────────────────────────
{
"name": "Multi-Episode Talent Agreement — Series Recurring",
"doc_type": "multi_ep_talent_agreement",
"attorney_only": False,
"description": "Recurring performer engagement across multiple episodes of an unscripted or scripted series.",
"content": """\
MULTI-EPISODE TALENT AGREEMENT

Date: [DATE]
Series Title ("Series"): [SERIES TITLE]
Network / Platform: [NETWORK / STREAMING PLATFORM]
Production Company ("Company"): [PRODUCTION COMPANY]
Performer ("Talent"): [TALENT LEGAL NAME], p/k/a "[PROFESSIONAL NAME]"
Loan-Out (if any): [LOANOUT ENTITY]

CHARACTER / ROLE: [CHARACTER NAME / ROLE DESCRIPTION]
SEASON(S): [SEASON NUMBER(S)]

1. GUARANTEED EPISODES & SCHEDULE
1.1 Guaranteed Episodes: [NUMBER] episodes in Season [X].
1.2 Episode Options: Company has [NUMBER] option episode(s) per season,
    exercisable by [X] days' advance written notice, at the same rate.
1.3 Additional Season Options: Company holds [NUMBER] options for Season(s)
    [X+1, X+2], exercisable by [DATE / X weeks before season production start].
1.4 Availability: Talent shall hold themselves available for [dates / periods — specify].

2. COMPENSATION
2.1 Per-Episode Fee: $[AMOUNT], all-in per produced episode.
    [ ] SAG-AFTRA scale   [ ] Scale +[__]%   [ ] Negotiated (overscale)
2.2 Holding Fee (between seasons): $[AMOUNT] per [week / month] during hold periods.
2.3 Rerun / Repeat (non-SAG): $[AMOUNT] per domestic rerun.
    SAG-AFTRA residuals are separately due per applicable SAG-AFTRA schedule.
2.4 Travel & Expenses: Per Company policy; coach air domestic, business international
    [unless otherwise agreed].

3. EXCLUSIVITY
3.1 During Production: Talent shall not render services in any other [scripted /
    unscripted] television or streaming series that directly competes with the Series.
    Specifics: [DEFINE COMPETING SERVICES — e.g. same genre, same network family].
3.2 Personal appearances and social media obligations per Exhibit [A].

4. GRANT OF RIGHTS
Company may exploit Talent's performance in the Series in all media and formats,
worldwide, in perpetuity, including all exploitation rights in and to each episode.
Company may use Talent's name, approved likeness, and biography in connection with
the promotion and exploitation of the Series and all spin-offs.

5. WORK FOR HIRE / IP ASSIGNMENT
All results and proceeds of Talent's services are works made for hire. To the extent
not qualifying, Talent irrevocably assigns all rights therein to Company.

6. CREDIT
Billing: [BILLING POSITION — e.g. "Series Regular," "Recurring," "Special Guest"]
Placement: [PLACEMENT — e.g. "Main titles, position [X]," "End titles"]
Format: "[CREDIT NAME AS IT APPEARS ON SCREEN]"
Credit applicable to all episodes in which Talent appears; casual omission is not a breach.

7. SAG-AFTRA COMPLIANCE (If Applicable)
If this is a SAG-AFTRA signatory production:
- Minimum rates, H&W, pension, and residuals per applicable SAG-AFTRA Television /
  New Media / Basic Cable Agreement.
- Holding fees: per applicable SAG-AFTRA agreement.
- Option periods and pickup notices per applicable SAG-AFTRA schedule.

8. CONDUCT & MORALS
Company may suspend services and/or exercise series options on 24-hours' notice if
Talent engages in conduct that Company reasonably believes would materially harm the
Series's commercial value or create legal liability.

9. GOVERNING LAW: California; Los Angeles County venue.

COMPANY:                              TALENT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [TALENT LEGAL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 9. PILOT TEST / OPTION AGREEMENT ─────────────────────────────────────────
{
"name": "Pilot Test / Option Agreement — Television / Streaming",
"doc_type": "pilot_option_agreement",
"attorney_only": False,
"description": "Agreement to produce a pilot episode with option to order a full series.",
"content": """\
PILOT TEST / OPTION AGREEMENT

Date: [DATE]
Network / Platform ("Buyer"): [NETWORK / STREAMING PLATFORM NAME]
Production Company ("Producer"): [PRODUCTION COMPANY NAME]
Project Title ("Project"): [PILOT TITLE / SERIES TITLE]
Format: [ ] Scripted   [ ] Unscripted / Reality   [ ] Limited Series
Based On: [UNDERLYING PROPERTY, if any — or "Original Concept by [CREATOR NAME]"]

NOTE TO ATTORNEY: This agreement covers the step deal structure standard for network /
streaming pilot orders. Confirm whether WGA MBA and/or DGA MBA apply and adjust
step compensation accordingly. Confirm whether this is a WGA signatory production.

─────────────────────────────────────────────────────────────────────────────
STEP 1 — PILOT DEVELOPMENT / SCRIPT
─────────────────────────────────────────────────────────────────────────────
1.1 Development Fee: $[AMOUNT] for development materials (bible, treatment, pilot script
    first draft). Payable [on commencement / on delivery].
1.2 Script Step Payments:
    First Draft: $[AMOUNT] payable on delivery.
    Rewrite(s): $[AMOUNT] per rewrite (maximum [X] rewrites).
    Polish(es): $[AMOUNT] per polish (maximum [X] polishes).
    (WGA minimum payments apply if WGA signatory.)

─────────────────────────────────────────────────────────────────────────────
STEP 2 — PILOT PRODUCTION
─────────────────────────────────────────────────────────────────────────────
2.1 Pilot Order: Buyer has the option to order production of one (1) pilot episode,
    exercisable by written notice within [X] days of script delivery.
2.2 Pilot Production Budget: $[AMOUNT] (or as separately agreed in pilot production budget).
2.3 Producer Fee (Pilot): $[AMOUNT], inclusive of all producing services.
2.4 Creator / Showrunner Fee: $[AMOUNT] per episode produced.
2.5 Pilot Delivery: [X] weeks from commencement of principal photography.
2.6 Delivery Materials: Per Buyer's standard delivery requirements.

─────────────────────────────────────────────────────────────────────────────
STEP 3 — SERIES OPTION
─────────────────────────────────────────────────────────────────────────────
3.1 Series Option: If Buyer orders the pilot under Step 2, Buyer holds an option to
    order a first season of the Series, exercisable by [X] days after pilot delivery.
3.2 Series Order Minimum: [X] episodes guaranteed per ordered season.
3.3 Per-Episode License Fee: $[AMOUNT] (covering all rights as set forth in § 5).
3.4 Additional Season Options: Buyer has [X] options for additional seasons,
    exercisable within [X] days of the season finale of the preceding season.

─────────────────────────────────────────────────────────────────────────────
STEP 4 — COMPENSATION (SERIES REGULAR)
─────────────────────────────────────────────────────────────────────────────
4.1 Showrunner / Creator Fee: $[AMOUNT] per episode (Season 1), with [X]% annual escalation.
4.2 Producer's Overhead: $[AMOUNT] per season, payable on series order.
4.3 Backend / Net Profits: Producer shall receive [X]% of 100% of Net Proceeds.
    Net Proceeds defined per Exhibit A (Polygram-style definition).

5. RIGHTS GRANT
Producer grants Buyer:
(a) The exclusive right to exploit the pilot and all episodes of the Series in all media,
    worldwide, in perpetuity (or for the applicable license term);
(b) All rights in and to the Series format, characters, storylines, and underlying
    materials created in connection with the Project;
(c) The right to produce spin-offs and related series, subject to Creator separated
    rights (if WGA signatory) and applicable credit obligations.

6. PRODUCER'S CREATIVE RIGHTS
6.1 Consultation: Producer shall have reasonable consultation rights over creative
    decisions affecting the Series, including casting, writing staff, and final cut of
    the pilot.
6.2 Final Cut: [Buyer / Producer] holds final cut of the pilot and all episodes.
6.3 Showrunner Approval: Producer's approval required for Series showrunner selection.

7. CREDIT
Creator credit: "Created by [CREATOR NAME]" — separate card, main titles, all episodes.
Producing credits: [SPECIFY ADDITIONAL PRODUCING CREDITS].
Per applicable WGA credit determination for all other writing credits.

8. WGA / GUILD COMPLIANCE
If this is a WGA signatory production:
- All writing fees at or above WGA MBA minimums.
- WGA separated rights provisions apply.
- Credits subject to WGA credit determination process.
- Residuals payable per applicable WGA MBA schedule.
If DGA signatory: Director's creative rights, credit, and compensation per applicable DGA MBA.

9. FIRST NEGOTIATION / LAST REFUSAL
Producer has a first negotiation right (for [X] days) and last refusal right for any
remake, spin-off, or sequel production based on the Series.

10. GOVERNING LAW: [STATE]; [COUNTY] venue.

BUYER:                                PRODUCER:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [AUTHORIZED SIGNATORY]
Title: [TITLE]                        Title: [TITLE]
Date: _______________                 Date: _______________
""",
},

# ── 10. SERIES TALENT AGREEMENT ──────────────────────────────────────────────
{
"name": "Series Talent Agreement — Series Regular (SAG-AFTRA Compliant)",
"doc_type": "series_talent_agreement",
"attorney_only": False,
"description": "Series regular engagement for a scripted television or streaming series, SAG-AFTRA compliant.",
"content": """\
SERIES TALENT AGREEMENT — SERIES REGULAR

Date: [DATE]
Series Title ("Series"): [SERIES TITLE]
Network / Streaming Platform: [NETWORK / PLATFORM]
Production Company ("Company"): [PRODUCTION COMPANY]
Actor ("Talent"): [TALENT LEGAL NAME], p/k/a "[PROFESSIONAL NAME]"
Loan-Out Corp (if any): [LOANOUT ENTITY]

CHARACTER: [CHARACTER NAME]   ROLE TYPE: [ ] Lead   [ ] Co-Lead   [ ] Series Regular
SEASON(S) COMMITTED: Season [X] (and options as set forth below)

NOTE TO ATTORNEY: Confirm applicable SAG-AFTRA agreement (Network Television,
Cable/Streaming, New Media). Adjust H&W rates and residual schedules accordingly.
Confirm whether talent is SAG-AFTRA member. Obtain Taft-Hartley if non-member.

─────────────────────────────────────────────────────────────────────────────
1. ENGAGEMENT & SCHEDULE
─────────────────────────────────────────────────────────────────────────────
1.1 Season [X] Guaranteed Episodes: [NUMBER].
1.2 Options for Additional Episodes: [NUMBER] per season, at same weekly rate.
1.3 Options for Additional Seasons: Company has options for Season(s) [X+1, X+2],
    exercisable no later than [DATE / X weeks before production start of optioned season].
1.4 Talent shall hold themselves available exclusively for Company's call
    throughout the production period of each ordered season.

─────────────────────────────────────────────────────────────────────────────
2. COMPENSATION
─────────────────────────────────────────────────────────────────────────────
2.1 Rate: $[AMOUNT] per [week / episode], all-in.
    SAG-AFTRA: [ ] Scale   [ ] Scale+[__]%   [ ] Negotiated (overscale): $[AMOUNT]
    Minimum per applicable SAG-AFTRA Television Agreement: [CURRENT SCALE].
2.2 Holding Fees (between seasons): $[HOLDING FEE RATE] per week, per applicable
    SAG-AFTRA holding fee provisions.
2.3 Stunt Adjustment (if applicable): Per applicable SAG-AFTRA schedule.
2.4 Travel & Per Diem: Per Company policy; [business class / coach] air.

3. SAG-AFTRA COMPLIANCE
3.1 Health & Welfare: Company shall remit H&W contributions at the applicable rate
    ([X]% of compensation, per applicable SAG-AFTRA schedule) to SAG-AFTRA H&P.
3.2 Pension: Company shall remit pension contributions per applicable SAG-AFTRA MBA.
3.3 Residuals: Domestic reuse, foreign, and supplemental market residuals are payable
    per the applicable SAG-AFTRA Television Agreement / Streaming / New Media provisions.
3.4 Working Conditions: Dressing room, meal period, turnaround, travel, rest periods
    per applicable SAG-AFTRA provisions.
3.5 Screen Test: Payable per applicable SAG-AFTRA provisions.

4. GRANT OF RIGHTS
Company may exploit Talent's performance in the Series in all media, worldwide,
in perpetuity (subject to applicable residual obligations), including:
initial release, repeats, home video, SVOD, AVOD, FAST channels, digital platforms,
promotional clips and trailers, and any and all future media.

5. EXCLUSIVITY
5.1 During Production: Talent shall not render services as an actor in any other
    television or streaming series, pilot, or motion picture without Company's
    written consent (not to be unreasonably withheld for non-conflicting projects).
5.2 Theatrical Exception: Talent may render theatrical motion picture services during
    hiatus periods, provided no conflict with Company's production schedule.
5.3 Social Media / Personal Appearances: Talent shall comply with Company's
    social media policy (Exhibit [A]).

6. CREDIT
6.1 Billing: [BILLING POSITION — e.g. "Star," "Co-Star," "Series Regular"]
6.2 Position: [POSITION — e.g. "First position main titles, separate card"]
6.3 Size: [SIZE — e.g. "100% of the size of the title of the Series"]
6.4 Subject to applicable WGA credit determination for any episodes on which Talent
    receives writing credit.

7. WORK FOR HIRE / IP ASSIGNMENT
Standard work-for-hire; irrevocable assignment of all rights to Company to the extent
any results do not qualify as work made for hire.

8. NET PROFITS PARTICIPATION (If Applicable)
[ ] Talent shall receive [X]% of [100% of / Producer's share of] Net Proceeds.
    Net Proceeds defined per Exhibit A (attached).

9. CONDUCT
Company may suspend and/or decline to exercise options upon material breach or
conduct that Company reasonably believes would materially harm the Series.

10. GOVERNING LAW: California; Los Angeles County venue.

COMPANY:                              TALENT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [TALENT LEGAL NAME]
Title: [TITLE]                        SSN (last 4): ___-___-____
Date: _______________                 Date: _______________
""",
},

# ── 11. EXECUTIVE PRODUCER AGREEMENT ─────────────────────────────────────────
{
"name": "Executive Producer Agreement",
"doc_type": "ep_agreement",
"attorney_only": False,
"description": "Executive Producer engagement covering creative, financial, and credit terms for film or series.",
"content": """\
EXECUTIVE PRODUCER AGREEMENT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME / ENTITY]
Executive Producer ("EP"): [EP FULL LEGAL NAME]
Loan-Out Corp (if any): [LOANOUT ENTITY]
Project ("Project"): [FILM / SERIES TITLE]
Format: [ ] Feature Film   [ ] Television Series   [ ] Limited Series   [ ] Documentary

1. ENGAGEMENT & SERVICES
Company engages EP, and EP agrees to render, executive producing services in connection
with the Project, including:
(a) Creative oversight and development of the Project;
(b) [Showrunner services — if applicable — including overseeing writing staff,
    production, and post-production];
(c) Liaison with network/platform (if applicable);
(d) Participation in casting, directing, and other key creative decisions;
(e) Representation of the Project at markets, festivals, and press events as required;
(f) Such other services as Company may reasonably request consistent with EP's stature.

2. TERM
2.1 Development Period: From execution through [first day of principal photography /
    network pickup / first episode order — specify].
2.2 Production Period: Through delivery of [the Picture / all episodes of Season [X]].
2.3 Post-Production: Through delivery of all required deliverables.
2.4 Additional Seasons (Series): EP's services shall continue for each additional season
    ordered by [Network / Platform], subject to the options set forth in § 3.

3. COMPENSATION
3.1 Development Fee: $[AMOUNT], payable [on execution / on first day of production].
3.2 Production Fee: $[AMOUNT] per [episode / picture], payable [weekly / on commencement
    of each episode / on delivery].
3.3 Overhead Allowance: $[AMOUNT] per [episode / season], covering EP's office overhead.
3.4 Expense Reimbursement: Company reimburses documented, pre-approved production expenses.
3.5 Additional Season Options:
    Season [X+1]: $[AMOUNT] per episode (or [X]% escalation over prior season).
    Season [X+2]: $[AMOUNT] per episode (or [X]% escalation over prior season).

4. BACKEND / NET PROFITS PARTICIPATION
EP shall receive [X]% of [100% of / Producer's share of] Net Proceeds.
Net Proceeds defined per Exhibit A (attached Polygram-style definition).

5. GRANT OF RIGHTS / WORK FOR HIRE
All creative materials, formats, pitch materials, and other results and proceeds
created by EP in connection with the Project are works made for hire (17 U.S.C. § 101).
To the extent not qualifying, EP irrevocably assigns all rights to Company.
EP's pre-existing materials incorporated into the Project shall be licensed to Company
on a perpetual, worldwide, royalty-free basis.

6. CREDIT
6.1 On-screen credit: "Executive Producer — [EP NAME]"
    Placement: [Separate card, main titles / end titles — specify].
6.2 Paid advertising: [SPECIFY MINIMUM BILLING IN ADS].
6.3 For Series: Credit on all episodes produced under EP's engagement.
6.4 Casual omission not a breach; remedy is prospective cure.

7. EXCLUSIVITY
7.1 During Production: EP shall devote [exclusive / first-priority] time and attention.
7.2 Other Projects: [EP may simultaneously develop other non-competing projects,
    subject to Company's prior approval for any projects in the same genre on the
    same network/platform family].

8. SEPARATION FROM PROJECT
If EP is separated from the Project prior to completion:
(a) If terminated by Company without cause: EP retains credit and all compensation
    earned to date; additional compensation per [SPECIFY SEVERANCE].
(b) If terminated for cause (material breach): EP retains compensation earned;
    credit at Company's discretion per applicable WGA/DGA provisions.

9. GUILD / UNION COMPLIANCE
[ ] WGA: If EP performs writing services, applicable WGA MBA minimums apply.
    Writing credits subject to WGA credit determination.
[ ] DGA: If EP performs directing services, applicable DGA MBA provisions apply.
    Director's cut right, creative rights, and compensation per DGA MBA.
[ ] Non-union project — no guild obligations.

10. REPRESENTATIONS & WARRANTIES
EP: (a) has full right and authority to enter this Agreement; (b) EP's contributions
will not infringe third-party rights; (c) no conflicting obligations exist.

11. GOVERNING LAW: California; Los Angeles County venue.

COMPANY:                              EP:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [EP LEGAL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 12. WRITER AGREEMENT (WGA COMPLIANT) ─────────────────────────────────────
{
"name": "Writer Agreement — WGA Compliant (Television / Theatrical)",
"doc_type": "writer_agreement",
"attorney_only": False,
"description": "Writer engagement for television episode or theatrical screenplay, WGA MBA compliant.",
"content": """\
WRITER AGREEMENT — WGA MINIMUM BASIC AGREEMENT COMPLIANT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Writer ("Writer"): [WRITER LEGAL NAME]
WGA Registration / Status: [ ] WGA Member   [ ] Non-Member (Taft-Hartley may apply)
Project ("Project"): [SERIES TITLE / FILM TITLE]
Episode (if applicable): "[EPISODE TITLE]" — Season [X], Episode [X]
Format: [ ] One-Hour Drama   [ ] Half-Hour Comedy   [ ] Feature Film   [ ] Limited Series

IMPORTANT NOTICE: This Agreement is intended to comply with the WGA Minimum Basic
Agreement (MBA) as applicable. If Company is a WGA signatory, all WGA MBA provisions
are incorporated herein by reference, including without limitation: minimum compensation,
separation of rights, residuals, pension & health contributions, and credit arbitration.
If any term of this Agreement is less favorable than the applicable WGA MBA minimum,
the WGA MBA minimum shall control.

─────────────────────────────────────────────────────────────────────────────
1. WRITING SERVICES & STEPS
─────────────────────────────────────────────────────────────────────────────
1.1 Assignment: Company engages Writer to write [DESCRIBE — e.g. "one (1) one-hour
    television episode" / "the theatrical motion picture screenplay"].

1.2 Step Structure (Television):
    Story / Outline:    $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    First Draft Script: $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    Rewrite:            $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    Polish:             $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])

1.3 Step Structure (Theatrical):
    Treatment:          $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    First Draft:        $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    Rewrite:            $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])
    Polish:             $[AMOUNT]    (WGA minimum: $[CURRENT MBA MINIMUM])

1.4 Delivery Schedule:
    Story / Treatment:  [X] weeks from commencement
    First Draft:        [X] weeks from step notes delivery
    Rewrite(s):         [X] weeks per rewrite from notes

─────────────────────────────────────────────────────────────────────────────
2. COMPENSATION
─────────────────────────────────────────────────────────────────────────────
2.1 Total Guaranteed Compensation: $[TOTAL AMOUNT] (inclusive of steps above).
2.2 Additional Episodes (if series): $[AMOUNT] per episode, with [X]% annual escalation.
2.3 Production Bonus: $[AMOUNT] upon commencement of principal photography
    (if not included in step compensation).
2.4 All amounts are gross; Company deducts applicable withholding as required by law.

3. WGA PENSION & HEALTH
Company shall remit pension contributions ([X]% per applicable WGA schedule) and
health fund contributions to the WGA Pension, Health, and Welfare Plan on all
compensation paid to Writer, as required by the applicable WGA MBA.

4. RESIDUALS
Residuals are payable to Writer per the applicable WGA MBA schedule, including:
domestic reuse fees, foreign residuals, supplemental market residuals (home video,
streaming, SVOD, AVOD, theatrical), and new media residuals, as applicable.

5. CREDIT
5.1 Credit is subject to WGA credit determination procedures.
5.2 Tentative sole writing credit: "[FORM TBD per WGA arbitration]"
5.3 Company shall submit the production to WGA for credit determination per MBA.
5.4 No casual or inadvertent omission shall be a breach; remedy is prospective cure.

6. SEPARATED RIGHTS (WGA THEATRICAL / LIMITED SERIES)
If this is a WGA signatory production and Writer qualifies for separated rights
under the applicable WGA MBA:
(a) Publication rights: Writer retains [per MBA provisions].
(b) Stage rights: Writer retains [per MBA provisions].
(c) Sequel rights: Subject to Company's right of first negotiation.
(d) Dramatic rights: [per MBA provisions].

7. GRANT OF RIGHTS / WORK FOR HIRE
All results and proceeds are works made for hire (17 U.S.C. § 101). To the extent
not qualifying, Writer irrevocably assigns all right, title, and interest to Company.
Subject to WGA separated rights provisions where applicable.

8. EXCLUSIVITY
Writer shall devote [exclusive / first-priority] time and attention to the Project
during the writing period. No conflicting services without Company's prior consent.

9. REPRESENTATIONS & WARRANTIES
Writer: (a) has full authority to enter this Agreement; (b) the Work will be
original (except for incorporated licensed material); (c) no conflicting obligations exist.

10. NET PROFITS (If Applicable)
[ ] Writer shall receive [X]% of [100% of / Producer's share of] Net Proceeds.

11. GOVERNING LAW: California; Los Angeles County venue.
    WGA disputes governed per applicable WGA MBA arbitration provisions.

COMPANY:                              WRITER:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [WRITER LEGAL NAME]
Title: [TITLE]                        WGA #: _______________
Date: _______________                 Date: _______________
""",
},

# ── 13. DIRECTOR AGREEMENT (DGA COMPLIANT) ────────────────────────────────────
{
"name": "Director Agreement — DGA Compliant",
"doc_type": "director_agreement",
"attorney_only": False,
"description": "Director engagement for feature film or television episode, DGA MBA compliant.",
"content": """\
DIRECTOR AGREEMENT — DGA MINIMUM BASIC AGREEMENT COMPLIANT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Director ("Director"): [DIRECTOR LEGAL NAME]
Loan-Out Corp (if any): [LOANOUT ENTITY]
DGA Status: [ ] DGA Member   [ ] Non-Member (Taft-Hartley if applicable)
Project ("Project"): [FILM / SERIES TITLE]
Episode (if series): "[EPISODE TITLE]" — Season [X], Episode [X]
Format: [ ] Theatrical Feature   [ ] Television Episode   [ ] Limited Series

IMPORTANT NOTICE: This Agreement is intended to comply with the DGA Minimum Basic
Agreement (MBA) as applicable to the Project. If Company is a DGA signatory, all DGA MBA
provisions are incorporated herein by reference, including minimum compensation,
creative rights (director's cut, consultation), residuals, and pension & health.
If any term herein is less favorable than the applicable DGA MBA minimum, the DGA MBA
minimum shall control.

─────────────────────────────────────────────────────────────────────────────
1. SERVICES
─────────────────────────────────────────────────────────────────────────────
1.1 Company engages Director to direct [the Picture / Episode(s) listed above].
1.2 Pre-Production Services: From [DATE / X weeks before principal photography].
    Director shall participate in: casting, location scouting, rehearsal, and all
    creative preparation customarily provided by a director of Director's stature.
1.3 Principal Photography: [START DATE] – [END DATE (estimated)].
    Estimated shooting days: [NUMBER].
1.4 Post-Production: Director shall participate in editing, scoring sessions,
    ADR, VFX review, and color/sound finishing through final delivery.
    Director's Cut: Director shall have [X] weeks to complete Director's cut after
    receipt of editor's assembly, per applicable DGA MBA provisions.

─────────────────────────────────────────────────────────────────────────────
2. COMPENSATION
─────────────────────────────────────────────────────────────────────────────
2.1 Directing Fee: $[AMOUNT] per [week / episode / flat for the Picture], all-in.
    DGA minimum: $[CURRENT DGA MINIMUM PER APPLICABLE AGREEMENT].
    [ ] Scale   [ ] Overscale: $[AMOUNT]
2.2 Pre-Production: [INCLUDED / $[AMOUNT] per week for [X] weeks of pre-production].
2.3 Post-Production: [INCLUDED / $[AMOUNT] per week for [X] weeks of post].
2.4 Budget-Based Escalation (Theatrical): If final budget exceeds $[AMOUNT],
    Director's fee shall be $[ESCALATED AMOUNT], per applicable DGA MBA schedule.

3. DGA PENSION & HEALTH
Company shall remit pension ([X]%) and health contributions to the DGA Pension and
Health Plans on all compensation paid to Director, per applicable DGA MBA.

4. RESIDUALS
Residuals payable per applicable DGA MBA: theatrical reuse, domestic and foreign
television, supplemental markets, new media, streaming, and SVOD/AVOD, as applicable.

5. CREATIVE RIGHTS (DGA)
5.1 Director's Cut (Theatrical): Director shall have [X] weeks to complete a Director's
    cut of the Picture after receipt of the editor's assembly, per applicable DGA MBA.
5.2 Consultation Rights: Company shall consult with Director on all major creative
    decisions affecting the Picture, including: final cut, music selection, marketing
    materials, and the Director's cut, per applicable DGA MBA provisions.
5.3 Final Cut: [ ] Director holds final cut.   [ ] Company holds final cut.
    Note: DGA MBA may grant Director additional rights regarding the final cut even
    where Company holds contractual final cut. Consult applicable DGA provisions.
5.4 Editing: Company may re-edit the Picture without Director's consent after
    expiration of Director's consultation period, subject to applicable DGA MBA provisions.
5.5 Theatrical Title Card: Director shall receive a single-card director's credit.

6. CREDIT
6.1 On-screen: "Directed by [DIRECTOR NAME]" — separate card, [main / end] titles.
6.2 Paid advertising: [SPECIFY — e.g. "Where Director's name appears, in [X]% size"].
6.3 Subject to applicable DGA credit requirements; no casual omission shall be a breach.

7. GRANT OF RIGHTS / WORK FOR HIRE
All results and proceeds of Director's services are works made for hire (17 U.S.C. § 101).
To the extent not qualifying, Director irrevocably assigns all rights to Company.
Subject to DGA creative rights provisions in § 5.

8. EXCLUSIVITY
Director shall devote exclusive time and attention to the Project during principal
photography. During pre- and post-production periods, Director shall give first priority
to the Project.

9. NET PROFITS PARTICIPATION (If Applicable)
[ ] Director shall receive [X]% of [100% of / Producer's share of] Net Proceeds.

10. REPRESENTATIONS & WARRANTIES
Director: (a) has full authority to enter this Agreement; (b) work will not infringe
third-party rights; (c) no conflicting obligations exist.

11. GOVERNING LAW: California; Los Angeles County venue.
    DGA disputes governed per applicable DGA MBA grievance and arbitration provisions.

COMPANY:                              DIRECTOR:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [DIRECTOR LEGAL NAME]
Title: [TITLE]                        DGA #: _______________
Date: _______________                 Date: _______________
""",
},


# ── 14. INDEPENDENT CONTRACTOR AGREEMENT (ICA) ───────────────────────────────
{
"name": "Independent Contractor Agreement (ICA)",
"doc_type": "ica",
"attorney_only": False,
"description": "Work-for-hire agreement for freelance crew, editors, composers, VFX artists, and other production contractors.",
"content": """\
INDEPENDENT CONTRACTOR AGREEMENT

This Independent Contractor Agreement ("Agreement") is entered into as of [DATE]
between:

PRODUCTION COMPANY: [PRODUCTION COMPANY NAME], a [STATE] [entity type] ("Company"), and
CONTRACTOR: [CONTRACTOR FULL LEGAL NAME] ("Contractor").
Loan-Out Corp (if any): [LOANOUT ENTITY NAME]   EIN/SSN: [EIN — W-9 required]

1. ENGAGEMENT
Company engages Contractor to perform the following services ("Services"):

  Role / Capacity: [JOB TITLE — e.g. "Director of Photography," "Editor," "Composer"]
  Production: [PRODUCTION TITLE] ("Production")
  Services: [DESCRIBE SPECIFIC DELIVERABLES — e.g. "Cinematography services during
             principal photography, including all camera operation, lens selection,
             and lighting design for the Production"]

2. TERM & SCHEDULE
2.1 Start Date: [DATE]
2.2 End Date / Delivery: [DATE or "upon delivery of final deliverables"]
2.3 Key Dates: [LIST KEY MILESTONES if applicable]
2.4 Location: [PRIMARY WORK LOCATION(S)]

3. COMPENSATION
3.1 Fee: $[AMOUNT] [flat / per day / per week / per deliverable], all-in.
3.2 Payment Schedule: [e.g. "50% on execution; 50% on final delivery" /
    "weekly, in arrears" / "net 30 from invoice"]
3.3 Expenses: Company reimburses pre-approved, documented expenses within
    [X] business days of submission. Contractor must obtain written approval
    for any single expense exceeding $[AMOUNT].
3.4 No Benefits: Contractor is not entitled to and shall not receive any
    employee benefits, including health insurance, workers' compensation,
    paid vacation, or retirement benefits.

4. INDEPENDENT CONTRACTOR STATUS
4.1 Contractor is an independent contractor, not an employee, partner, agent,
    or joint venturer of Company.
4.2 Contractor shall control the manner and means by which the Services are
    performed, subject to Company's reasonable direction regarding results.
4.3 Contractor is solely responsible for all federal, state, and local taxes
    on compensation received hereunder. Company will issue a Form 1099 where
    required by law.
4.4 Contractor shall maintain any professional licenses or certifications
    required for performance of the Services.

5. WORK FOR HIRE / IP ASSIGNMENT
5.1 All results and proceeds of Contractor's Services, including all
    copyrightable works, inventions, developments, and other work product
    created in connection with this Agreement (collectively, "Work Product"),
    shall be deemed a "work made for hire" as defined in 17 U.S.C. § 101.
5.2 To the extent any Work Product does not qualify as a work made for hire,
    Contractor irrevocably assigns to Company all right, title, and interest
    therein, including all copyright, patent, trademark, trade secret, and
    moral rights, in perpetuity, throughout the universe.
5.3 Pre-existing materials owned by Contractor ("Pre-existing IP") that are
    incorporated into the Work Product are listed in Exhibit A (if any).
    Contractor grants Company a perpetual, royalty-free license to use
    Pre-existing IP solely as incorporated in the Work Product.
5.4 Contractor shall execute any additional documents Company reasonably
    requests to confirm the assignment of rights hereunder.

6. CONFIDENTIALITY
Contractor shall keep confidential all non-public information concerning the
Production, Company's business, and any third parties, and shall not disclose
such information to any third party without Company's prior written consent.
This obligation survives termination of this Agreement for [3 / 5] years.

7. CREDIT
On-screen credit (if any): [CREDIT FORM AND PLACEMENT — e.g. "Director of Photography:
[NAME], end titles" / "No credit obligation"]
Credit is subject to Company's standard practices; casual omission is not a breach.

8. REPRESENTATIONS & WARRANTIES
Contractor represents and warrants: (a) full right and authority to enter this
Agreement; (b) Work Product will be original (except for Pre-existing IP) and will
not infringe any third-party rights; (c) no existing obligation conflicts herewith;
(d) Contractor carries adequate liability insurance for the Services performed.

9. INDEMNIFICATION
Each party shall indemnify, defend, and hold harmless the other from and against
any third-party claims arising out of the indemnifying party's breach of its
representations, warranties, or obligations hereunder.

10. TERMINATION
10.1 Company may terminate this Agreement on [X] business days' written notice.
     Upon termination, Company shall pay Contractor for all Services satisfactorily
     completed through the termination date.
10.2 Company may terminate immediately (without further obligation) for Contractor's
     material breach, provided Company gives written notice and Contractor fails to
     cure within [5] business days.
10.3 All IP assignment and confidentiality obligations survive termination.

11. GENERAL
11.1 Governing law: [STATE]; [COUNTY] venue.
11.2 This Agreement is the entire agreement between the parties on its subject matter.
11.3 Amendments must be in writing and signed by both parties.
11.4 If any provision is unenforceable, the remainder continues in full force.

COMPANY:                              CONTRACTOR:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [CONTRACTOR LEGAL NAME]
Title: [TITLE]                        SSN/EIN (last 4 or full EIN): ___________
Date: _______________                 Date: _______________
""",
},

# ── 15. ACCESS AGREEMENT — LIVING SUBJECT ────────────────────────────────────
{
"name": "Access Agreement — Living Subject",
"doc_type": "access_agreement_living",
"attorney_only": False,
"description": "Agreement granting a documentary production company access to a living subject for filming, interviews, and use of personal materials.",
"content": """\
ACCESS AGREEMENT — LIVING SUBJECT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Subject ("Subject"): [SUBJECT FULL LEGAL NAME]
Production Title ("Documentary"): [DOCUMENTARY TITLE (working title)]

RECITALS
Company is producing the Documentary, a [feature-length / short] documentary film
concerning the life, work, and legacy of Subject. Subject wishes to cooperate with
Company in the production of the Documentary on the terms set forth below.

─────────────────────────────────────────────────────────────────────────────
1. GRANT OF ACCESS & COOPERATION
─────────────────────────────────────────────────────────────────────────────
Subject grants Company the right to:

(a) Film, photograph, and record Subject at times and locations mutually agreed
    in writing, for purposes of the Documentary;
(b) Conduct on-camera and off-camera interviews of Subject;
(c) Access Subject's personal archives, photographs, documents, and materials
    for incorporation into the Documentary, subject to Section 4 below;
(d) Film Subject in Subject's personal and professional environments as agreed;
(e) Use Subject's name, approved likeness, voice, and biography in connection
    with the Documentary and its promotion and distribution.

2. TERM & SCHEDULE
2.1 Access Period: From execution through [ANTICIPATED PRODUCTION WRAP DATE].
2.2 Filming Days: Subject agrees to make themselves available for a minimum of
    [NUMBER] filming day(s), to be scheduled with reasonable advance notice of
    not less than [X] business days.
2.3 Additional filming days may be agreed in writing.

3. COMPENSATION
[ ] Subject shall receive $[AMOUNT] as compensation for cooperation hereunder,
    payable [on execution / upon commencement of principal photography].
[ ] No monetary compensation. Subject's cooperation is provided voluntarily.
[ ] Deferred compensation: $[AMOUNT] from first net receipts.
[ ] Subject shall receive [X]% of Net Proceeds (defined per Exhibit A).

4. PERSONAL MATERIALS
4.1 Subject may (but is not obligated to) provide personal photographs, home
    footage, documents, and other archival materials (collectively, "Materials").
4.2 For any Materials provided, Subject grants Company a non-exclusive, worldwide,
    perpetual license to reproduce and incorporate such Materials in the Documentary.
4.3 Company shall handle all Materials with reasonable care and return originals
    (if any) within [X] days after completion of production.
4.4 Subject represents and warrants that Subject owns or controls sufficient rights
    in any Materials provided to grant the license in Section 4.2.

5. RIGHTS GRANT
Subject grants Company the perpetual, worldwide, irrevocable right to:
(a) Incorporate Subject's participation (including footage and audio) in the Documentary;
(b) Distribute and exploit the Documentary in all media now known or hereafter devised,
    including theatrical, streaming/VOD, broadcast, cable, home video, educational,
    and digital platforms;
(c) Use clips from the Documentary in trailers, promotional materials, and press;
(d) Use Subject's name, biography, and approved likeness in all promotion and
    distribution of the Documentary.

6. EDITORIAL CONTROL
Company retains sole and final editorial control over the Documentary in all
respects, including the selection, use, and context of footage, interviews,
and Materials. Subject has no right of approval over the Documentary's content,
edit, or distribution, except as expressly set forth in Section 7.

7. LIMITED FACTUAL REVIEW (If Granted)
[ ] Not applicable — no review right granted.
[ ] Company agrees to provide Subject with [a near-final cut of the Documentary /
    a written summary of material factual statements about Subject] no later than
    [X] business days before first public exhibition, solely for Subject to identify
    verifiable factual inaccuracies (not editorial judgment). See attached
    Pre-Publication Review Agreement for full terms.

8. LIFE RIGHTS OPTION (If Applicable)
[ ] Not applicable.
[ ] Company holds an option, exercisable by written notice within [X] months
    of execution, to purchase Subject's life rights for use in a separate
    dramatic/narrative production, on terms to be negotiated in good faith.
    Option fee: $[AMOUNT], applicable against the purchase price.

9. CREDIT
Subject shall receive the following on-screen credit:
"[CREDIT FORM — e.g. 'Featuring [SUBJECT NAME]' / 'With the cooperation of [NAME]']"
in [PLACEMENT — e.g. "opening titles," "end titles"].
Credit obligations are subject to Company's standard practices; casual omission
is not a breach. Remedy: prospective cure only.

10. REPRESENTATIONS & WARRANTIES
10.1 Subject: (a) has full right and authority to enter this Agreement;
     (b) Subject's participation will not infringe any third-party rights;
     (c) no conflicting obligation prevents Subject's performance hereunder.
10.2 Company: (a) has full right and authority to produce the Documentary;
     (b) will produce the Documentary in a professional manner;
     (c) carries adequate production insurance.

11. RELEASE
In consideration of Company's agreement to produce the Documentary with Subject's
cooperation, Subject releases and discharges Company and its successors, licensees,
and assigns from any and all claims arising out of: (a) the production, distribution,
or exploitation of the Documentary; (b) Company's exercise of editorial discretion
in the Documentary, except claims for defamation or intentional misrepresentation
of verifiable facts.

12. GOVERNING LAW
[STATE]; [COUNTY] venue.

COMPANY:                              SUBJECT:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [SUBJECT FULL LEGAL NAME]
Title: [TITLE]                        Date: _______________
Date: _______________
""",
},

# ── 16. ACCESS AGREEMENT — ESTATE ────────────────────────────────────────────
{
"name": "Access Agreement — Estate",
"doc_type": "access_agreement_estate",
"attorney_only": False,
"description": "Agreement with the estate or executor of a deceased subject, granting access to archival materials and rights to depict the subject's life and work.",
"content": """\
ACCESS AGREEMENT — ESTATE OF DECEASED SUBJECT

Date: [DATE]
Production Company ("Company"): [PRODUCTION COMPANY NAME]
Estate Representative ("Estate"): [EXECUTOR / ADMINISTRATOR / TRUSTEE NAME]
  Capacity: [ ] Executor   [ ] Administrator   [ ] Trustee   [ ] Authorized Representative
  Estate of: [DECEASED SUBJECT FULL LEGAL NAME] (the "Subject"), deceased [DATE OF DEATH]
Production Title ("Documentary"): [DOCUMENTARY TITLE (working title)]

RECITALS
Company is producing the Documentary, a [feature-length / short] documentary film
concerning the life, work, and legacy of the Subject. The Estate controls certain
rights in and to the Subject's name, likeness, archival materials, and related
intellectual property. Company and the Estate desire to enter into this Agreement
to facilitate the production of the Documentary.

NOTE TO ATTORNEY: Confirm the Estate Representative's authority to enter this
Agreement. Obtain Letters Testamentary or Letters of Administration. Confirm
any statutory right of publicity claims under applicable state law (California,
New York, etc.) and their duration. Confirm any trust or foundation involvement.

─────────────────────────────────────────────────────────────────────────────
1. GRANT OF RIGHTS
─────────────────────────────────────────────────────────────────────────────
Subject to the terms hereof, the Estate grants Company the perpetual, worldwide,
irrevocable right and license to:

(a) Use the Subject's name, likeness, voice recordings, biography, and personal
    history in connection with the Documentary;
(b) Portray, depict, and recreate events from the Subject's life in the Documentary,
    based on publicly available information and materials provided by the Estate;
(c) Reproduce, synchronize, and incorporate into the Documentary: photographs,
    home films/video, correspondence, writings, and other archival materials provided
    by the Estate (collectively, "Estate Materials"), subject to Section 3;
(d) Distribute and exploit the Documentary in all media worldwide in perpetuity,
    including theatrical, streaming/VOD, broadcast, cable, home video, digital,
    and educational distribution;
(e) Use clips, stills, and excerpts from the Documentary in trailers, promotional
    materials, and press coverage.

2. ESTATE COOPERATION
2.1 The Estate agrees to: (a) make available to Company for review and duplication
    the Estate Materials listed or described in Exhibit A; (b) provide one (1)
    authorized representative to conduct an on-camera interview regarding the
    Subject's life and legacy (if agreed); (c) introduce Company to other individuals
    who may have relevant information, where reasonably possible.
2.2 All Estate cooperation is at the Estate's sole discretion; nothing herein
    obligates the Estate to provide any specific materials beyond those listed
    in Exhibit A.

3. ESTATE MATERIALS
3.1 The Estate Materials are described in Exhibit A attached hereto.
3.2 Company shall handle all Estate Materials with reasonable care. Originals
    (if any) shall be returned within [X] days after production wrap.
3.3 Company may duplicate any Estate Materials for production purposes.
3.4 The Estate represents and warrants that it owns or controls sufficient rights
    in the Estate Materials to grant the license in Section 1(c).
3.5 Any Estate Materials not included in Exhibit A that the Estate wishes to
    provide after execution may be added by written amendment.

4. COMPENSATION
[ ] One-time fee: $[AMOUNT], payable [on execution / on first day of production].
[ ] Deferred: $[AMOUNT] from first net receipts of the Documentary.
[ ] Net Profits participation: Estate shall receive [X]% of Net Proceeds
    (defined per Exhibit A).
[ ] No monetary compensation — Estate cooperation provided as courtesy.
[ ] Archive licensing fee: $[AMOUNT] per minute of footage used (minimum $[AMOUNT]).

5. CREDIT
The Documentary shall include the following credit:
"[CREDIT FORM — e.g. 'Produced with the cooperation of the Estate of [SUBJECT NAME]'
/ 'With special thanks to the [SUBJECT] Foundation'"]"
Placement: [PLACEMENT]. Casual omission is not a breach; remedy is prospective cure.

6. EDITORIAL CONTROL & PORTRAYAL
6.1 Company retains sole and final editorial control over the Documentary.
6.2 The Estate has no right of approval over the Documentary's content, edit,
    or distribution, except as expressly provided below.
6.3 Limited Review (if granted):
    [ ] Not applicable.
    [ ] Company will provide the Estate with [a near-final cut / written summary
        of material factual statements] for factual accuracy review only (not
        editorial approval), per attached Pre-Publication Review Agreement.
6.4 Company agrees to produce the Documentary with the intent of providing a
    fair and balanced portrayal of the Subject, based on documented facts.
    This is an expression of Company's intent only and not an enforceable obligation.

7. RESERVED RIGHTS
The following rights are reserved by the Estate and NOT granted herein:
[ ] Dramatic/narrative adaptation rights (feature, scripted series, stage).
[ ] Merchandise and consumer products based on the Subject's name/likeness.
[ ] Music rights in the Subject's recordings (separate synchronization and
    master licenses required — see Music Clearance Agreement).
[ ] Publication rights in the Subject's writings.
[ ] Other: [SPECIFY].

8. REPRESENTATIONS & WARRANTIES
8.1 Estate: (a) Estate Representative has full legal authority to enter this
    Agreement on behalf of the Estate; (b) the rights granted herein do not
    violate any court order, trust provision, or agreement; (c) no third party
    has been granted conflicting rights; (d) Estate Materials do not infringe
    any third-party copyright (to Estate's knowledge).
8.2 Company: (a) has full right and authority to produce and distribute the
    Documentary; (b) will produce the Documentary in a professional manner.

9. INDEMNIFICATION
Each party shall indemnify, defend, and hold harmless the other from third-party
claims arising out of the indemnifying party's breach of its representations
and warranties herein.

10. RIGHT OF FIRST NEGOTIATION (Optional)
[ ] Not applicable.
[ ] If Company wishes to produce any narrative (scripted) adaptation based on the
    Subject's life, Company shall first negotiate exclusively with the Estate for
    [X] days before offering such rights to any third party.

11. GOVERNING LAW
[STATE]; [COUNTY] venue.

COMPANY:                              ESTATE REPRESENTATIVE:
By: ___________________________       By: ___________________________
Name: [AUTHORIZED SIGNATORY]         Name: [ESTATE REPRESENTATIVE NAME]
Title: [TITLE]                        Capacity: [EXECUTOR / TRUSTEE / etc.]
Date: _______________                 Date: _______________

                                      Estate of: [SUBJECT NAME]
                                      Letters Testamentary / Auth. No.: _______
""",
},

]  # end ENTERTAINMENT_TEMPLATES


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def seed_entertainment_templates(db, Template):
    """
    Idempotently seed all entertainment-specific templates.
    Called at startup from app.py. Skips any doc_type already present.
    """
    existing = {t.doc_type for t in Template.query.with_entities(Template.doc_type).all()}
    added = 0
    for tmpl in ENTERTAINMENT_TEMPLATES:
        if tmpl["doc_type"] not in existing:
            db.session.add(Template(
                name=tmpl["name"],
                doc_type=tmpl["doc_type"],
                description=tmpl["description"],
                content=tmpl["content"],
                attorney_only=tmpl.get("attorney_only", False),
                is_active=True,
                source="system",
            ))
            added += 1
    if added:
        db.session.commit()
    return added
