"""Saved, already-clarified state (from a Step 3.3 run) so demos can skip the questions."""

CLARIFIED_STATE = {
    "question": "I am building an AI application that may have 10,000 users. Should I use PostgreSQL or MongoDB for the backend?",
    "problem_domain": "databases",
    "requirements": {
        "expected_users": "may have 10,000 users",
        "application_type": "AI application",
        "data_types": "user accounts and billing",
        "vector_search": "no need",
        "consistency": "yes, strong transactional consistency needed",
    },
    "constraints": {"database_options": "PostgreSQL or MongoDB", "hosting": "cloud service in prod"},
    "clarification_answers": {
        "What kind of data will the app store?": "user accounts and billing",
        "Do you need vector search?": "no need",
        "Do you need strong transactional consistency?": "yes",
        "Managed cloud service or self-hosting?": "cloud service in prod",
    },
    "assumptions": ["Traffic is modest; 10,000 users is a ceiling with low-to-moderate concurrency."],
}
