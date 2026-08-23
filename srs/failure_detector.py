import re
from src.config import FIELDS

class FailureDetector:
    def __init__(self):
        pass

    def check_field(self, field_name, extraction_result) -> dict:
        reasons = []
        severity = "ok"
        
        if not extraction_result.get("success"):
            reasons.append("Selector matched no elements")
            severity = "critical"
        elif not extraction_result.get("raw_value") or str(extraction_result.get("raw_value")).isspace():
            reasons.append("Extracted value is empty")
            severity = "critical"
        else:
            field_config = FIELDS.get(field_name, {})
            pattern = field_config.get("pattern")
            if pattern:
                if not re.search(pattern, str(extraction_result["raw_value"])):
                    reasons.append("Value doesn't match expected format")
                    if severity != "critical":
                        severity = "warning"
                        
        failed = (severity == "critical")
        
        return {
            "field_name": field_name,
            "failed": failed,
            "reasons": reasons,
            "severity": severity
        }

    def check_all(self, extraction_results) -> dict:
        results = {}
        total = len(extraction_results)
        passed = 0
        failed = 0
        warned = 0
        
        for field_name, result in extraction_results.items():
            check_res = self.check_field(field_name, result)
            results[field_name] = check_res
            if check_res["severity"] == "critical":
                failed += 1
            elif check_res["severity"] == "warning":
                warned += 1
            else:
                passed += 1
                
        results["_summary"] = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warned": warned
        }
        return results
