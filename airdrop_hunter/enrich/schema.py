"""AI 輸出的 JSON Schema（Claude structured outputs 會保證輸出符合這個格式）。"""

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "kind", "status", "confirmed", "backing_level", "backers", "backing_note",
                 "difficulty", "difficulty_note", "time_commitment", "cost_type", "cost_note", "steps",
                 "reward", "distribution", "requirements", "deadline", "risk_level", "risks",
                 "official_links", "tips"],
    "properties": {
        "summary": {"type": "string", "description": "項目介紹：做什麼的、為什麼可能空投（2-4 句）"},
        "kind": {"type": "string", "enum": ["defi", "p2e"]},
        "status": {"type": "string", "enum": ["ongoing", "upcoming", "potential", "claimable", "ended", "unknown"]},
        "confirmed": {"type": "string", "enum": ["confirmed", "unconfirmed", "speculative"]},
        "backing_level": {"type": "string", "enum": ["top", "notable", "some", "none_known"]},
        "backers": {"type": "array", "items": {"type": "string"}},
        "backing_note": {"type": "string"},
        "difficulty": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "difficulty_note": {"type": "string"},
        "time_commitment": {"type": "string"},
        "cost_type": {"type": "string", "enum": ["free", "gas_only", "deposit", "paid", "unknown"]},
        "cost_note": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "reward": {"type": "string"},
        "distribution": {"type": "string"},
        "requirements": {"type": "array", "items": {"type": "string"}},
        "deadline": {"type": "string"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "risks": {"type": "array", "items": {"type": "string"}},
        "official_links": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "url"],
                "properties": {"label": {"type": "string"}, "url": {"type": "string"}},
            },
        },
        "tips": {"type": "string"},
    },
}

POSTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["posts"],
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["post_id", "relevant", "title_zh", "summary_zh", "projects"],
                "properties": {
                    "post_id": {"type": "string"},
                    "relevant": {"type": "boolean"},
                    "title_zh": {"type": "string"},
                    "summary_zh": {"type": "string"},
                    "projects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "kind", "status", "confirmed", "actions", "chains",
                                         "backers", "links", "scam_risk"],
                            "properties": {
                                "name": {"type": "string"},
                                "kind": {"type": "string", "enum": ["defi", "p2e"]},
                                "status": {"type": "string",
                                           "enum": ["ongoing", "upcoming", "potential", "claimable", "ended", "unknown"]},
                                "confirmed": {"type": "string", "enum": ["confirmed", "unconfirmed", "speculative"]},
                                "actions": {"type": "string"},
                                "chains": {"type": "array", "items": {"type": "string"}},
                                "backers": {"type": "array", "items": {"type": "string"}},
                                "links": {"type": "array", "items": {"type": "string"}},
                                "scam_risk": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
        }
    },
}
