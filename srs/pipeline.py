"""Pipeline orchestrator — runs the full scrape cycle:
fetch → extract → detect failures → repair → re-extract → validate → store.
"""

from src.config import MOCK_SITE_ID, MOCK_V1_SELECTORS, FIELDS
from src.storage import Storage
from src.selector_store import SelectorStore
from src.extractor import Extractor
from src.failure_detector import FailureDetector
from src.ai_repair import AIRepairEngine
from src.validator import Validator


class ScrapePipeline:
    def __init__(self, db_path=None):
        self.storage = Storage(db_path=db_path)
        self.selector_store = SelectorStore(self.storage)
        self.extractor = Extractor(self.storage, self.selector_store)
        self.detector = FailureDetector()
        self.repair_engine = AIRepairEngine(self.storage)
        self.validator = Validator(self.storage)

    def initialize(self, site_id=None, selectors=None):
        """Initialize selector store with default selectors."""
        site_id = site_id or MOCK_SITE_ID
        selectors = selectors or MOCK_V1_SELECTORS
        self.selector_store.initialize_defaults(site_id, selectors)

    def run_cycle(self, site_id=None, html=None) -> dict:
        """Run one complete scrape → detect → repair → validate cycle.
        
        Returns a comprehensive result dict for the dashboard to consume.
        """
        site_id = site_id or MOCK_SITE_ID
        cycle_number = self.storage.get_next_cycle_number(site_id)

        # 1. Fetch HTML
        html_content = self.extractor.fetch_page(local_html=html)

        # 2. Get active selectors
        selectors = self.selector_store.get_all_selectors(site_id)

        # 3. Extract all fields
        extraction_results = self.extractor.extract_all(html_content, selectors)

        # 4. Detect failures
        failure_results = self.detector.check_all(extraction_results)

        # 5. Repair failed fields
        repair_results = {}
        fields_repaired = 0
        for field_name, check_res in failure_results.items():
            if field_name == "_summary":
                continue

            if check_res["failed"]:
                old_selector = selectors.get(field_name, "")
                # Add alert for detected failure
                self.storage.add_alert(
                    site_id, field_name, "extraction_failure",
                    f"Selector '{old_selector}' failed: {', '.join(check_res['reasons'])}"
                )

                # Run AI repair
                repair_res = self.repair_engine.repair_field(
                    html_content, field_name, old_selector, site_id
                )
                repair_results[field_name] = repair_res

                if repair_res.get("success"):
                    new_selector = repair_res["new_selector"]
                    # Update selector store
                    self.selector_store.update_selector(site_id, field_name, new_selector)
                    # Re-extract with new selector
                    extraction_results[field_name] = self.extractor.extract_field(
                        html_content, field_name, new_selector
                    )
                    fields_repaired += 1
                    # Add repair success alert
                    self.storage.add_alert(
                        site_id, field_name, "repair_success",
                        f"Repaired: '{old_selector}' → '{new_selector}' "
                        f"(confidence: {repair_res['confidence']:.2f}, method: {repair_res['method']})"
                    )
                else:
                    self.storage.add_alert(
                        site_id, field_name, "repair_failed",
                        f"Could not repair selector for {field_name}: {repair_res.get('justification', 'Unknown')}"
                    )

        # 6. Validate all extracted data
        validation_results = self.validator.validate_all(extraction_results, site_id=site_id)

        # 7. Save extracted data per field
        for field_name, ext_res in extraction_results.items():
            val_res = validation_results.get(field_name, {})
            raw_value = ext_res.get("raw_value", "")
            
            self.storage.save_extracted_data(
                site_id=site_id,
                field_name=field_name,
                value=raw_value,
                raw_value=raw_value,
                selector_used=ext_res.get("selector", ""),
                confidence=val_res.get("confidence", 0.0),
                validation_status=val_res.get("status", "pending"),
                scrape_cycle=cycle_number
            )

            # Add validation alerts
            if val_res.get("status") == "fail":
                self.storage.add_alert(
                    site_id, field_name, "validation_failed",
                    f"Validation failed for '{field_name}': checks={val_res.get('checks', {})}"
                )
            elif val_res.get("status") == "flagged":
                self.storage.add_alert(
                    site_id, field_name, "validation_flagged",
                    f"Drift detected for '{field_name}'"
                )

        # 8. Resolve old alerts for fields that now pass
        for field_name, val_res in validation_results.items():
            if val_res.get("status") == "pass" and field_name not in repair_results:
                self.storage.resolve_alerts(site_id, field_name)

        # 9. Save scrape cycle status
        summary = failure_results.get("_summary", {})
        fields_failed = summary.get("failed", 0)
        fields_success = len(FIELDS) - fields_failed
        status = "success" if fields_failed == 0 else ("partial" if fields_repaired > 0 else "failed")

        self.storage.save_scrape_status(
            site_id=site_id,
            status=status,
            fields_total=len(FIELDS),
            fields_success=fields_success,
            fields_failed=fields_failed,
            fields_repaired=fields_repaired,
            cycle_number=cycle_number
        )

        return {
            "cycle_number": cycle_number,
            "status": status,
            "extraction_results": extraction_results,
            "failure_detection": failure_results,
            "repair_results": repair_results,
            "validation_results": validation_results,
            "summary": {
                "total_fields": len(FIELDS),
                "successful": fields_success,
                "failed": fields_failed,
                "repaired": fields_repaired,
            }
        }

    def get_status(self) -> dict:
        """Return current pipeline status."""
        return self.storage.get_latest_scrape_status(MOCK_SITE_ID) or {"status": "ready"}

    def reset(self):
        """Reset database and re-initialize with default selectors."""
        self.storage.reset_database()
        self.initialize()
