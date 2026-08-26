# Every number this project uses, and where it comes from

Written because two of the figures in an earlier draft had the shape this project
has been burned by before: precise, dramatic, and uncited. One survived checking.
One did not.

**Rule: a number that cannot be defended is worse than no number.** If a figure is
not in this file with a source, it does not go in the README, the demo, or the pitch.

---

## Verified — safe to use

| Figure | Exact claim | Source |
|---|---|---|
| **$170M** | The global investigative site community spent $170M in 2024 completing feasibility assessments and site qualification visits for FDA-regulated industry-funded trials | Tufts CSDD survey, fielded April–July 2024, reported in [Applied Clinical Trials](https://www.appliedclinicaltrialsonline.com/view/benchmarking-the-investigative-site-qualification-process) |
| **2,500 hours** | Average hours per year, per investigative site, dedicated to feasibility and qualification | Same |
| **~$7,500** | Median annual financial investment per site to support feasibility assessments and site qualification visits | Same |
| **57% → 76%** | Prevalence of protocols with at least one substantial amendment, phases I–IV, rose from 57% (2015) to 76% | Tufts CSDD, [New Benchmarks on Protocol Amendment Practices](https://link.springer.com/article/10.1007/s43441-024-00622-9) |
| **82%** | Phase III protocols with at least one substantial amendment, 2018–2021, up from 66% in 2013–2015 | Same |
| **2.3 → 3.5** | Mean substantial amendments per protocol, rising to 3.5 by 2022–2023 | Same |
| **$141,000 / $535,000** | Median *direct* cost to implement one substantial amendment — **$141k Phase II, $535k Phase III**. Not a range for a single trial | Same |
| **21–26%** | Screen-failure rates across three French cancer centres in early-phase trials | [ESMO Open, 2025](https://www.esmoopen.com/article/S2059-7029(25)01200-1/fulltext) |
| **47.5%** | Current inclusion criteria deem ineligible 47.5% of patients still alive at 6 months | [Evaluating eligibility criteria of oncology trials using real-world data and AI](https://pmc.ncbi.nlm.nih.gov/articles/PMC9007176/) |
| **No AE increase** | Trials with more relaxed laboratory eligibility thresholds did not have more treatment withdrawals due to adverse events than trials with stringent thresholds | Same |
| **65%** | Gap between structured data documented for patient care and the data required for eligibility assessment | [Automatic data source identification for clinical trial eligibility criteria](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5333255/) |
| **Excluded in practice** | "Subjects with incomplete eligibility data are almost always excluded from analysis" | [Missingness in eligibility criteria for target trial emulation](https://onlinelibrary.wiley.com/doi/10.1002/sim.70500) |
| **300M+** | TriNetX network size; patient-level data never leaves the source system | [TriNetX](https://trinetx.com/data/) |

## Removed — could not be verified

| Figure | Why it is gone |
|---|---|
| **29.4 days** | Attributed in a search summary to a feasibility explainer. Does not appear in the Tufts CSDD data, and the underlying source was never opened. Unsupported. |
| **"twenty hospitals"** | Invented as illustrative prose. Reads like a statistic. Not one. |
| **70–80% of trials hit delays** | Widely repeated, no primary source located. Dropped. |
| **260 days per amendment cycle** | Not found in the amendment benchmark literature checked. Dropped. |
| **16% of amendments change eligibility criteria** | Plausible and probably real, but not located in a primary source. Dropped until it is. |
| **"3.3 amendments"** | **Wrong.** The figure is **3.5**. Corrected. |
| **"23% avoidable"** | Derived by subtracting a "77% unavoidable" figure. A separate study reports 45% avoidable. The two conflict and the derivation was mine, not the source's. Dropped — see note below. |

### On avoidability

The literature disagrees with itself. One Tufts analysis deemed **45%** of amendments
avoidable; more recent data reports **77% unavoidable**, with regulatory requests and
strategy changes as leading causes. **Do not quote an avoidability percentage.** The
defensible statement is narrower and still sufficient:

> Amendments are common, they are expensive, and eligibility criteria are among the
> things they change.

## On our own numbers

Every figure produced by TrialGrid itself — patient counts, criterion costs, relaxation
gains — comes from **synthetic cohorts we generated**. They demonstrate what the system
computes. **They are not evidence about the world**, and three synthetic sites are not a
study. See the "What we do not claim" section of the README.
