"""Small TMF629-inspired customer records for the local UK CPQ preview."""
import copy
import json
import re
from pathlib import Path

CUSTOMERS_PATH = Path(__file__).with_name("customers.json")
POSTCODE = re.compile(r"^(GIR 0AA|(?:[A-Z]{1,2}[0-9][A-Z0-9]?)[ ]?[0-9][A-Z]{2})$")


class CustomerError(ValueError):
    pass


def validate_customer(record):
    if not isinstance(record, dict):
        raise CustomerError("Customer must be an object")
    if set(record) != {"id", "givenName", "familyName", "email", "mobile", "address", "segment"}:
        raise CustomerError("Customer has missing or unsupported fields")
    result = copy.deepcopy(record)
    for key in ("id", "givenName", "familyName", "email", "mobile"):
        if not isinstance(result.get(key), str) or not 1 <= len(result[key].strip()) <= 150:
            raise CustomerError(f"Customer needs {key}")
        result[key] = result[key].strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", result["email"]):
        raise CustomerError("Enter a valid email address")
    mobile = re.sub(r"[\s-]", "", result["mobile"])
    if not re.fullmatch(r"(?:07\d{9}|\+447\d{9})", mobile):
        raise CustomerError("Enter a UK mobile number starting 07 or +447")
    result["mobile"] = mobile
    address = result.get("address")
    if not isinstance(address, dict):
        raise CustomerError("Customer needs a UK address")
    if set(address) != {"line1", "city", "postcode", "countryCode"}:
        raise CustomerError("Address has missing or unsupported fields")
    for key in ("line1", "city", "postcode"):
        if not isinstance(address.get(key), str) or not 1 <= len(address[key].strip()) <= 150:
            raise CustomerError(f"Customer address needs {key}")
        address[key] = address[key].strip()
    postcode = re.sub(r"\s+", "", address["postcode"].upper())
    if not POSTCODE.fullmatch(postcode[:-3] + " " + postcode[-3:]):
        raise CustomerError("Enter a UK-format postcode")
    address["postcode"] = postcode[:-3] + " " + postcode[-3:]
    if address.get("countryCode") != "GB":
        raise CustomerError("This preview accepts UK addresses only")
    if result.get("segment") not in ("consumer", "business"):
        raise CustomerError("Customer segment must be consumer or business")
    return result


def load_customers(path=None):
    try:
        data = json.loads(Path(path or CUSTOMERS_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CustomerError("Could not load customer records") from exc
    if not isinstance(data, dict) or not isinstance(data.get("customers"), list):
        raise CustomerError("Customer store is invalid")
    records = [validate_customer(row) for row in data["customers"]]
    ids = [row["id"] for row in records]
    if len(ids) != len(set(ids)):
        raise CustomerError("Customer IDs must be unique")
    return {"version": data.get("version"), "customers": records}
