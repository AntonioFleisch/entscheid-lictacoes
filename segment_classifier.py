import re
import json
import unicodedata

def strong_normalize_text(text: str) -> str:
    """
    1) lowercase
    2) remove accents
    3) convert any character outside [a-z0-9 ] to space
    4) collapse spaces
    """
    if not text:
        return ""
    text = text.lower()
    text = "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    # Replace anything not a-z, 0-9, or space with space
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Collapse spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

class SegmentRule:
    def __init__(self, segment_id: str, priority: int, match_mode: str, terms: list, min_hits: int = 1):
        self.segment_id = segment_id
        self.priority = priority
        self.match_mode = match_mode.upper() # ANY, ALL
        self.min_hits = max(1, min_hits)
        self.excludes = []
        self.required = []
        self.includes = []
        self.groups = {} # group_id -> list of terms
        
        for term_dict in terms:
            t_type = term_dict['term_type']
            val = term_dict['term']
            g_id = term_dict.get('group_id')
            
            # Prepare matchers
            # if single word: store as string for fast membership check in set(tokens)
            # if multi-word: store as compiled regex
            normalized_val = strong_normalize_text(val)
            if not normalized_val:
                continue
                
            is_multi = ' ' in normalized_val
            if is_multi:
                # regex padded with word boundaries -> handle spaces
                pattern_str = r'\b' + re.escape(normalized_val).replace(r'\ ', r'\s+') + r'\b'
                matcher = ('regex', re.compile(pattern_str))
            else:
                matcher = ('exact', normalized_val)

            t_obj = {'matcher': matcher, 'raw': val}

            if t_type == 'exclude':
                self.excludes.append(t_obj)
            elif t_type == 'required':
                self.required.append(t_obj)
            elif t_type == 'include':
                if g_id:
                    if g_id not in self.groups:
                        self.groups[g_id] = []
                    self.groups[g_id].append(t_obj)
                else:
                    self.includes.append(t_obj)

    def _matches_term(self, t_obj, text: str, tokens_set: set) -> bool:
        m_type, val = t_obj['matcher']
        if m_type == 'exact':
            return val in tokens_set
        else: # regex
            return bool(val.search(text))

    def evaluate(self, text: str, tokens_set: set) -> tuple[bool, list]:
        """Returns True if matches, and a list of matched term raw strings as evidence."""
        matches = []
        
        # 1. Check excludes -> Immediate False if any match
        for t in self.excludes:
            if self._matches_term(t, text, tokens_set):
                return False, []
                
        # 2. Check required -> All must match
        for t in self.required:
            if self._matches_term(t, text, tokens_set):
                matches.append(t['raw'])
            else:
                return False, []
                
        # 3. Check Groups -> At least 1 per group must match
        for g_id, t_list in self.groups.items():
            g_match = False
            for t in t_list:
                if self._matches_term(t, text, tokens_set):
                    matches.append(t['raw'])
                    g_match = True
                    break # one is enough
            if not g_match:
                return False, []
                
        # 4. Check includes according to match_mode
        # Notice: if match_mode is ALL, and there are NO includes, it technically matches (since required/groups matched).
        # We assume if terms are grouped or required, they fulfill the segment definition.
        if self.includes:
            if self.match_mode == 'ALL':
                # all includes must match
                for t in self.includes:
                    if self._matches_term(t, text, tokens_set):
                        matches.append(t['raw'])
                    else:
                        return False, []
                # ALL implies it hit all required include terms. We bypass min_hits checks, or assume hits == len(includes) >= min_hits.
                if len(self.includes) < self.min_hits:
                    return False, []
                    
            elif self.match_mode == 'ANY':
                # at least 'min_hits' unique includes must match
                hits = 0
                for t in self.includes:
                    if self._matches_term(t, text, tokens_set):
                        matches.append(t['raw'])
                        hits += 1
                        
                if hits < self.min_hits:
                    return False, []

        # If it reached here, it didn't fail required/excludes/groups/match_mode
        # BUT edge case: ANY segment with strictly NO groups/required matched and NO includes were passed? 
        # If there are includes, they must have matched. If there are no includes, it's valid as long as we had required/groups.
        if not matches and not self.required and not self.groups and self.excludes_only_or_empty():
             # If a segment is empty of terms entirely, it's a fallback. Returning True for fallback.
             # but "diversos" has no terms.
             pass
                
        return True, list(set(matches))

    def excludes_only_or_empty(self):
        return len(self.required) == 0 and len(self.includes) == 0 and len(self.groups) == 0


class DeterministicClassifier:
    def __init__(self, frozen_rules: list[dict]):
        """
        frozen_rules is a list of dictionaries. Each dict:
        {
          "segment_id": "slug",
          "priority": 100,
          "match_mode": "ANY",
          "terms": [
            {"term": "x", "term_type": "include", "group_id": None}
          ]
        }
        """
        self.rules = []
        self.fallback = None
        for r in frozen_rules:
            # Detect various fallback (no terms at all but prioritize 0)
            if r.get('segment_id') == 'diversos':
                self.fallback = r.get('segment_id')
            self.rules.append(SegmentRule(r['segment_id'], r['priority'], r['match_mode'], r['terms'], r.get('min_hits', 1)))
            
        # Sort rules strictly by priority DESC so we evaluate highest priority first
        self.rules.sort(key=lambda x: x.priority, reverse=True)

    def classify(self, text: str) -> tuple[str, list]:
        """Returns segment_id (or None) and the matched evidence list."""
        if not text or not text.strip():
            return None, []
            
        norm_text = strong_normalize_text(text)
        if not norm_text:
            return None, []
            
        tokens = set(norm_text.split())
        
        for rule in self.rules:
            # We don't evaluate fallback rule via text matching if it has no terms
            if rule.segment_id == self.fallback and rule.excludes_only_or_empty():
                continue
                
            is_match, evidence = rule.evaluate(norm_text, tokens)
            if is_match:
                return rule.segment_id, evidence
                
        # If it didn't hit any rule, check if fallback exists
        if self.fallback:
            return self.fallback, []
            
        return None, []

# ---- API / Ingestion Integration Facade ----

def fetch_frozen_rules(conn, ws_id: str) -> list[dict]:
    """Helper to fetch rules from DB to construct the classifier."""
    cur = conn.execute("SELECT id, slug, priority, match_mode, min_hits FROM segments WHERE is_active IS TRUE AND workspace_id=%s", (ws_id,))
    segments = cur.fetchall()
    
    rules = []
    for s in segments:
        cur_t = conn.execute("SELECT term, term_type, group_id FROM segment_terms WHERE segment_id = %s", (s['id'],))
        terms = [dict(row) for row in cur_t.fetchall()]
        rules.append({
            "segment_id": s['slug'],
            "priority": s['priority'],
            "match_mode": s['match_mode'],
            "min_hits": s['min_hits'],
            "terms": terms
        })
    return rules

def classify_segment_with_db(text: str, conn, ws_id: str) -> tuple[str, list]:
    """Utility for single-item classification."""
    rules = fetch_frozen_rules(conn, ws_id)
    classifier = DeterministicClassifier(rules)
    return classifier.classify(text)

def classify_segment(text: str) -> tuple[str, list]:
    """
    Deprecated! Retained for backward compat until ingestion fully decoupled.
    You MUST pass conn now or use classify_segment_with_db.
    """
    raise NotImplementedError("classify_segment without DB connection is removed in Phase 3.")

def finalize_contract_segment(objeto: str, items_text_list: list) -> tuple[str, str]:
    """
    Deprecated signature! 
    Requires `conn` parameter or frozen rules injection.
    """
    raise NotImplementedError("Use finalize_contract_segment_frozen instead.")

def finalize_contract_segment_frozen(classifier: DeterministicClassifier, objeto: str, items_text_list: list, modalidade_nome: str = "") -> tuple[str, str]:
    """
    Aggregates text from all items, uses the instantiated classifier.
    If no items exist or items are empty, fallback = None ('Sem classificação').
    If items exist but don't match -> 'diversos' (or whatever fallback rule is).
    """
    # Override completely if modalidade_nome is missing
    if modalidade_nome is None:
        return 'unclassified', "{}"

    # 1. Determine if we have analyzable items
    valid_items = [t for t in items_text_list if (t and isinstance(t, str) and t.strip())]
    
    if not valid_items:
        # Require: Se NÃO tem itens analisáveis -> segment_id = NULL
        return None, "{}"
        
    # Concatenate items. User explicitly requested: "A classificação deve ser derivada PRINCIPALMENTE dos seus ITENS"
    # We append objeto just as fallback or edge case enrichment
    full_text = " || ".join(valid_items) + " || " + (objeto or "")
    
    seg_id, matches = classifier.classify(full_text)
    
    evidence = {
        'matches': matches,
        'source_length': len(full_text)
    }
    
    return seg_id, json.dumps(evidence)
