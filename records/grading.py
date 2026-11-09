"""Grade computation kept separate so it can be unit tested and reused."""
from decimal import Decimal

from django.conf import settings


def compute_grade(total):
    """Return (letter grade, grade point) for a total score, using settings.GRADING_SCALE."""
    total = Decimal(total)
    for minimum, letter, point in settings.GRADING_SCALE:
        if total >= minimum:
            return letter, point
    return settings.GRADING_SCALE[-1][1], settings.GRADING_SCALE[-1][2]
