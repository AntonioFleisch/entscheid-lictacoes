import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pncp_utils import normalize_valor_estimado_centavos

def test_normalization():
    cases = [
        # (pub, detail, expected)
        ({"valorTotalEstimado": 287568.8}, None, 28756880),
        (None, {"valorTotalEstimado": "287568.8"}, 28756880),
        ({"valorTotalEstimado": "2026-03-09T09:29:00"}, None, None),
        ({"valorTotalEstimado": 0}, None, 0),
        ({}, {}, None),
        ({"valorTotalEstimado": 10.55}, {"valorTotalEstimado": 20.99}, 2099),
        (None, {"valorTotalEstimado": None}, None),
    ]
    
    for pub, det, expected in cases:
        result = normalize_valor_estimado_centavos(pub, det)
        print(f"Pub: {pub} | Det: {det} => Result: {result} (Expected: {expected})")
        assert result == expected

if __name__ == "__main__":
    try:
        test_normalization()
        print("\nAll normalization tests passed!")
    except AssertionError:
        print("\nTest failed!")
        sys.exit(1)
