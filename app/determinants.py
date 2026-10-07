"""Mappings from collected signals to determinant domains and health indicators."""

DETERMINANT_DOMAINS = [
    {
        "id": "behavioral",
        "name": "Behavioral and lifestyle factors",
        "definition": (
            "Behaviors and routines that can influence health. This app currently "
            "collects optional self-reports and selected activity measurements."
        ),
        "not_collected": False,
        "evidence_categories": ["activity", "sleep", "tobacco", "alcohol", "nutrition"],
    },
    {
        "id": "social_economic",
        "name": "Social and economic conditions",
        "definition": (
            "Conditions such as education, work, income, housing, and social "
            "protection that shape the conditions in which people live."
        ),
        "not_collected": True,
        "evidence_categories": [],
    },
    {
        "id": "physical_environment",
        "name": "Physical environment",
        "definition": (
            "The surrounding built and natural environments, including housing, "
            "transport, air, water, and workplace conditions."
        ),
        "not_collected": True,
        "evidence_categories": [],
    },
    {
        "id": "health_services",
        "name": "Health services",
        "definition": (
            "Availability, accessibility, affordability, and quality of health "
            "services and care."
        ),
        "not_collected": True,
        "evidence_categories": [],
    },
    {
        "id": "personal_characteristics",
        "name": "Personal characteristics",
        "definition": (
            "Personal characteristics can include age, sex, and family history. "
            "This prototype does not collect these attributes or genetic data."
        ),
        "not_collected": True,
        "evidence_categories": [],
    },
]

ACTIVITY_METRICS = {
    "HKQuantityTypeIdentifierStepCount": "Step count",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "Walking/running distance",
    "HKQuantityTypeIdentifierAppleExerciseTime": "Exercise time",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "Active energy",
    "HKQuantityTypeIdentifierFlightsClimbed": "Flights climbed",
    "HKQuantityTypeIdentifierCyclingDistance": "Cycling distance",
    "HKQuantityTypeIdentifierSwimmingDistance": "Swimming distance",
    "HKQuantityTypeIdentifierWheelchairPushCount": "Wheelchair pushes",
}

HEALTH_INDICATOR_METRICS = {
    "HKQuantityTypeIdentifierHeartRate": "Heart rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "Resting heart rate",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": "Walking heart-rate average",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "Heart-rate variability",
    "HKQuantityTypeIdentifierOxygenSaturation": "Blood oxygen saturation",
    "HKQuantityTypeIdentifierBloodPressureSystolic": "Systolic blood pressure",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "Diastolic blood pressure",
    "HKQuantityTypeIdentifierBloodGlucose": "Blood glucose",
    "HKQuantityTypeIdentifierBodyMass": "Body mass",
    "HKQuantityTypeIdentifierBodyMassIndex": "Body mass index",
}
