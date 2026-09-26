# Trusted journals/sources reference

Living list of journals/sources already cited across the vault, extracted 2026-08-17. Discovery aid for /journal-sweep and /institution-sweep - never a restriction.

## For future Claude

Built 2026-08-17 by grepping every real citation already present in `Concepts/*.md`, `Optimization/*.md`, `Protocols/*.md`, `Synthesis/*.md` (incl. `Synthesis/Critiques/`) and `Research/Web/*.md` — both inline citations (e.g. "*JAMA Psychiatry* 2021") and the `> [!success]`/`> [!warning] Verified YYYY-MM-DD` claim-verification callouts. This is a **living document**: whenever `/journal-sweep` or `/institution-sweep` turns up a real, legitimately-accessible journal or source not already listed here, add it (with a rough citation count and 1-2 example topics) rather than letting the list go stale. Counts below are rough (grep-derived, not exhaustive) — treat them as "seen at least this many times," not a precise audit.

**This list is a discovery aid / starting-point prioritization, never a restriction.** `/journal-sweep` and `/institution-sweep` should still search wherever the actual literature lives for a given topic. The point of this list is: when scoping a new sweep, check whether the topic overlaps a journal already known to be productive for this vault, and check that journal directly first — not to limit search to only what's listed here. Every entry is a real, legitimately-accessible source (open-access full text or freely-readable abstract) per this vault's legitimate-access-only rule — nothing paywall-scraped or shadow-library sourced appears here, and nothing like that should ever be added.

## Repositories / open-access databases already relied on

- **PubMed / PubMed Central (PMC)** — the vault's primary abstract + open-access full-text source. `pmc.ncbi.nlm.nih.gov` confirmed (2026-08-01, `journal-sweep.md`) as reliably fetchable via WebFetch directly, preferred over `defuddle` which gets Cloudflare-blocked on some NCBI pages. **Abstract text specifically should come from PubMed's own E-utilities (`efetch`) whenever a PMID exists, not from OpenAlex's reconstructed abstract** — formalized in `concept-audit.md`/`journal-sweep.md` 2026-09-02 after a real, demonstrated case (PMID 37796222) where OpenAlex's summary dropped a study's own stated non-significant p-values and CI-plateau language that materially changed the claim's verdict. Used constantly across nearly every Concept/critique note (dozens of PMC IDs and PubMed IDs cited).
- **OpenAlex** — used for citation-network verification (strongest-alternative, superseding, retraction checks) in `/concept-audit` — its own strength, not abstract-text fidelity (see the PubMed bullet above) — and cited directly with OpenAlex work IDs (e.g. W2016924495, W2946524956) in the Total Body Optimization critique (sauna/CV mortality, ecdysteroids).
- **Cochrane Database of Systematic Reviews** — cited as both a source-of-record and a specific journal (Cerebrolysin for acute ischaemic stroke, BPC-157/Cerebrolysin safety critique, Peptide Neurological Safety Profile).
- **ScienceDirect** — publisher platform, used as an access point for Elsevier-hosted journals (VMO EMG systematic review, high-protein/low-carb breakfast and cognitive performance — Poliquin Bulk Program critique).
- **NCBI Bookshelf / StatPearls / MMWR / DOAJ / DOAB / Crossref** — named in `journal-sweep.md`/`institution-sweep.md`/`book-discovery.md` as intended legitimate sources but no direct citation to any of these found yet in actual vault content as of this extraction — listed here as known-legitimate options to reach for, not yet a demonstrated productive source.

## Journals cited (deduplicated, with rough count and example topics)

| Journal | Count | Example topic(s) cited for |
|---|---|---|
| Neuroendocrinology Letters | 3 | Khavinson Bioregulator Peptides class review |
| Neurological Sciences | 3 | BPC-157/Cerebrolysin safety, Peptide Neurological Safety Profile, CAPTAIN II trial design |
| Psychoneuroendocrinology | 3 | Grief and Attachment, Testosterone/HPG Axis, Allostatic Load and Stress Recovery |
| Cochrane Database of Systematic Reviews | 2 | Cerebrolysin for acute ischaemic stroke |
| Innovation in Aging | 2 | Cardiorespiratory Fitness/VO2max, Exercise Effects on Hippocampal Memory |
| Neurology | 2 | Exercise Effects on Hippocampal Memory, Eyes and Vision |
| American Journal of Psychiatry | 2 | Major Depression neurobiology, Psychedelic-Assisted Therapy |
| PLOS ONE / PLoS ONE | 2 | Mitochondrial Function, Testosterone and Reproductive-Endocrine Axis |
| Nature | 2 | Nutrition Fundamentals (macronutrients), Sleep Architecture and Circadian Rhythm |
| Toxicological Sciences | 2 | Peptide Neurological Safety Profile, Cardiovascular and Lipids (Optimization) |
| Cell Metabolism | 2 (same note) | Insulin Sensitivity |
| British Journal of Sports Medicine | 3 (same note) | Concussion Return-to-Training protocol |
| Frontiers in Psychology | 1 | Attachment Neuroscience and Relationship Stability |
| Mayo Clinic Proceedings | 1 | Cardiorespiratory Fitness, VO2max, Zone 2 Training |
| JAMA Network Open | 1 | Cardiorespiratory Fitness, VO2max, Zone 2 Training |
| Neuron | 1 | Anterior Mid-Cingulate Cortex and Willpower |
| Scientific Reports | 1 | Brain Cholesterol Homeostasis and APOE |
| Mitochondrion | 1 | Environmental Toxin Exposure / functional-medicine detox |
| Biology | 1 | Environmental Toxin Exposure / functional-medicine detox |
| Age and Ageing | 1 | Hormesis and Thermal Stress (cold/heat exposure) |
| Scandinavian Journal of Gastroenterology | 1 | Gut Health and the Microbiome |
| Psychological Science | 1 | Mindset Effects on Physiology |
| Nutrients | 1 | L-Theanine |
| JAMA Psychiatry | 1 | Major Depression - Neurobiology and Treatment |
| Environmental Science & Technology | 1 | Microplastics and Endocrine-Disrupting Chemical Exposure |
| Advances in Gerontology | 1 | Khavinson Bioregulator Peptides class review |
| Frontiers in Nutrition | 1 | Lion's Mane (Hericium erinaceus) |
| Circulation | 1 | Neuroscience of Grief and Attachment |
| Nature Communications | 1 | Nervous System Modulation of Immune Function |
| Fertility and Sterility | 1 | Nutrition Diet Trends and Debates |
| American Journal of Clinical Nutrition | 1 | Postprandial Inflammation and Metabolic Endotoxemia |
| Nutrition and Healthy Aging | 1 | Time-Restricted Eating and Intermittent Fasting |
| Lasers in Surgery and Medicine (Lasers Surg Med) | 1 | Thyroid Function and the HPT Axis |
| Anticancer Agents in Medicinal Chemistry | 1 | Testosterone and the HPG Axis |
| Psychosomatic Medicine | 1 | Allostatic Load and Stress Recovery (Connection Map) |
| JAMA Internal Medicine (JAMA Intern Med) | 1 | Sauna bathing and fatal cardiovascular/all-cause mortality (Total Body Optimization critique) |
| Archives of Toxicology | 1 | Beta-Ecdysterone RCT (Isenmann et al. 2019) |
| Journal of Ethnopharmacology (J Ethnopharmacol) | 1 | Fadogia agrestis rat testicular toxicity study |
| European Review for Medical and Pharmacological Sciences (Eur Rev Med Pharmacol Sci) | 1 | Myo-inositol and selenium, euthyroid restoration (Nordio & Basetti 2017) |
| Journal of Clinical Medicine (J Clin Med) | 1 | Myo-inositol + selenium meta-analysis, Hashimoto's (2026) |
| Frontiers in Endocrinology | 1 | Gluten and Hashimoto's thyroiditis narrative review (2026) |

## 2026-09-09/10 additions (real citations from this session, not yet folded into the counts above)

Added per this file's own "living document" instruction rather than letting it drift further - counts are session-additions only, not merged into the deduplicated table above yet (a future full re-extraction pass should do that properly):

| Journal | Example topic(s) cited for |
|---|---|
| Diabetes (journal) | Cold acclimation recruits BAT in obese humans (Hanssen et al. 2016) |
| Nature Medicine | Cold acclimation improves insulin sensitivity in T2DM (Hanssen et al. 2015) |
| European Heart Journal | EVAPORATE trial - icosapent ethyl plaque regression |
| JAMA (main) | GLAGOV/ASTEROID plaque-regression trials, GH2000 recreational-athlete trial |
| Annals of Internal Medicine | GH2000 growth-hormone-in-athletes RCT |
| JBJS Reviews (J Bone Joint Surg Rev) | 2026 injectable-peptides-in-sports-medicine structured review |
| American Journal of Physiology | Yarasheski 1992 GH + resistance training in young men; nocturnal GH/lipolysis (Boyle et al. 1992) |
| Annals of Surgery | GH-driven lipolysis/re-esterification in burn patients (Aarsland et al. 1996) |
| International Journal of Behavioral Nutrition and Physical Activity | Teixeira et al. 2012 SDT-and-exercise systematic review |
| Sports (Basel, MDPI) | Barbell-training affective-response study |
| Journal of Sports Medicine and Physical Fitness | CrossFit-vs-other-modalities motivation comparison |
| Current Opinion in Clinical Nutrition & Metabolic Care | Brown-fat/TRP-agonist recruitment review (Yoneshiro & Saito 2013) |
| Diagnostics (Basel, MDPI) | Coronary microcalcification imaging review |
| Curr Atheroscler Rep | Serial CCTA lipid-lowering-monitoring review |
| European Journal of Sport Science | Time-restricted feeding in young resistance-trained men (Tinsley et al. 2017) |
| American Journal of Clinical Nutrition | Stote et al. 2007 reduced-meal-frequency trial (already listed above, reinforced) |
| J Funct Morphol Kinesiol | Campbell et al. 2020 intermittent-energy-restriction RCT + its independent reanalysis correction |
| Naunyn-Schmiedeberg's Archives of Pharmacology | Irisin exercise-browning narrative review |

## Not yet directly cited, but named as legitimate targets in the commands themselves

`journal-sweep.md`/`institution-sweep.md`/`book-discovery.md` reference these as intended legitimate sources even though no direct vault citation to them was found in this extraction pass — worth checking first when a sweep's topic plausibly overlaps them: **NCBI Bookshelf, StatPearls, MMWR, DOAJ, DOAB, Crossref, arXiv**.

## High-value candidate journals for this vault's domains, not yet cited (added 2026-09-10, per Ross's request for broader journal coverage)

Real, legitimate, high-quality journals directly relevant to this vault's active domains (exercise physiology/hypertrophy, endocrinology/GH-testosterone-thyroid axes, cardiovascular/lipids, sleep, longevity, nutrition) that haven't come up in any sweep yet — worth reaching for first when a future topic overlaps them, same discovery-aid role as the rest of this list, not a mandate to search all of them every time:

| Journal | Why it's a strong candidate for this vault |
|---|---|
| Journal of Clinical Endocrinology & Metabolism (JCEM) | The field's top endocrinology journal — directly on top of every GH/testosterone/thyroid axis question this vault tracks |
| Medicine & Science in Sports & Exercise (MSSE) | ACSM's flagship journal — core exercise-science venue, hasn't come up despite this vault's heavy hypertrophy/training-volume research |
| Journal of Applied Physiology | Companion to the American Journal of Physiology already cited — exercise/training-adaptation mechanism studies specifically |
| Diabetologia | European counterpart to *Diabetes* (already cited) — insulin-sensitivity/metabolic-disease literature |
| Obesity Reviews / International Journal of Obesity | Body-composition/fat-loss literature this vault's recomp tracking would benefit from |
| GeroScience / Nature Aging / Aging Cell | Longevity-specific venues - relevant given the vault's peptide/bioregulator longevity tracking (Epitalon, SS-31, etc.) |
| Sleep / Sleep Medicine Reviews | Dedicated sleep-science journals - this vault's sleep-architecture tracking currently leans on Huberman-relayed content more than primary sleep literature |
| Metabolism: Clinical and Experimental | Direct overlap with Insulin Sensitivity/GH-axis/recomp tracking |
| Circulation Research | Basic-science companion to *Circulation* (already cited) and *European Heart Journal* (newly cited this session) |
| Molecular Psychiatry / Psychological Medicine | Would deepen the mental-health domain this vault treats as first-class, beyond the American Journal of Psychiatry/JAMA Psychiatry already cited |
| Cell / Cell Reports / Science | General top-tier venues for mechanism-level findings (mTOR, myostatin, cellular-senescence work already referenced in Hypertrophy/Aging notes) that haven't been searched directly yet |

**On "ideally we have all of them" - a real, necessary correction, not just caution**: this vault's actual architecture (`journal-sweep.md` itself, written explicitly) rejects "every journal, full coverage" as a scope - most of the journals above (and virtually every one already in this list) are paywalled for full text, and scraping/downloading paywalled full text is a hard legal/ethical boundary this vault already enforces elsewhere (the same boundary behind `/book-discovery`'s Internet Archive exclusion). **What "integrated" actually means here, and already happens automatically**: any journal - Nature included, already cited twice (Nutrition Fundamentals, Sleep Architecture) - gets used whenever `/journal-sweep`, `/concept-audit`, or a direct research pass like this session's finds a relevant PubMed/OpenAlex-indexed abstract or legitimate open-access article from it. There's no subscription list or standing "coverage" of a journal to build - it's abstract-plus-open-access, topic-by-topic, the same way this session pulled Nature Medicine and JAMA and Annals of Internal Medicine into today's plaque/motivation/brown-fat/GH research without anyone "adding" those journals first. If what's actually wanted is a channel-style recurring monitor (periodically check Nature/Cell/Science/JCEM/etc. tables of contents for new vault-relevant papers, the way `/youtube-channel` tracks new videos), that's a real, different, buildable capability that doesn't exist yet - worth a direct decision before building it, since it's new scope (a scan cadence, a topic-relevance filter, and - same as the YouTube pipeline - a real decision about staying inside abstract-only/open-access-only even for "new paper alerts").

## Extraction method (for whoever updates this next)

Grepped for italicized `*Journal Name* YYYY` inline-citation patterns across `Concepts/`, `Optimization/`, `Protocols/`, `Synthesis/` (incl. `Synthesis/Connections/`, `Synthesis/Critiques/`), plus targeted greps for `PMC\d+`, `PubMed \d+`, `doi.org`, `OpenAlex`, and known repository/journal keywords (StatPearls, NCBI Bookshelf, MMWR, Frontiers in *, Metabolic Brain Disease, Aging (Albany NY)) across the whole vault, and read the one existing `Research/Web/*Journal Sweep*.md` output plus all four `Synthesis/Critiques/*.md` notes directly. This is a grep-based extraction, not a claim that every citation in the vault was caught — if a future pass finds citations this one missed (e.g. journals named without italics or without a `*...*` wrapper), add them.
