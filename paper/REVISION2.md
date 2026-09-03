# Revision protocol — round 2 (PI review, 2026-09-03)

**Status: proposal for agreement. Nothing in `main.tex` has been changed.**
Each numbered block maps one review point to a diagnosis, a proposed
edit, and what it needs (text only / new figure / new analysis / your
decision). The decisions are collected at the end. Numbers quoted here
were re-read from `docs/paper-pack/data/`; new analyses are marked as such
and would be added to the pack with an audit check before any prose uses
them.

Figure numbers below are those of the current PDF (`main5.pdf`):
Fig 1 curves, Fig 2 Gini plane, Fig 3 scaling, Fig 4 specification curve,
Fig 5 regional strips, Fig 6 coverage grades, Fig 7 coupling ρ, Fig 8
compounding gallery, Fig 9 vulnerability strata, Fig 10 deprivation vs
access.

---

## R1 — Framing of the abstract and the paper (Musso et al. as the model)

**What could be checked.** arXiv, PNAS, Semantic Scholar, ResearchGate,
the Utrecht working-paper mirror and the press releases are all blocked by
the egress proxy, so the Musso abstract could not be read verbatim. Its
structure is recoverable from indexed snippets and is, sentence by
sentence: (1) a striking stylised fact ("the share of the world population
living in cities of more than one million rose from 11 % in 1975 to 24 %
in 2025"); (2) the open question that fact raises ("will this continue?");
(3) two competing theories named in one sentence each (increasing returns
vs proportional growth); (4) "we introduce two new datasets with
consistent city definitions across countries and over time"; (5) the
finding as a law-like statement ("urban growth follows a life cycle...");
(6) a forward-looking implication with one number (38 % by 2100). **Please
check this against the actual abstract once**; the draft below is built to
that skeleton.

**Diagnosis of the current abstract.** It opens with generic context
("cities concentrate people..."), names the gap as a measurement flaw
(uniform minutes), and only then says what is done. The big question
never appears, the two regimes are not framed as regimes, and the
deprivation-theory import reads as a technical fix. Result: the abstract
sounds like an accessibility paper with a better metric.

**Proposed abstract (draft, 232 words, no citations, for your reaction):**

> Cities are built for an everyday in which residents reach shops, schools
> and doctors at their own pace. A growing share of urban life is spent
> under disruption, when what matters is how fast help reaches people.
> Urban research measures both kinds of need in the same currency, travel
> minutes, and therefore cannot say how bad it is that some residents need
> more time than others. Welfare economics offers an answer. Deprivation
> cost theory, developed for disaster relief, values time without a service
> by the welfare it destroys. Here we bring that theory into urban analysis
> and ask whether the welfare cities deliver follows the same laws in the
> everyday and in the emergency regime. We measure deprivation for 67
> European city regions in 24 countries on a 100 m population grid: a
> bounded level for substitutable everyday services, anchored on the
> 15-minute city, and an unbounded cost for emergency care, anchored on
> clinical response benchmarks. The two regimes obey different laws. Larger
> cities lower everyday deprivation but not emergency deprivation, and
> everyday inequality widens with size while emergency inequality never
> narrows. Emergency deprivation is set by national coverage rather than by
> size, and its extreme, five capital-city emergency deserts, is invisible
> to travel-time averages. The same residents carry both deprivations in
> nearly every city, and children carry the compounded burden most
> consistently. Cities built around the everyday regime deliver welfare
> there and leave the emergency regime to national systems, a division that
> disruption is now testing.

**Introduction, same skeleton.** Paragraph 1: the stylised fact and the
question (the disruption statistics of R2b go here, two or three of them,
not a list). Paragraph 2: the two positions, access measurement vs welfare
economics, and the big theoretical move (R2a). Paragraph 3: the two
regimes as regimes (R2b). Paragraph 4: why Europe (R3). Paragraph 5: what
we do and find, in four sentences. Research questions reduced from four
to three (see R2a); RQ4 becomes the first results section (R6).

Needs: text only. Decision D1 (abstract draft), D2 (title, see end).

---

## R2 — The theoretical contribution

### R2a. Is scaling a theory? Is accessibility? What is ours?

Position I propose the paper takes, stated in the introduction and again
in the Discussion:

- **Urban scaling** is a theoretical programme with an empirical law at
  its core: the 2007 PNAS paper is the regularity, the 2013 *Science*
  paper ("The origins of scaling in cities") is the generative theory that
  explains it. The paper should call it "urban scaling theory" only for
  the 2013 model and otherwise "the scaling regularity" or "scaling laws".
  We do not advance it; we use it as the **benchmark prediction** that
  provisioning improves with size, and we test whether *welfare* does.
- **Accessibility** is not a theory. It is a measurement tradition (Hansen
  1959 defined it as "a measurement of the spatial distribution of
  activities about a point") and a planning doctrine (the 15-minute city).
  The paper should stop positioning it as a theory being advanced and
  position it as **the measurement convention being replaced**.
- **Deprivation cost theory** is the theory. It comes from welfare
  economics via humanitarian logistics (Holguín-Veras et al. 2013, 2016),
  it has axioms (deprivation as a function of time without the good, value
  as willingness to pay, convexity for critical goods), it has been
  econometrically estimated, and it has never been applied to the urban
  structure of a functioning city. **That transfer is the theoretical
  contribution**: it lets us say not only *that* some populations need
  more time but *how bad that is*, in welfare terms, and it is what makes
  the two regimes different objects (a bounded level vs an unbounded cost)
  rather than two travel-time maps. Two hitherto separate strands,
  welfare economics of disaster relief and urban science of proximity, are
  joined; that is the sentence the introduction should build to.

The three big questions the paper then answers, replacing RQ1–RQ4:

1. **How bad is it that some urban residents need more time than others?**
   (the welfare question; answered by the deprivation measurement and by
   what it reveals that minutes cannot: Section R6's first results block)
2. **Does the city that works every day also work in the emergency, and
   does urban growth deliver welfare in both regimes?** (the regime
   question; scaling of levels and inequality, the geography of divergence)
3. **Who carries the burden where the city fails on both clocks?**
   (compounding and its carriers)

Needs: text only, plus two bibliography entries to be verified before use
(Bettencourt 2013 *Science* 340:1438; Hansen 1959 *JAIP* 25:73). Decision
D3 (agree the three questions).

### R2b. The two REGIMES, and the disruption argument

The word "regime" already appears in the paper but it is used as a label
for two service classes. The reframing: cities are designed for an
**assumed ideal day-to-day regime** (the 15-minute city is the purest
expression of that design assumption), while the **emergency regime** is
the one that matters when that assumption fails, and it fails more often.
The everyday regime is walk-based, substitutable and coped with; the
emergency regime is time-critical and cannot be coped with. Deprivation
theory says the two need different loss functions; the paper shows they
obey different laws and have different geographies.

Statistics found that support "the everyday design assumption is
increasingly jeopardised" (all from sources retrieved today; each would
need a verified bibliography entry before use, see the note at the end):

| Claim | Number | Source |
|---|---|---|
| Europe's weather and climate losses have accelerated | EUR 822 bn 1980–2024 in the EU, a quarter of it (EUR 208 bn) in 2021–2024; annual average 2020–2023 2.5× that of 2010–2019 | EEA indicator "Economic losses from weather- and climate-related extremes in Europe" (2025 update) |
| 2024 flooding was the most widespread since 2013 | ≈413,000 people affected, at least 335 deaths, ≥ EUR 18 bn damage; 30 % of the river network above the "high" flood threshold | Copernicus / WMO, *European State of the Climate 2024* |
| Valencia DANA, Oct 2024 | 223–232 deaths; ≈1 million people affected; 7 hospitals and primary-care centres inundated or within 200 m of flooding; highway flooding impeded emergency response | *Public Health Reviews* 2025 (SSPH+), ESOTC 2024 |
| Summer 2025 heat | ≈24,400 heat deaths in 854 European cities, 16,500 attributed to climate change | LSHTM / Imperial rapid attribution study, Sept 2025 |
| Long-run heat mortality | 5.5 heat deaths per 100k per year in Europe 2012–2021, almost double 1992–2021 | Lancet Countdown 2025 Europe report |
| Iberian blackout, 28 Apr 2025 | >10 h outage; traffic-signal failure delayed emergency response; 1-1-2 call networks collapsed; primary care "ground to a halt" | *Prehospital and Disaster Medicine* 2025 ("Blackout in Spain: urgent analysis of impact on EMS") |
| Conflict | >3,000 WHO-verified attacks on health care in Ukraine since Feb 2022, ≈200 ambulances destroyed per year, attacks up ≈20 % in 2025 | WHO Europe, May 2026 |
| Policy response | EU Preparedness Union Strategy (26 Mar 2025): 72-hour household self-sufficiency guideline; 30 actions covering hospitals, schools, transport; Eurobarometer: >8 in 10 Europeans want more EU preparedness | European Commission, Preparedness Union Strategy; Niinistö report (Oct 2024) |
| Routine disruption | EU Civil Protection Mechanism activated 66 times in 2023 and 58 times in 2024 (floods in FR, CZ, PL, ES; wildfires) | European Commission DG ECHO |
| Global | disaster costs >USD 2.3 trillion per year including cascading costs; +1.2 bn urban residents by 2050; five hazards cause 90 % of disaster deaths, extreme heat 18 % | UNDRR GAR 2025 |

Recommended use: the introduction's first paragraph takes **two** of these
(the EEA acceleration and the 2025 heat deaths in 854 cities, or the
Valencia flood as the one concrete case where hospitals and roads failed
together), the Preparedness Union Strategy gives the emergency regime a
policy address in the Discussion, and the rest goes nowhere (a list of
disasters reads as journalism). The paper should also say once, plainly,
that the analysis does not model disruption: it measures the emergency
regime's welfare geography under normal conditions, which is the floor
disruption starts from. The one "usual disruptions" point to make is that
the emergency regime is exercised every day (ambulance calls, ED visits)
and not only in disasters, so its geography matters before any extreme
event.

Needs: text; 5–7 new bibliography entries to verify (see end). Decision
D4 (which statistics to use; whether the conflict statistic belongs in a
paper on European cities).

---

## R3 — Why Europe, and why not the world

Three arguments, to be made in one paragraph of the introduction and
echoed once in the Discussion:

1. **Comparability.** Musso et al. build their own consistent city
   definition because none existed globally; Europe already has one
   (Eurostat/OECD functional urban areas, used here), a harmonised 1 km
   census grid (Census 2021) that no other continent has, near-complete
   OpenStreetMap coverage of both street networks and facilities, and
   clinical EMS response benchmarks that are common across national
   systems. Global travel-time mapping (Weiss et al. 2020; Wu et al. 2025)
   exists, but it cannot carry a welfare calibration or a census-anchored
   vulnerability analysis, and its friction-surface engine is exactly the
   one our engine cross-check demoted to a sensitivity variant (E.1).
2. **A mature urban system.** Musso et al. show that large cities lose
   their growth advantage as urban systems mature. Europe is the mature
   end of that life cycle, so its cross-sectional size gradient is a
   clean reading of *what size delivers* once growth no longer favours
   the large city; a global sample would mix urban systems at different
   life-cycle stages, which their paper shows changes the exponents.
   This is the one place the Musso paper is a substantive benchmark for
   ours rather than a style model.
3. **Legal and policy comparability.** Access to services of general
   interest is a right in the EU legal order (Charter of Fundamental
   Rights Art. 36; TFEU Art. 14; European Pillar of Social Rights
   principle 20, "access to essential services"), emergency care is
   organised nationally under a shared 112 number and shared response
   targets, and the Preparedness Union Strategy (2025) is now asking
   member states to plan for the emergency regime explicitly. The
   findings therefore address one polity with one set of obligations and
   24 national emergency systems, which is what makes "country, not
   size" a policy finding rather than a curiosity.

Needs: text; entries for the Charter / Pillar to verify (primary legal
texts, citable by URL). Decision D5 (use all three, or comparability plus
maturity only).

---

## R4 — Figure 1 (curves) and the level-vs-cost argument

**Diagnosis.** The PNG carries an in-image super-title and a 6.5 pt
footer line that is wider than the three panels. `bbox_inches="tight"`
extends the canvas to that footer, so the panels sit boxed in the left
two-thirds of the image with blank space to the right. Then the LaTeX
caption repeats the footer at length. The calibration (Layer 1, Layer 2,
Box-Cox λ, anchors at 4/8/15 min) is explained in the caption and the
Results opening before Methods has introduced any of it.

**Edits.**
1. Regenerate `deprivation_curves.png` from the paper directory
   (`paper/make_fig_curves.py`, same pattern as `make_fig_dep_vs_access.py`,
   reading `config/deprivation.yaml` for the functions): no suptitle, no
   footer, three panels filling the width, panel titles reduced to
   "Everyday: deprivation level", "Emergency: deprivation cost, benchmark
   window", "Emergency: beyond the benchmark". The sensitivity sweep
   lines stay (they are what the robustness section refers to), but
   thinner and unlabelled in the legend; the legend shows baseline,
   pure-access line, and "sensitivity sweep".
2. LaTeX caption cut to four lines: what each panel is, the dotted line
   is the loss a minutes average implies, panels are on different scales.
3. **All calibration mechanics move to Methods** (curvature grid, form
   swaps, λ, the anchor values). The Results opening keeps only: the two
   objects, what 0/1 and "multiples of the benchmark cost" mean for a
   reader, and the level-vs-cost argument below.
4. **The level-vs-cost argument, made properly** (one paragraph, replacing
   the current "forcing both into levels would assert..."). Deprivation
   theory gives the argument: the welfare loss from time without a good
   depends on whether the good can be substituted or deferred. Everyday
   services can (a further pharmacy, a later trip, a delivery), so the
   marginal minute loses value once coping sets in and the loss is
   bounded; that is a level. Emergency care cannot, and the outcome
   (survival) worsens with every minute, so the marginal minute gains
   value and the loss is unbounded; that is a cost. The two forms are
   not a modelling choice but what the theory implies for the two kinds
   of good, and the comparability rule follows from them: only
   unit-free statistics cross regimes. One sentence then states what the
   asymmetry buys: a single loss function would either declare a
   60-minute ambulance no worse than a 30-minute one or declare a distant
   supermarket a catastrophe.

Needs: new figure script, text. No decision.

---

## R5 — Deprivation vs access wording (Section 2.1 and throughout)

The 2.1 heading says "City size buys everyday **access**"; the abstract
says "size buys everyday access"; the text says "deliver everyday
services closer to people", "proximity to emergency care". After the
paper has just argued that access and deprivation are different things,
every result must be stated in deprivation terms. Rule for the revision:
**"access" and "travel time" appear only when the minutes-based
benchmark is meant**, and every result sentence says "deprivation level"
or "deprivation cost". Headings are rewritten accordingly (R6 gives the
new ones). A grep for "access" in the Results after the edit is the
acceptance check; each surviving occurrence must be a deliberate
reference to the benchmark.

Needs: text only.

---

## R6 — Results structure: order, merges, the Gini figure

**Diagnosis.** Fig 2 (the Gini plane) floats under the 2.1 heading
although 2.1 is about mean levels; the inequality result is in 2.2, the
regional colouring in Fig 2 belongs to 2.3, and the outlined desert
group belongs to 2.3/2.5. Five results sections with the core argument
(2.5) last.

**Proposed structure (four sections):**

**2.0 What is measured** (kept, shortened per R4): the two objects, Fig 1,
Table 1. No Gini plane here.

**2.1 Deprivation, not access: what the welfare layer reveals**
(current 2.5, moved to the front as the core; Fig 10 becomes Fig 2; the
desert table stays with it). Written so that it stands before the
scaling results: move 1, the deprivation outcomes are the better-behaved
objects (R² 0.44 vs 0.16) because the level function discounts
welfare-inert minutes; move 2, the emergency deserts, five capitals that
look average or better by minutes and sit at 2.4–4.7× the sample by
deprivation cost; move 3, the rank agreement (r ≥ 0.965), which is what
licenses every rank-based result later. The "claims survive in plain
minutes" move stays but shortens to two sentences, because it defends
results the reader has not yet seen; it is repeated in one sentence at
the end of 2.2 where it belongs. Forward references to 2.2 and 2.3 are
explicit.

**2.2 Urban growth delivers everyday welfare, not emergency welfare**
(current 2.1 + 2.2 merged, as suggested last round). One figure: Fig 3
(scaling of means) gains a second panel with the Gini elasticities
(everyday +0.062, emergency +0.004, with the paired difference), so the
level and inequality halves sit side by side. The specification curve
(Fig 4) moves to the SI (see R8); the text keeps the two-sentence
summary (positive under all 14 parameterisations, 13/14 significant, the
Box-Cox exception named; emergency flat under two of three escalation
forms, rising under the third).

**2.3 Emergency deprivation has a geography of coverage, not of size**
(current 2.3, reordered per R10: coverage grades first, then regions,
with a map; Fig 2 Gini plane moves here, redrawn with coverage-grade
markers; Fig 5 strips redrawn per R9; Fig 6 kept).

**2.4 Compounding is the norm, and children carry it** (current 2.4,
unchanged in content; Figs 7–9). Consider dropping Fig 7 (ρ ranked by
city) to the SI and keeping the gallery and the vulnerability strata,
since the ρ range and the 66/67 count are two numbers the text carries.

The Gini plane (current Fig 2) is therefore neither an overview nor a
2.1 figure: it is the geography figure, because what it shows is region
and coverage grade in the inequality plane. Its caption changes to say
so.

Needs: text; Fig 3 extended; Figs 2 and 5 redrawn; Fig 4 and possibly
Fig 7 to SI. Decisions D6 (four-section order), D7 (Fig 7 to SI).

---

## R7 — Section 2.3 opening and headline

Current: "If size does not set emergency deprivation, what does? The
divergence between regimes has a geography, and the honest unit for
testing it is the country." The rhetorical question, "honest unit" and the
heading "The geography of divergence: country-level structure and a
coverage gradient" all go.

Proposed heading: **"Emergency deprivation follows national coverage,
not city size"**. Proposed opening (in the register of your abstract seed
in the brief): "Size explains 2 % of the variance in emergency
deprivation cost. Most of the remaining variance sits between countries.
We first identify the structure in the city vectors themselves, then test
whether it aligns with the four macro-regions. Because macro-region is a
property of countries, whole countries are permuted across regions in
every regional test." Then clusters (coverage grades), then regions.

Style pass for the whole paper (from this comment and the earlier
"sound like I write" instruction). Phrases to remove wherever they occur:
"the honest unit/assessment", "survives every diagnostic we throw at
it", "earn their keep", "cuts deeper", "the answers, previewed",
"decisively", "stark", "comfort of the first", "which we state rather
than smooth over", "exactly" as an intensifier, rhetorical questions
opening a section, "not X but Y", colon-chains of three. Register to
adopt (from the brief's abstract seed): short declarative sentences,
"We measure", "We find", "We identify", one claim per sentence, numbers
in the sentence that makes the claim, no throat-clearing before a
result.

Needs: text only.

---

## R8 — Figure 4 (specification curve)

**Diagnosis.** The bottom panel is the finding (the emergency Gini slope
is zero under 13 of 14 parameterisations and rises only under exponential
escalation), but as a figure it shows fourteen points on zero. The top
panel shows fourteen points between 0.03 and 0.08. A reader gains nothing
the two summary sentences do not give.

**Proposal.** Move it to the SI as Fig S2 with the current caption. In the
main text, the merged 2.2 carries the result in prose and the extended
Fig 3 shows the baseline Gini elasticities with their CIs. If a visual
reminder of robustness is wanted in the main text, a small inset in
Fig 3's Gini panel showing the 14 everyday slopes as a strip (all above
zero) and the 14 emergency slopes (all on zero, one off) does the job
in a quarter of the space. Recommendation: SI, no inset.

Needs: LaTeX only (SI figure), or a small figure edit if the inset is
wanted. Decision D8.

---

## R9 — Figure 5: dispersion differs by region, and the South splits in two

**What the data say (recomputed from `cities_descriptives.csv`).**
Dispersion is genuinely unequal across regions:

| indicator | North sd | West sd | South sd | CEE sd |
|---|---|---|---|---|
| coupling ρ | 0.14 | 0.10 | **0.18** | 0.15 |
| everyday Gini | 0.07 | 0.08 | **0.10** | 0.06 |
| emergency Gini | 0.06 | 0.06 | 0.07 | **0.13** |
| divergence gap | 0.07 | 0.07 | 0.10 | **0.16** |

CEE's emergency-Gini spread is twice any other region's, and the five
desert capitals are the reason. The **two South clusters in the everyday
Gini panel are countries**: Spain (Palma, Talavera, Alicante, Madrid,
Jaén, Barcelona, Bilbao) and Athina at 0.50–0.61, Italy and Portugal
(Porto, Caserta, Napoli, Lisboa, Palermo, Vicenza, Milano, Cosenza,
Arezzo, Roma) at 0.27–0.42, with no overlap. That is exactly what the
limitations section already predicts: mapped GP density in PT and IT is a
fifth of the Western median because primary care sits in health centres
OSM tags differently, which inflates everyday deprivation levels there
and compresses their within-city spread. It is also the reason the
everyday-Gini regional contrast fails country permutation while the city
ANOVA passes: the "regional" effect is a two-country effect.

**Proposed new analysis (small, additive to the pack):**
1. A **nested variance decomposition** for each of the four indicators:
   share of city-level variance between regions, between countries within
   region, and within country (random-intercept model, or simple ANOVA
   sums of squares). This answers "any way to compare and measure that"
   directly and gives 2.3 its opening number ("x % of the variance in
   emergency deprivation lies between countries").
2. A **dispersion test** per indicator (Fligner–Killeen across regions,
   with the same country-permutation null used for the medians), so the
   paper can state that CEE's emergency-Gini dispersion, not only its
   median, differs.
3. Re-run the regional emergency-Gini contrast **excluding the five
   desert capitals**, to state whether CEE's regional signal is the
   deserts or the region.

**Figure 5 redrawn**: same four strips, points marked by country (two-letter
label or a per-country marker inside the region colour), with a
median-and-IQR bar instead of the median line, so the country clustering
inside South and the CEE spread are visible without a second figure.

Needs: new analysis (one script, three CSV outputs, audit checks), one
figure redraw, text. Decision D9 (do all three, or the decomposition
only).

---

## R10 — Clusters vs regions in 2.3/2.4, and the map

**Diagnosis.** 2.3 opens with regions, then introduces clusters that
produce the coverage grades, then 2.4 and 2.5 use the grades while the
figures still colour by region. The reader is never told why two
partitions exist.

**Cross-check of the two partitions (from `cityvector_clustered*.csv`):**

| region | covered | partial desert | desert |
|---|---|---|---|
| North | 6 | 7 | 0 |
| West | 15 | 1 | 0 |
| South | 17 | 1 | 0 |
| CEE | 10 | 5 | 5 |

ARI between grades and regions is 0.001 (main) and 0.07 (peeled), so
they are different partitions, but the table shows they are not
unrelated: the partial-desert grade is a Nordic and CEE phenomenon
(Oslo, Stockholm, Stavanger, Göteborg, Aalborg, Norrköping, Turku;
Zagreb, Warszawa, Sofia, Łomża, Brăila; plus Luxembourg and Palermo), the
deserts are all CEE capitals, and West and South are almost entirely
covered. Against Fig 2: the five deserts are the five highest points on
the emergency-Gini axis, and the partial-desert cities fill the band
below them.

**Proposed order for 2.3** (this also answers the first sentence of 2.3):
1. **Structure from the data first**: clustering on the city vectors
   finds no types, only a one-dimensional coverage ordering (covered /
   partial / desert); the grade sets emergency deprivation cost above
   everything else (Wald p ≈ 1e-15; medians 1.02 / 1.87 / 3.37).
2. **Then the regional test**: the ordering has a geography (the
   cross-tab above); the regional contrasts that survive country
   permutation (emergency Gini, gap, ρ, compounding) and the one that
   does not (everyday Gini, explained by R9); whether the CEE contrast
   survives without the deserts (R9.3).
3. **One map figure, new**: Europe with the 67 FUAs as points, fill
   colour = coverage grade, marker shape = macro-region, point size =
   population, deserts labelled. This is the figure that shows both
   partitions at once and makes the cross-tab legible. It needs city
   coordinates; `config/cities/*.yaml` carry the FUA codes but no
   centroid, so a 67-row `paper/city_coords.csv` (FUA centroid lat/lon)
   would be added, drawn from the Eurostat FUA layer if reachable and
   otherwise hand-entered and checked.
4. Fig 2 (Gini plane) redrawn with fill = coverage grade and shape =
   region, matching the map, and placed here.

Needs: one new figure (map), one redraw (Gini plane), a coordinates
table, text. Decision D10 (map yes/no; if yes, whether grade or region is
the fill colour).

---

## R11 — Discussion headings and structure

Replace "What the results change for theory" and the numbered
"1./2./3." paragraph labels. Proposed structure and headings:

- **3.1 Deprivation as the welfare measure of urban proximity.** The
  theoretical contribution stated once as a result: welfare economics
  gives urban analysis the loss function it lacked; where minutes and
  deprivation agree (ranks) the access literature is certified at
  continental scale, where they disagree (levels, tails, inequality
  magnitudes) minutes were never a welfare measure. The framework
  travels to any domain with anchors of comparable strength.
- **3.2 What urban growth delivers, regime by regime.** The scaling
  benchmark revised: returns to size in welfare are regime-specific;
  inequality of welfare scales only in the everyday regime; the exponent
  is not a sufficient statistic. Ties to Musso et al.: in a mature urban
  system, what size still delivers is everyday welfare, and not the
  emergency regime.
- **3.3 Built for the everyday, tested by the emergency.** The resilience
  reading: two capabilities, national vs municipal geographies, the
  compounded periphery as the coupling pathology; the disruption
  statistics of R2b return here in one paragraph as the reason the
  emergency regime's floor matters now; the Preparedness Union Strategy
  as the policy address.
- **3.4 Implications for planning and preparedness** (current 3.3,
  unchanged content, heading changed).
- **3.5 Robustness and limitations** (current 3.1 and 3.4 merged; the
  envelope table stays, the robustness inventory shortens to one
  paragraph with the SI figure as its home). Moving robustness after the
  theory sections follows the Musso pattern of leading the Discussion
  with the finding rather than the defence; if you prefer robustness
  first (as the round-1 brief asked), it stays as 3.1 with a new heading
  "How much of this depends on the deprivation functions".

The Musso discussion itself could not be read (egress block); the
structure above follows the PNAS convention their abstract implies
(finding → theory → implication → caveat). Please check once.

Needs: text; decisions D11 (headings), D12 (robustness first or last).

---

## R12 — Cross-check pass before any push (unchanged from round 1)

1. Every quoted number re-grepped against `docs/paper-pack/data/*.csv`;
   new analyses (R9) added to the pack with `tools/audit_paper_pack.py`
   checks before the prose quotes them.
2. Prohibited-claims scan (brief): no "proven flat"; no regional
   everyday-Gini claim (the R9 country finding is reported as the reason
   the claim is not made); no European elderly claim; conditional
   emergency-Gini statement; no per-cell class readings; slope × grade
   interaction never headlined; "deprivation cost" whenever an emergency
   level is quoted.
3. Style scan per R7; "access" grep per R5.
4. Abstract ≤ 250 words, 0 citations; significance 50–120 words.
5. Clean compile; figure files regenerated by scripts under `paper/`
   that read only the pack CSVs and the config, never re-deriving
   statistics.

---

## New bibliography entries this round would need (all to be verified)

The brief forbids citations from memory; each of these would be added to
`references.bib` only with a checked DOI or URL. Marked (T) theory,
(S) statistics, (L) legal.

- (T) Bettencourt, L. M. A. (2013). The origins of scaling in cities.
  *Science* 340(6139), 1438–1441.
- (T) Hansen, W. G. (1959). How accessibility shapes land use. *Journal of
  the American Institute of Planners* 25(2), 73–76.
- (S) EEA (2025). Economic losses from weather- and climate-related
  extremes in Europe (indicator).
- (S) Copernicus Climate Change Service / WMO (2025). European State of
  the Climate 2024.
- (S) LSHTM / Imperial College London (2025). Climate change-driven summer
  heat caused 16,500 additional deaths across Europe (rapid attribution
  report, 854 cities).
- (S) Prehospital and Disaster Medicine (2025). Blackout in Spain: urgent
  analysis of impact on emergency medical services.
- (S) WHO Regional Office for Europe (2026). 3000 attacks on health care
  in Ukraine verified by WHO.
- (S) European Commission (2025). Preparedness Union Strategy, JOIN(2025)
  130; Niinistö (2024), Safer together.
- (S) UNDRR (2025). Global Assessment Report on Disaster Risk Reduction
  2025.
- (L) Charter of Fundamental Rights of the EU, Art. 36; European Pillar of
  Social Rights, principle 20.

---

## Decisions for the PI

| # | Decision | My recommendation |
|---|---|---|
| D1 | Abstract draft in R1: right skeleton and register? | Yes, refine wording after your read |
| D2 | Title. Current: "The two geographies of urban deprivation: everyday services and emergency care in 67 European cities". Alternatives in the new framing: "How bad is far? The welfare of urban proximity in the everyday and the emergency regime"; "Cities built for the everyday: deprivation in two regimes across 67 European cities" | Second alternative |
| D3 | Replace RQ1–4 with the three questions of R2a | Yes |
| D4 | Which disruption statistics enter the introduction; include the Ukraine conflict statistic? | EEA acceleration + 2025 heat + Valencia; conflict only as one clause in the Discussion |
| D5 | Europe justification: comparability + maturity + legal, or drop legal | Keep all three, legal in one sentence |
| D6 | Results order: 2.1 deprivation vs access, 2.2 growth (levels + inequality merged), 2.3 geography (grades then regions), 2.4 compounding | Yes |
| D7 | Fig 7 (ρ ranked) to SI | Yes |
| D8 | Fig 4 (specification curve) to SI, no inset | Yes |
| D9 | R9 analyses: variance decomposition, dispersion test, no-desert re-test | All three (one script) |
| D10 | New map figure of grades × regions; grade as fill colour | Yes, grade as fill |
| D11 | Discussion headings of R11 | Yes |
| D12 | Robustness first (3.1) or last (3.5) in the Discussion | Last |

Once agreed, the implementation order is: R9 analyses and audit checks →
figures (R4, R6, R9, R10) → text in the order abstract, introduction,
results, discussion → cross-check pass → compile → push.
