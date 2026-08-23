import re
import json
from bs4 import BeautifulSoup, NavigableString
from rapidfuzz import fuzz
try:
    import anthropic
except ImportError:
    anthropic = None

from src.config import FIELDS, ANTHROPIC_API_KEY, ANTHROPIC_MODEL


class AIRepairEngine:
    """AI-powered repair engine that finds new CSS selectors when old ones break.
    
    Two layers:
    1. Heuristic candidate scoring (always runs, no API key needed)
    2. LLM reasoning layer (optional, activates if ANTHROPIC_API_KEY is set)
    """

    def __init__(self, storage):
        self.storage = storage

    def _generate_css_selector(self, element, soup) -> str:
        """Generate a unique CSS selector for a BeautifulSoup element.
        
        Strategy: prefer id, then data-* attributes, then class combo, 
        then tag + nth-of-type, building a parent > child chain.
        """
        if element.get("id"):
            return f"#{element.get('id')}"

        path = []
        for el in [element] + list(element.parents):
            if el.name is None or el.name == '[document]':
                break

            # If this element has an id, use it and stop
            if el.get("id"):
                path.insert(0, f"#{el.get('id')}")
                break

            segment = el.name

            # Add data-* attributes for specificity (critical for v2-style HTML)
            data_attrs = {k: v for k, v in el.attrs.items() 
                         if k.startswith("data-") and isinstance(v, str)}
            
            classes = el.get("class", [])

            if data_attrs:
                # Use the most descriptive data attribute
                for attr_name, attr_val in data_attrs.items():
                    segment += f'[{attr_name}="{attr_val}"]'
                if classes:
                    segment = el.name + "." + ".".join(classes)
                    for attr_name, attr_val in data_attrs.items():
                        segment += f'[{attr_name}="{attr_val}"]'
            elif classes:
                segment = el.name + "." + ".".join(classes)
                # Check if classes are unique among siblings
                if el.parent:
                    same_class_siblings = el.parent.find_all(
                        el.name, class_=classes, recursive=False
                    )
                    if len(same_class_siblings) > 1:
                        # Classes are not unique; add nth-of-type
                        idx = same_class_siblings.index(el) + 1 if el in same_class_siblings else 1
                        segment += f":nth-of-type({idx})"
            else:
                siblings = el.find_previous_siblings(el.name)
                if siblings:
                    segment += f":nth-of-type({len(siblings) + 1})"

            path.insert(0, segment)

            # Test if current path already uniquely identifies the element
            test_selector = " > ".join(path)
            try:
                matches = soup.select(test_selector)
                if len(matches) == 1:
                    return test_selector
            except Exception:
                pass

        return " > ".join(path)

    def _get_nearby_text(self, element):
        """Get text from nearby elements (siblings, parent's other children) for label matching."""
        texts = []
        # Check previous siblings
        for sib in element.find_previous_siblings():
            t = sib.get_text(strip=True)
            if t:
                texts.append(t)
            if len(texts) >= 3:
                break
        # Check parent's direct text
        if element.parent:
            for child in element.parent.children:
                if isinstance(child, NavigableString):
                    t = child.strip()
                    if t:
                        texts.append(t)
                elif child != element:
                    t = child.get_text(strip=True)
                    if t and len(t) < 50:
                        texts.append(t)
        return texts

    def _find_candidates(self, html, field_name, site_id) -> list:
        """Scan the page for candidate elements and score each one.
        
        Scoring dimensions:
        (a) regex_score: match against field's expected data pattern
        (b) label_score: proximity to label text matching known synonyms
        (c) attribute_score: keyword match in element's attributes
        (d) value_similarity_score: fuzzy similarity to last known good value
        """
        soup = BeautifulSoup(html, 'html.parser')
        field_config = FIELDS.get(field_name, {})
        pattern = field_config.get("pattern", "")
        synonyms = field_config.get("synonyms", [])

        last_good = self.storage.get_last_good_value(site_id, field_name)
        last_good_value = last_good.get("value", "") if last_good else ""

        candidates = []

        # Find all text-containing elements, preferring leaf nodes
        for element in soup.find_all(True):
            # Skip non-content tags
            if element.name in ['script', 'style', 'head', 'meta', 'link', 'title']:
                continue

            text = element.get_text(strip=True)
            if not text or len(text) > 200:
                continue

            # Count child tags that have their own text (non-leaf indicator)
            child_tags = [c for c in element.children if not isinstance(c, NavigableString)]
            text_children = [c for c in child_tags if c.get_text(strip=True)]
            
            # Skip elements with many text-bearing children (they're containers, not data)
            if len(text_children) > 2:
                continue
            
            # Check if element has direct text (not just from children)
            direct_text = element.string  # None if mixed content
            has_direct_text = direct_text is not None and direct_text.strip()
            
            # Leaf penalty — strongly prefer elements with direct text content
            # Elements that contain other text-bearing children get penalized
            leaf_factor = 1.0
            if text_children:
                if has_direct_text:
                    leaf_factor = 0.7  # Has own text but also children
                else:
                    leaf_factor = 0.3  # All text comes from children — container element

            # (a) Regex score
            regex_score = 0.0
            if pattern:
                match = re.search(pattern, text)
                if match:
                    # Full match vs partial
                    matched_text = match.group(0).strip()
                    regex_score = 1.0 if matched_text == text.strip() else 0.5

            # (b) Label proximity score
            label_score = 0.0
            nearby_texts = self._get_nearby_text(element)
            for syn in synonyms:
                syn_lower = syn.lower()
                # Check nearby/sibling text
                for nearby in nearby_texts:
                    ratio = fuzz.partial_ratio(syn_lower, nearby.lower())
                    if ratio > 80:
                        label_score = max(label_score, 0.8)
                # Check parent element text (excluding this element's own text)
                if element.parent and element.parent.name not in [None, '[document]']:
                    parent_direct_text = ""
                    for child in element.parent.children:
                        if isinstance(child, NavigableString):
                            parent_direct_text += child.strip() + " "
                        elif child != element:
                            parent_direct_text += child.get_text(strip=True) + " "
                    if parent_direct_text.strip():
                        ratio = fuzz.partial_ratio(syn_lower, parent_direct_text.lower())
                        if ratio > 80:
                            label_score = max(label_score, 1.0)
                # Check grandparent
                if (element.parent and element.parent.parent 
                    and element.parent.parent.name not in [None, '[document]']):
                    gp_text = element.parent.parent.get_text(strip=True).lower()
                    ratio = fuzz.partial_ratio(syn_lower, gp_text)
                    if ratio > 80:
                        label_score = max(label_score, 0.4)

            # (c) Attribute score
            attribute_score = 0.0
            # Check element's own attributes and ancestors
            for el in [element] + list(element.parents)[:3]:
                if el.name is None or el.name == '[document]':
                    break
                attr_text = ""
                for attr_name, attr_val in el.attrs.items():
                    if isinstance(attr_val, list):
                        attr_text += " ".join(attr_val) + " "
                    else:
                        attr_text += str(attr_val) + " "
                    attr_text += attr_name + " "
                attr_text = attr_text.lower()

                # Check field name keywords
                field_keywords = field_name.lower().replace("_", " ").split()
                for kw in field_keywords:
                    if kw in attr_text:
                        attribute_score = max(attribute_score, 1.0 if el == element else 0.6)

                # Check synonyms in attributes
                for syn in synonyms:
                    syn_parts = syn.lower().split()
                    for part in syn_parts:
                        if len(part) > 2 and part in attr_text:
                            attribute_score = max(attribute_score, 0.7 if el == element else 0.4)

            # (d) Value similarity score
            value_sim_score = 0.0
            if last_good_value:
                if field_config.get("field_type") in ("currency", "numeric", "percentage", "abbreviated"):
                    # Numeric comparison
                    try:
                        new_nums = re.findall(r'[\d.]+', text)
                        old_nums = re.findall(r'[\d.]+', str(last_good_value))
                        if new_nums and old_nums:
                            new_n = float(new_nums[0])
                            old_n = float(old_nums[0])
                            if old_n != 0:
                                closeness = 1.0 - min(abs(new_n - old_n) / old_n, 1.0)
                                value_sim_score = closeness
                    except (ValueError, IndexError):
                        pass
                else:
                    # Text comparison
                    value_sim_score = fuzz.ratio(str(last_good_value).lower(), text.lower()) / 100.0

            confidence = (0.35 * regex_score + 0.25 * label_score 
                         + 0.25 * attribute_score + 0.15 * value_sim_score)
            confidence *= leaf_factor  # Penalize non-leaf container elements

            if confidence > 0.05:  # Skip very low confidence candidates
                candidates.append({
                    "element_text": text,
                    "element_html": str(element),
                    "css_selector": self._generate_css_selector(element, soup),
                    "confidence": round(confidence, 4),
                    "scores": {
                        "regex": round(regex_score, 3),
                        "label": round(label_score, 3),
                        "attribute": round(attribute_score, 3),
                        "value_similarity": round(value_sim_score, 3)
                    }
                })

        # Deduplicate by selector and sort by confidence
        seen = set()
        unique_candidates = []
        for c in sorted(candidates, key=lambda x: x["confidence"], reverse=True):
            if c["css_selector"] not in seen:
                seen.add(c["css_selector"])
                unique_candidates.append(c)

        return unique_candidates

    def _llm_repair(self, candidates, field_name, html_snippet):
        """Optional LLM layer that refines heuristic candidates using Claude.
        
        Only activates if ANTHROPIC_API_KEY is set. Falls back gracefully on any error.
        """
        if not ANTHROPIC_API_KEY or not anthropic:
            return None

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            field_config = FIELDS.get(field_name, {})

            prompt = (
                f"You are a web scraping expert. A financial data field needs to be extracted from a changed webpage.\n\n"
                f"Field: {field_config.get('display_name', field_name)}\n"
                f"Expected format pattern: {field_config.get('pattern')}\n"
                f"Known label synonyms: {', '.join(field_config.get('synonyms', []))}\n"
                f"Field type: {field_config.get('field_type')}\n\n"
                f"Top candidates found by heuristic analysis:\n"
            )

            for i, cand in enumerate(candidates[:3]):
                prompt += (
                    f"\n[{i}] Text: \"{cand['element_text']}\"\n"
                    f"    HTML: {cand['element_html'][:200]}\n"
                    f"    Heuristic scores: {cand['scores']}\n"
                )

            prompt += (
                f"\n\nBased on the field description and candidates above, pick the correct element.\n"
                f"Respond with ONLY valid JSON: {{\"chosen_index\": <int>, \"confidence\": <float 0-1>, \"justification\": \"<brief reason>\"}}"
            )

            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            resp_text = response.content[0].text
            match = re.search(r'\{.*\}', resp_text, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                if "chosen_index" in result:
                    return result
        except Exception:
            pass

        return None

    def repair_field(self, html, field_name, old_selector, site_id) -> dict:
        """Main repair method. Runs heuristic layer, optionally LLM layer.
        
        Returns dict with: success, new_selector, extracted_value, confidence,
        method, justification, candidates_found, old_selector.
        """
        candidates = self._find_candidates(html, field_name, site_id)
        if not candidates:
            result = {
                "success": False, "method": "none", "new_selector": None,
                "extracted_value": None, "confidence": 0.0,
                "justification": "No candidates found on page",
                "candidates_found": 0, "old_selector": old_selector
            }
            self.storage.log_repair(
                site_id, field_name, old_selector, "", "none", 0.0,
                "No candidates found", success=False
            )
            return result

        top_cand = candidates[0]
        method = "heuristic"
        confidence = top_cand["confidence"]
        justification = (
            f"Best heuristic match (scores: regex={top_cand['scores']['regex']:.2f}, "
            f"label={top_cand['scores']['label']:.2f}, "
            f"attr={top_cand['scores']['attribute']:.2f}, "
            f"similarity={top_cand['scores']['value_similarity']:.2f})"
        )

        # Try LLM layer
        llm_result = self._llm_repair(candidates[:3], field_name, html[:3000])
        if llm_result and "chosen_index" in llm_result:
            idx = llm_result["chosen_index"]
            if 0 <= idx < len(candidates[:3]):
                top_cand = candidates[idx]
                method = "heuristic+llm"
                confidence = float(llm_result.get("confidence", confidence))
                justification = llm_result.get("justification", justification)

        success = confidence > 0.3

        result = {
            "success": success,
            "new_selector": top_cand["css_selector"],
            "extracted_value": top_cand["element_text"],
            "confidence": round(confidence, 4),
            "method": method,
            "justification": justification,
            "candidates_found": len(candidates),
            "old_selector": old_selector
        }

        # Log the repair attempt
        self.storage.log_repair(
            site_id, field_name, old_selector, top_cand["css_selector"],
            method, confidence, justification, success=success
        )

        return result
