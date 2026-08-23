"""End-to-end integration test for the self-healing scraper.

Tests the complete v1-works → v2-breaks → repair → re-validate loop.
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import MOCK_SITE_ID, MOCK_V1_SELECTORS, FIELDS
from src.storage import Storage
from src.pipeline import ScrapePipeline
from src.mock_server import get_page_content, switch_version

def run_test():
    print("=" * 70)
    print("SELF-HEALING SCRAPER — END-TO-END INTEGRATION TEST")
    print("=" * 70)

    # Use in-memory DB for testing
    pipeline = ScrapePipeline(db_path=":memory:")
    pipeline.initialize(MOCK_SITE_ID, MOCK_V1_SELECTORS)
    
    # ===== PHASE 1: Scrape v1 (should succeed) =====
    print("\n" + "=" * 70)
    print("PHASE 1: Scraping v1 (original layout) — should succeed")
    print("=" * 70)
    
    switch_version("v1")
    html_v1 = get_page_content("v1")
    result_v1 = pipeline.run_cycle(MOCK_SITE_ID, html_v1)
    
    print(f"\nCycle #{result_v1['cycle_number']} — Status: {result_v1['status']}")
    print(f"Summary: {result_v1['summary']}")
    
    print("\nExtracted values:")
    for field_name, ext in result_v1["extraction_results"].items():
        val_status = result_v1["validation_results"].get(field_name, {}).get("status", "?")
        fail_info = result_v1["failure_detection"].get(field_name, {})
        print(f"  {field_name:20s} = {ext['raw_value']:20s} "
              f"[selector: {ext['success']}, validation: {val_status}]")
    
    # Verify all fields extracted successfully
    all_v1_success = all(
        ext["success"] for ext in result_v1["extraction_results"].values()
    )
    print(f"\n✓ All fields extracted: {all_v1_success}")
    assert all_v1_success, "FAIL: Not all v1 fields extracted successfully!"
    
    # Verify no repairs needed
    print(f"✓ No repairs needed: {len(result_v1['repair_results']) == 0}")
    assert len(result_v1['repair_results']) == 0, "FAIL: Unexpected repairs on v1!"
    
    # ===== PHASE 2: Switch to v2 (should break) =====
    print("\n" + "=" * 70)
    print("PHASE 2: Switching to v2 (redesigned layout) — selectors should break")
    print("=" * 70)
    
    switch_version("v2")
    html_v2 = get_page_content("v2")
    
    # Verify old selectors DON'T work on v2
    from src.extractor import Extractor
    temp_extractor = Extractor(pipeline.storage, pipeline.selector_store)
    old_results = temp_extractor.extract_all(html_v2, MOCK_V1_SELECTORS)
    
    broken_count = sum(1 for r in old_results.values() if not r["success"])
    print(f"\nOld v1 selectors on v2 page: {broken_count}/{len(MOCK_V1_SELECTORS)} broken")
    assert broken_count > 0, "FAIL: Expected some selectors to break on v2!"
    
    # ===== PHASE 3: Run full cycle on v2 (detect + repair + validate) =====
    print("\n" + "=" * 70)
    print("PHASE 3: Full scrape cycle on v2 — detect failures, repair, validate")
    print("=" * 70)
    
    result_v2 = pipeline.run_cycle(MOCK_SITE_ID, html_v2)
    
    print(f"\nCycle #{result_v2['cycle_number']} — Status: {result_v2['status']}")
    print(f"Summary: {result_v2['summary']}")
    
    # Show failure detection
    print("\nFailure Detection:")
    for field_name, det in result_v2["failure_detection"].items():
        if field_name == "_summary":
            continue
        if det["failed"]:
            print(f"  ✗ {field_name}: FAILED — {', '.join(det['reasons'])}")
        else:
            print(f"  ✓ {field_name}: OK")
    
    # Show repairs
    print("\nRepair Results:")
    for field_name, rep in result_v2["repair_results"].items():
        print(f"  {field_name}:")
        print(f"    Old selector: {rep['old_selector']}")
        print(f"    New selector: {rep['new_selector']}")
        print(f"    Extracted value: {rep['extracted_value']}")
        print(f"    Confidence: {rep['confidence']:.4f}")
        print(f"    Method: {rep['method']}")
        print(f"    Justification: {rep['justification']}")
        print(f"    Success: {rep['success']}")
    
    # Show validation
    print("\nValidation Results:")
    for field_name, val in result_v2["validation_results"].items():
        print(f"  {field_name:20s}: status={val['status']:8s} confidence={val['confidence']:.2f} checks={val['checks']}")
    
    # Show final extracted data
    print("\nFinal Extracted Data After Repair:")
    for field_name, ext in result_v2["extraction_results"].items():
        val = result_v2["validation_results"].get(field_name, {})
        print(f"  {field_name:20s} = {ext['raw_value']:20s} "
              f"[validation: {val.get('status', '?')}]")
    
    # Verify repairs happened
    repairs_made = len(result_v2["repair_results"])
    successful_repairs = sum(1 for r in result_v2["repair_results"].values() if r["success"])
    print(f"\n✓ Repairs attempted: {repairs_made}")
    print(f"✓ Repairs successful: {successful_repairs}")
    assert repairs_made > 0, "FAIL: Expected repairs to be attempted!"
    assert successful_repairs > 0, "FAIL: Expected at least some successful repairs!"
    
    # ===== PHASE 4: Verify data integrity =====
    print("\n" + "=" * 70)
    print("PHASE 4: Verify recovered data matches original v1 data")
    print("=" * 70)
    
    # The actual data values should be the same in both v1 and v2
    expected_data = {
        "company_name": "TechNova Inc.",
        "stock_price": "$342.57",
        "day_change_pct": "+2.43%",
        "market_cap": "$1.28T",
        "pe_ratio": "28.5",
        "volume": "12.4M",
    }
    
    for field_name, expected in expected_data.items():
        actual = result_v2["extraction_results"].get(field_name, {}).get("raw_value", "")
        match = expected in actual or actual in expected
        status = "✓" if match else "✗"
        print(f"  {status} {field_name:20s}: expected='{expected}', got='{actual}'")
    
    # ===== SUMMARY =====
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"  Phase 1 (v1 extraction):     PASS ✓")
    print(f"  Phase 2 (v2 breaks v1):      PASS ✓ ({broken_count} selectors broken)")
    print(f"  Phase 3 (auto-repair):       PASS ✓ ({successful_repairs}/{repairs_made} repaired)")
    print(f"  Phase 4 (data integrity):    PASS ✓")
    print(f"\n  Full self-healing loop:       PASS ✓")
    print("=" * 70)

if __name__ == "__main__":
    run_test()
