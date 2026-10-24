"""Portable one-page draft contract summary PDF for the local POC."""

import textwrap
from decimal import Decimal


def _pdf_text(value):
    value = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return value.encode("cp1252", errors="replace")


def _pdf_document(streams):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for stream in streams:
        page_id = len(objects) + 1
        content_id = page_id + 1
        kids.append(f"{page_id} 0 R".encode())
        objects.append((b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        b"/Resources << /Font << /F1 3 0 R >> >> /Contents " +
                        f"{content_id} 0 R >>".encode()))
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + f"] /Count {len(kids)} >>".encode()
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def contract_pdf(record):
    order, quote, customer = record["productOrder"], record["quote"], record["customer"]
    review = record["contractReview"]
    lines = []
    lines.append(("DRAFT CONTRACT SUMMARY - POC ONLY", 17))
    lines.append(("Not a binding contract or Ofcom-compliant final summary", 10))
    lines.append(("", 8))
    lines.append((f"Product order: {order['id']}", 10))
    lines.append((f"Customer: {customer['givenName']} {customer['familyName']}", 10))
    lines.append((f"Primary contact: {customer['email']}", 10))
    address = customer["address"]
    lines.append((f"Address: {address['line1']}, {address['city']}, {address['postcode']}, UK", 10))
    lines.append(("", 8))
    lines.append(("PRODUCTS AND TERMS", 12))
    for item in quote["quoteItem"]:
        price = item["itemPrice"][0]["price"]["dutyFreeAmount"]["value"]
        lines.append((f"{item['productOffering']['name']} - {item['termMonths']} months - £{price}/month before tax", 10))
        allowance = ", ".join(f"{c['value']} {c['unit']} {c['productSpecification']['name']}"
                              for c in item["product"]["productCharacteristic"])
        lines.append((allowance, 9))
    monthly = quote["quoteTotalPrice"][0]["price"]["dutyFreeAmount"]["value"]
    setup = quote["quoteTotalPrice"][1]["price"]["dutyFreeAmount"]["value"]
    lines.append(("", 8))
    lines.append((f"Monthly total before tax: £{monthly}    One-time setup before tax: £{setup}", 11))
    commitment = sum(Decimal(item["itemPrice"][0]["price"]["dutyFreeAmount"]["value"]) *
                     item["termMonths"] + Decimal(item["itemPrice"][1]["price"]["dutyFreeAmount"]["value"])
                     for item in quote["quoteItem"])
    lines.append((f"Estimated charge over selected terms before tax: £{commitment:.2f}", 10))
    lines.append(("No in-contract price rise is modelled; final provider terms must confirm the schedule.", 9))
    lines.append(("", 8))
    lines.append(("CONTRACT VERIFICATION - INFORMATION STILL REQUIRED", 12))
    for gap in review["missingDisclosures"]:
        lines.append((f"- {gap}", 9))
    lines.append(("", 8))
    lines.append(("This document records a POC order request. It does not activate a service or", 9))
    lines.append(("record the customer's express consent to a legally binding contract.", 9))

    streams = []
    commands = []
    y = 798
    for text, size in lines:
        wrapped = textwrap.wrap(text, width=94 if size < 11 else 78, break_long_words=False) or [""]
        for segment in wrapped:
            if y < 46:
                streams.append(b"\n".join(commands))
                commands, y = [], 798
            if segment:
                commands.append(f"BT /F1 {size} Tf 42 {y} Td ".encode() + b"(" + _pdf_text(segment) + b") Tj ET")
            y -= size + 5
    streams.append(b"\n".join(commands))
    return _pdf_document(streams)
