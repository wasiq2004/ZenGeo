"""The seven GEO pillars, in report order.

Weights come from spec section 2 and must sum to 1.0 - `PILLAR_WEIGHTS` is
asserted at import so a future edit cannot silently skew every score.
"""

from app.audit.pillars.base import (
    Effort,
    Impact,
    Pillar,
    PillarCheck,
    PillarResult,
    Recommendation,
    ScoreBuilder,
)
from app.audit.pillars.crawlability import CrawlabilityPillar
from app.audit.pillars.entity_authority import EntityAuthorityPillar
from app.audit.pillars.evidence import EvidencePillar
from app.audit.pillars.extractability import ExtractabilityPillar
from app.audit.pillars.llms_txt import LlmsTxtPillar
from app.audit.pillars.share_of_voice import ShareOfVoicePillar
from app.audit.pillars.structured_data import StructuredDataPillar

#: The six pillars that need no API key. Share of Voice is constructed
#: separately because it needs the user's provider adapters.
AUTOMATED_PILLARS: tuple[type[Pillar], ...] = (
    CrawlabilityPillar,
    LlmsTxtPillar,
    StructuredDataPillar,
    ExtractabilityPillar,
    EvidencePillar,
    EntityAuthorityPillar,
)

PILLAR_WEIGHTS = {
    CrawlabilityPillar.key: CrawlabilityPillar.weight,
    LlmsTxtPillar.key: LlmsTxtPillar.weight,
    StructuredDataPillar.key: StructuredDataPillar.weight,
    ExtractabilityPillar.key: ExtractabilityPillar.weight,
    EvidencePillar.key: EvidencePillar.weight,
    EntityAuthorityPillar.key: EntityAuthorityPillar.weight,
    ShareOfVoicePillar.key: ShareOfVoicePillar.weight,
}

# A weight typo would quietly rescale every user's score, so fail loudly here.
if abs(sum(PILLAR_WEIGHTS.values()) - 1.0) > 1e-9:
    raise RuntimeError(
        f"Pillar weights must sum to 1.0, got {sum(PILLAR_WEIGHTS.values())}"
    )

__all__ = [
    "AUTOMATED_PILLARS",
    "PILLAR_WEIGHTS",
    "CrawlabilityPillar",
    "Effort",
    "EntityAuthorityPillar",
    "EvidencePillar",
    "ExtractabilityPillar",
    "Impact",
    "LlmsTxtPillar",
    "Pillar",
    "PillarCheck",
    "PillarResult",
    "Recommendation",
    "ScoreBuilder",
    "ShareOfVoicePillar",
    "StructuredDataPillar",
]
