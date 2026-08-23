import re
from src.config import FIELDS, MOCK_SITE_ID


class Validator:
    """Validates extracted/repaired data before marking it as reliable.
    
    Checks: format (regex), range/sanity bounds, type parsing, and drift
    against last known good value.
    """

    def __init__(self, storage):
        self.storage = storage

    def _extract_numeric(self, value):
        """Extract numeric value from string, handling $, commas, and suffixes (M/B/T/K/%)."""
        if value is None:
            return None
        try:
            val_str = str(value).replace('$', '').replace('₹', '').replace(',', '').replace('+', '').strip()
            multiplier = 1
            if val_str.lower().endswith('m'):
                multiplier = 1e6
                val_str = val_str[:-1]
            elif val_str.lower().endswith('b'):
                multiplier = 1e9
                val_str = val_str[:-1]
            elif val_str.lower().endswith('k'):
                multiplier = 1e3
                val_str = val_str[:-1]
            elif val_str.lower().endswith('t'):
                multiplier = 1e12
                val_str = val_str[:-1]
            
            # Handle percentage
            if val_str.endswith('%'):
                val_str = val_str[:-1].strip()
                # Don't multiply by 0.01 — keep as the face value for range checks
            
            val_str = val_str.strip()
            return float(val_str) * multiplier
        except (ValueError, TypeError):
            return None

    def validate_field(self, field_name, value, raw_value=None, site_id=None) -> dict:
        """Validate a single field value.
        
        Returns dict with: field_name, value, valid, status (pass/fail/flagged),
        confidence, and individual checks results.
        """
        site_id = site_id or MOCK_SITE_ID
        field_config = FIELDS.get(field_name, {})
        checks = {}

        # 1. Format check — does value match field's regex pattern?
        pattern = field_config.get("pattern")
        if pattern and value:
            checks["format_check"] = "pass" if re.search(pattern, str(value)) else "fail"
        elif not value:
            checks["format_check"] = "fail"
        else:
            checks["format_check"] = "skip"

        # 2. Type check — can the value be parsed as expected type?
        field_type = field_config.get("field_type")
        if field_type in ("numeric", "currency", "percentage", "abbreviated"):
            num_val = self._extract_numeric(value)
            checks["type_check"] = "pass" if num_val is not None else "fail"
        elif field_type == "text":
            checks["type_check"] = "pass" if value and str(value).strip() else "fail"
        else:
            checks["type_check"] = "pass" if value and str(value).strip() else "fail"

        # 3. Range check — is value within expected bounds?
        min_val = field_config.get("min_val")
        max_val = field_config.get("max_val")
        if (min_val is not None or max_val is not None) and checks.get("type_check") == "pass":
            num_val = self._extract_numeric(value)
            if num_val is not None:
                if min_val is not None and num_val < min_val:
                    checks["range_check"] = "fail"
                elif max_val is not None and num_val > max_val:
                    checks["range_check"] = "fail"
                else:
                    checks["range_check"] = "pass"
            else:
                checks["range_check"] = "skip"
        else:
            checks["range_check"] = "skip"

        # 4. Drift check — flag large changes from last known good value
        drift_threshold = field_config.get("drift_threshold")
        if drift_threshold and checks.get("type_check") == "pass":
            last_good = self.storage.get_last_good_value(site_id, field_name)
            if last_good:
                last_good_val = last_good.get("value", "")
                num_val = self._extract_numeric(value)
                last_good_num = self._extract_numeric(last_good_val)
                if num_val is not None and last_good_num is not None and last_good_num != 0:
                    change = abs((num_val - last_good_num) / last_good_num)
                    if change > drift_threshold:
                        checks["drift_check"] = "flagged"
                    else:
                        checks["drift_check"] = "pass"
                else:
                    checks["drift_check"] = "skip"
            else:
                checks["drift_check"] = "skip"
        else:
            checks["drift_check"] = "skip"

        # Compute final status and confidence
        status = "pass"
        if checks.get("format_check") == "fail" or checks.get("type_check") == "fail":
            status = "fail"
        elif any(c == "flagged" for c in checks.values()):
            status = "flagged"

        score_map = {"pass": 1.0, "fail": 0.0, "flagged": 0.5, "skip": 1.0}
        active_scores = [score_map[c] for c in checks.values() if c != "skip"]
        confidence = sum(active_scores) / len(active_scores) if active_scores else 1.0

        return {
            "field_name": field_name,
            "value": value,
            "valid": status == "pass",
            "status": status,
            "confidence": round(confidence, 4),
            "checks": checks
        }

    def validate_all(self, extraction_results, site_id=None) -> dict:
        """Validate all field extraction results."""
        results = {}
        for field_name, result in extraction_results.items():
            value = result.get("raw_value", "")
            results[field_name] = self.validate_field(
                field_name, value, site_id=site_id
            )
        return results
