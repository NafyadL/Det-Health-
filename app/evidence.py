"""Offline evidence notes about population-level behavioral health associations."""

EVIDENCE_CATALOG = [
    {
        "category": "activity",
        "title": "Physical activity",
        "summary": (
            "WHO reports that regular physical activity in adults is associated "
            "with lower risks of all-cause and cardiovascular mortality, "
            "hypertension, some cancers, and type 2 diabetes, and with improved "
            "mental health, cognitive health, and sleep."
        ),
        "health_domains": [
            "cardiovascular",
            "metabolic",
            "some cancers",
            "mental and cognitive health",
            "sleep",
        ],
        "source_name": "World Health Organization — Physical activity",
        "source_url": "https://www.who.int/news-room/fact-sheets/detail/physical-activity",
    },
    {
        "category": "sleep",
        "title": "Sleep",
        "summary": (
            "CDC says getting enough sleep can help improve heart health and "
            "metabolism and lower the risk of chronic conditions including "
            "type 2 diabetes, heart disease, high blood pressure, and stroke. "
            "Sleep duration alone does not describe sleep quality."
        ),
        "health_domains": ["cardiovascular", "metabolic", "sleep quality"],
        "source_name": "US Centers for Disease Control and Prevention — Sleep",
        "source_url": "https://www.cdc.gov/sleep/about/index.html",
    },
    {
        "category": "tobacco",
        "title": "Tobacco and second-hand smoke",
        "summary": (
            "WHO reports that all forms of tobacco use are harmful and that "
            "tobacco use is a major risk factor for cardiovascular and "
            "respiratory diseases and many cancers. WHO also reports harms "
            "from second-hand smoke."
        ),
        "health_domains": [
            "cardiovascular",
            "respiratory",
            "cancer",
            "second-hand smoke exposure",
        ],
        "source_name": "World Health Organization — Tobacco",
        "source_url": "https://www.who.int/news-room/fact-sheets/detail/tobacco",
    },
    {
        "category": "alcohol",
        "title": "Alcohol use",
        "summary": (
            "CDC reports that alcohol use is linked with several types of cancer. "
            "Over time, excessive alcohol use can contribute to high blood "
            "pressure, heart disease, liver disease, stroke, and other harms. "
            "The app does not infer an individual's risk from a log."
        ),
        "health_domains": [
            "cancer",
            "cardiovascular",
            "liver",
            "stroke",
            "mental health",
        ],
        "source_name": "US Centers for Disease Control and Prevention — Alcohol use",
        "source_url": "https://www.cdc.gov/alcohol/about-alcohol-use/index.html",
    },
    {
        "category": "nutrition",
        "title": "Dietary patterns",
        "summary": (
            "WHO describes healthy dietary patterns as helping protect against "
            "malnutrition and noncommunicable diseases, including diabetes, "
            "heart disease, stroke, and cancer. The optional journal records "
            "only a limited self-reported fruit and vegetable measure."
        ),
        "health_domains": [
            "metabolic",
            "cardiovascular",
            "stroke",
            "cancer",
            "nutrition",
        ],
        "source_name": "World Health Organization — Healthy diet",
        "source_url": "https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
    },
]
