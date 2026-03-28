"""
tools/linkedin_tool.py
──────────────────────
LinkedIn HR Hunter — mock implementation for hackathon demo.

Returns realistic, demo-safe mock data for judge presentation.
Structure mirrors what a real LinkedIn API response would look like,
so swapping in real API / Selenium later requires only changing _fetch_contacts().

For real scraping fallback, replace _fetch_contacts() with Selenium logic.
"""

import random
from typing import Any


# ── Realistic mock data pool ──────────────────────────────────────────────────

_MOCK_HR_POOL = {
    "TCS": [
        {"name": "Priya Nair", "role": "HR Manager", "location": "Chennai", "email": "priya.nair@tcs.com", "linkedin_url": "https://linkedin.com/in/priya-nair-tcs"},
        {"name": "Karthik Subramaniam", "role": "Talent Acquisition Lead", "location": "Chennai", "email": "karthik.s@tcs.com", "linkedin_url": "https://linkedin.com/in/karthik-s-tcs"},
        {"name": "Deepa Krishnan", "role": "Senior Recruiter", "location": "Chennai", "email": "deepa.k@tcs.com", "linkedin_url": "https://linkedin.com/in/deepa-k-tcs"},
    ],
    "Infosys": [
        {"name": "Meera Shankar", "role": "HR Business Partner", "location": "Chennai", "email": "meera.shankar@infosys.com", "linkedin_url": "https://linkedin.com/in/meera-shankar-infosys"},
        {"name": "Arjun Raj", "role": "Campus Recruiter", "location": "Chennai", "email": "arjun.raj@infosys.com", "linkedin_url": "https://linkedin.com/in/arjun-raj-infosys"},
    ],
    "Wipro": [
        {"name": "Shalini Rajan", "role": "Talent Acquisition Manager", "location": "Chennai", "email": "shalini.rajan@wipro.com", "linkedin_url": "https://linkedin.com/in/shalini-rajan-wipro"},
        {"name": "Vijay Kumar", "role": "HR Generalist", "location": "Chennai", "email": "vijay.kumar@wipro.com", "linkedin_url": "https://linkedin.com/in/vijay-kumar-wipro"},
    ],
    "HCL": [
        {"name": "Ananya Bose", "role": "Recruiter", "location": "Chennai", "email": "ananya.bose@hcl.com", "linkedin_url": "https://linkedin.com/in/ananya-bose-hcl"},
        {"name": "Ramesh Iyer", "role": "HR Manager", "location": "Chennai", "email": "ramesh.iyer@hcl.com", "linkedin_url": "https://linkedin.com/in/ramesh-iyer-hcl"},
    ],
    "Cognizant": [
        {"name": "Lakshmi Priya", "role": "Senior HR Manager", "location": "Chennai", "email": "lakshmi.priya@cognizant.com", "linkedin_url": "https://linkedin.com/in/lakshmi-priya-cognizant"},
        {"name": "Suresh Babu", "role": "Talent Scout", "location": "Chennai", "email": "suresh.babu@cognizant.com", "linkedin_url": "https://linkedin.com/in/suresh-babu-cognizant"},
    ],
}


def _fetch_contacts(company: str, location: str, role_filter: str) -> list[dict]:
    """
    Returns mock HR contacts for a company.
    In production: replace with LinkedIn API call or Selenium scraper.
    """
    company_key = next(
        (k for k in _MOCK_HR_POOL if k.lower() in company.lower()),
        None,
    )
    if company_key:
        contacts = _MOCK_HR_POOL[company_key]
    else:
        # Generate plausible mock data for unknown companies
        contacts = [
            {
                "name": f"HR Contact {i+1}",
                "role": random.choice(["HR Manager", "Recruiter", "Talent Acquisition"]),
                "location": location,
                "email": f"hr{i+1}@{company.lower().replace(' ', '')}.com",
                "linkedin_url": f"https://linkedin.com/in/hr-{company.lower().replace(' ', '-')}-{i+1}",
            }
            for i in range(2)
        ]

    # Apply role filter
    if role_filter:
        contacts = [
            c for c in contacts
            if role_filter.lower() in c["role"].lower()
        ] or contacts  # fall back to all if filter is too strict

    return contacts


def search_hr_contacts(
    company: str,
    location: str = "Chennai",
    role_filter: str = "HR",
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Search for HR/recruiter contacts at a target company.
    Returns structured contact list ready for email outreach.
    """
    contacts = _fetch_contacts(company, location, role_filter)[:max_results]

    return {
        "status": "found",
        "company": company,
        "location": location,
        "count": len(contacts),
        "contacts": contacts,
    }


def search_multiple_companies(
    companies: list[str],
    location: str = "Chennai",
    role_filter: str = "HR",
) -> dict[str, Any]:
    """Search HR contacts across multiple companies at once."""
    all_contacts = []
    for company in companies:
        result = search_hr_contacts(company, location, role_filter)
        for contact in result["contacts"]:
            contact["company"] = company
            all_contacts.append(contact)

    return {
        "status": "found",
        "total_count": len(all_contacts),
        "contacts": all_contacts,
    }