"""Rebuild the synthetic Jason Smith order JSON and contract PDF examples."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from catalogue_core import DEFAULT_CATALOGUE
from contract_core import contract_pdf
from cpq_core import configure_quote
from customer_core import load_customers
from order_core import create_order


def main():
    customer = load_customers()["customers"][0]
    quote = configure_quote(customer, [{"offeringId": "po-mobile-mini", "termMonths": 12},
                                       {"offeringId": "po-sms-extra", "termMonths": 12}])
    record = create_order(quote, customer, DEFAULT_CATALOGUE, order_id="order-demo-jason")
    here = Path(__file__).resolve().parent
    (here / "tmf622-product-order-example.json").write_text(
        json.dumps(record["productOrder"], indent=2) + "\n", encoding="utf-8")
    (here / "cfs-service-order-example.json").write_text(
        json.dumps(record["serviceOrder"], indent=2) + "\n", encoding="utf-8")
    (here / "draft-contract-summary.pdf").write_bytes(contract_pdf(record))
    print("Wrote synthetic order, CFS and draft contract examples")


if __name__ == "__main__":
    main()
