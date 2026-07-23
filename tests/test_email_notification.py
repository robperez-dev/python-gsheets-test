import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sheet import build_notification_email


def test_build_notification_email_contains_expected_details():
    subject, body = build_notification_email(
        persona_nombre='Flia Perez Paredes',
        persona_codigo='002',
        monto=250.5,
        mes='enero',
        domingo='D1',
        tesorero_email='robertoperezparedes@gmail.com',
    )

    assert 'robertoperezparedes@gmail.com' in subject or 'robertoperezparedes@gmail.com' in body
    assert 'Flia Perez Paredes' in body
    assert '002' in body
    assert '250,50' in body
    assert 'enero' in body.lower()
    assert 'D1' in body
    assert '📬' in body or '💰' in body or '🏛️' in body
