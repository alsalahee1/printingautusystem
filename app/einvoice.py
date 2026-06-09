"""Malaysian e-Invoice (LHDN MyInvois) document builder.

Produces a JSON payload aligned to the MyInvois UBL 2.1 invoice structure from
a PrintSys Invoice. This captures all the business fields LHDN requires
(supplier & buyer TIN/BRN/SST, MSIC, line items with classification codes, SST
tax totals, monetary totals) so it can be handed to a MyInvois submitter.

Note: actually transmitting to the MyInvois API requires IRBM credentials and
the platform's sign/submit step — that integration is intentionally out of
scope here; this module prepares the document.
"""
from datetime import datetime


def _party(name, tin, brn, sst, address, city, msic=None, activity=None, phone="", email=""):
    party = {
        "PartyLegalEntity": [{"RegistrationName": [{"_": name or ""}]}],
        "PartyIdentification": [
            {"ID": [{"_": tin or "", "schemeID": "TIN"}]},
            {"ID": [{"_": brn or "NA", "schemeID": "BRN"}]},
            {"ID": [{"_": sst or "NA", "schemeID": "SST"}]},
        ],
        "PostalAddress": [{
            "CityName": [{"_": city or ""}],
            "AddressLine": [{"Line": [{"_": (address or "").replace("\n", ", ")}]}],
            "Country": [{"IdentificationCode": [{"_": "MYS"}]}],
        }],
        "Contact": [{"Telephone": [{"_": phone or ""}], "ElectronicMail": [{"_": email or ""}]}],
    }
    if msic:
        party["IndustryClassificationCode"] = [{"_": msic, "name": activity or ""}]
    return party


def build_einvoice(inv, settings) -> dict:
    """Return a MyInvois-aligned e-Invoice JSON dict for the given invoice."""
    cust = inv.customer
    currency = settings.currency if settings.currency in ("MYR", "RM") else "MYR"
    currency = "MYR" if currency == "RM" else currency

    # SST tax category: 01 = Sales Tax, 06 = Not Applicable / zero-rated.
    tax_category = "01" if inv.tax_pct > 0 else "06"

    lines = []
    for it in inv.items:
        lines.append({
            "ID": [{"_": str(it.line_no)}],
            "InvoicedQuantity": [{"_": it.quantity, "unitCode": "C62"}],
            "LineExtensionAmount": [{"_": round(it.amount, 2), "currencyID": currency}],
            "Item": [{
                "Description": [{"_": it.description}],
                "CommodityClassification": [{
                    "ItemClassificationCode": [{"_": settings.einvoice_classification or "022",
                                                 "listID": "CLASS"}]
                }],
            }],
            "Price": [{"PriceAmount": [{"_": round(it.unit_price, 2), "currencyID": currency}]}],
        })

    tax_total = [{
        "TaxAmount": [{"_": round(inv.tax_amount, 2), "currencyID": currency}],
        "TaxSubtotal": [{
            "TaxableAmount": [{"_": round(inv.subtotal, 2), "currencyID": currency}],
            "TaxAmount": [{"_": round(inv.tax_amount, 2), "currencyID": currency}],
            "TaxCategory": [{
                "ID": [{"_": tax_category}],
                "Percent": [{"_": inv.tax_pct}],
                "TaxScheme": [{"ID": [{"_": "OTH", "schemeID": "UN/ECE 5153"}]}],
            }],
        }],
    }]

    document = {
        "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "Invoice": [{
            "ID": [{"_": inv.number}],
            "IssueDate": [{"_": inv.date.isoformat()}],
            "IssueTime": [{"_": datetime.utcnow().strftime("%H:%M:%SZ")}],
            "InvoiceTypeCode": [{"_": "01", "listVersionID": "1.1"}],
            "DocumentCurrencyCode": [{"_": currency}],
            "AccountingSupplierParty": [{"Party": [_party(
                settings.company_name, settings.company_tin, settings.company_brn,
                settings.company_tax_no, settings.company_address, "",
                msic=settings.company_msic, activity=settings.company_activity,
                phone=settings.company_phone, email=settings.company_email)]}],
            "AccountingCustomerParty": [{"Party": [_party(
                cust.company or cust.name, cust.tin, cust.reg_no, cust.tax_no,
                cust.address, cust.city, phone=cust.phone, email=cust.email)]}],
            "InvoiceLine": lines,
            "TaxTotal": tax_total,
            "LegalMonetaryTotal": [{
                "LineExtensionAmount": [{"_": round(inv.subtotal, 2), "currencyID": currency}],
                "TaxExclusiveAmount": [{"_": round(inv.subtotal, 2), "currencyID": currency}],
                "TaxInclusiveAmount": [{"_": round(inv.total, 2), "currencyID": currency}],
                "PayableAmount": [{"_": round(inv.total, 2), "currencyID": currency}],
            }],
        }],
    }
    return document


def validation_warnings(inv, settings) -> list[str]:
    """Surface obvious gaps before an e-Invoice is submitted."""
    w = []
    if not settings.company_tin:
        w.append("Your company TIN is not set (Settings → e-Invoice).")
    if not settings.company_msic:
        w.append("Your company MSIC code is not set (Settings → e-Invoice).")
    if not inv.customer.tin:
        w.append(f"Customer '{inv.customer.name}' has no TIN.")
    return w
