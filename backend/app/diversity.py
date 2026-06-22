"""Bias & diversity analysis.

We do NOT infer protected attributes. Instead we flag *background homogeneity*
in the shortlist and surface qualified candidates with non-traditional
backgrounds that a naive ranking would bury — which is what the assignment asks
for ("flag a homogeneous shortlist; surface non-traditional candidates").
"""
from __future__ import annotations

import re
from collections import Counter

from app.store import Candidate

# Signals that a candidate has a non-traditional background.
_NONTRAD_PATTERNS = [
    r"bootcamp", r"self[- ]taught", r"self taught", r"community college",
    r"associate'?s", r"ged\b", r"no degree", r"career (change|switch|transition)",
    r"military", r"veteran", r"apprenticeship",
]
_ELITE_HINT = ["bachelor", "master", "phd", "b.tech", "m.tech", "msc", "bsc", "mba", "doctor"]


def _degree_level(c: Candidate) -> str:
    text = " ".join(
        f"{e.degree} {e.field} {e.institution}" for e in c.parsed.education
    ).lower()
    if any(k in text for k in ["phd", "doctor"]):
        return "doctorate"
    if any(k in text for k in ["master", "msc", "m.tech", "mba", "ms "]):
        return "masters"
    if any(k in text for k in ["bachelor", "bsc", "b.tech", "be ", "bs "]):
        return "bachelors"
    if c.parsed.education:
        return "other"
    return "none"


def is_non_traditional(c: Candidate) -> bool:
    blob = " ".join([
        c.parsed.headline,
        " ".join(c.parsed.achievements),
        " ".join(f"{e.degree} {e.field} {e.institution}" for e in c.parsed.education),
        " ".join(c.parsed.certifications),
    ]).lower()
    if any(re.search(p, blob) for p in _NONTRAD_PATTERNS):
        return True
    # No formal degree listed but still skilled => non-traditional path.
    if not c.parsed.education and not any(k in blob for k in _ELITE_HINT):
        return True
    return False


def analyze(candidates: list[Candidate], shortlist_size: int) -> dict:
    ranked = sorted(candidates, key=lambda c: c.rank or 9999)
    shortlist = ranked[:shortlist_size]
    rest = ranked[shortlist_size:]
    flags: list[dict] = []

    # --- Hidden gems: strong on skills but pushed below the shortlist, or a
    # non-traditional background that a pedigree-biased reader would skip.
    hidden = []
    for c in rest:
        skills = c.scores.skills if c.scores else 0
        overall = c.scores.overall if c.scores else 0
        if (skills >= 65 and overall >= 55) or (is_non_traditional(c) and overall >= 55):
            c.is_hidden_gem = True
            hidden.append(c)
    hidden = hidden[:6]

    # --- Education homogeneity in the shortlist
    if len(shortlist) >= 4:
        levels = Counter(_degree_level(c) for c in shortlist)
        top_level, top_count = levels.most_common(1)[0]
        frac = top_count / len(shortlist)
        if frac >= 0.8 and top_level not in ("none", "other"):
            flags.append({
                "severity": "warning",
                "title": "Homogeneous education profile",
                "detail": (f"{top_count} of {len(shortlist)} shortlisted candidates share a "
                           f"'{top_level}' education profile. Consider whether equally capable "
                           f"candidates with different backgrounds are being overlooked."),
            })

    # --- Non-traditional candidates excluded despite being qualified
    qualified_nontrad_excluded = [c for c in hidden if is_non_traditional(c)]
    if qualified_nontrad_excluded:
        names = ", ".join(c.parsed.name for c in qualified_nontrad_excluded[:3])
        flags.append({
            "severity": "warning",
            "title": "Qualified non-traditional candidates below the shortlist",
            "detail": (f"{len(qualified_nontrad_excluded)} candidate(s) with strong skills but "
                       f"non-traditional backgrounds rank just outside the shortlist ({names}). "
                       f"Worth a closer look."),
        })

    # --- Experience clustering
    if len(shortlist) >= 4:
        bands = Counter(_exp_band(c.parsed.years_of_experience) for c in shortlist)
        band, cnt = bands.most_common(1)[0]
        if cnt / len(shortlist) >= 0.85:
            flags.append({
                "severity": "info",
                "title": "Narrow experience range",
                "detail": f"Most of the shortlist falls in the '{band}' experience band.",
            })

    if not flags:
        flags.append({
            "severity": "info",
            "title": "No major skew detected",
            "detail": "The shortlist shows a reasonable spread of backgrounds and experience.",
        })

    skewed = any(f["severity"] == "warning" for f in flags)

    distribution = {
        "education": dict(Counter(_degree_level(c) for c in ranked)),
        "experience": dict(Counter(_exp_band(c.parsed.years_of_experience) for c in ranked)),
        "score_bands": dict(Counter(_score_band(c.scores.overall if c.scores else 0) for c in ranked)),
    }

    return {
        "skewed": skewed,
        "flags": flags,
        "hidden_gem_ids": [c.id for c in hidden],
        "shortlist_size": len(shortlist),
        "distribution": distribution,
    }


def _exp_band(years: float) -> str:
    if years < 2:
        return "0-2y"
    if years < 5:
        return "2-5y"
    if years < 8:
        return "5-8y"
    if years < 12:
        return "8-12y"
    return "12y+"


def _score_band(score: float) -> str:
    if score >= 80:
        return "80-100"
    if score >= 65:
        return "65-80"
    if score >= 50:
        return "50-65"
    return "<50"
