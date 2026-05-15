"""
KDV Bedding — ZIMRA Fiscalisation Module
Handles invoice signing and submission to ZIMRA as per Zimbabwe fiscal requirements.
"""

import json
import hashlib
import base64
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime
import requests


# ---------------------------------------------------------------------------
# Settings DocType helper
# ---------------------------------------------------------------------------

def get_fiscalisation_settings():
	"""Return KDV Fiscalisation Settings document."""
	return frappe.get_single("KDV Fiscalisation Settings")


# ---------------------------------------------------------------------------
# Document Event Hooks
# ---------------------------------------------------------------------------

def on_sales_invoice_submit(doc, method):
	"""Triggered on Sales Invoice submit — signs and submits to ZIMRA."""
	settings = get_fiscalisation_settings()
	if not settings.enabled:
		return

	try:
		result = submit_invoice_to_zimra(doc)
		if result.get("success"):
			frappe.db.set_value("Sales Invoice", doc.name, {
				"custom_fiscal_day_no": result.get("fiscal_day_no"),
				"custom_receipt_counter": result.get("receipt_counter"),
				"custom_fiscal_signature": result.get("signature"),
				"custom_qr_code": result.get("qr_code"),
				"custom_fiscal_status": "Submitted",
			})
			frappe.msgprint(
				_("Invoice successfully submitted to ZIMRA. Receipt No: {0}").format(
					result.get("receipt_counter")
				),
				indicator="green",
			)
		else:
			_log_fiscal_error(doc.name, result.get("error", "Unknown error"))
	except Exception as e:
		_log_fiscal_error(doc.name, str(e))


def on_sales_invoice_cancel(doc, method):
	"""Triggered on Sales Invoice cancel — sends void/credit note to ZIMRA."""
	settings = get_fiscalisation_settings()
	if not settings.enabled:
		return
	if not doc.get("custom_fiscal_signature"):
		return

	try:
		result = void_invoice_in_zimra(doc)
		if result.get("success"):
			frappe.db.set_value("Sales Invoice", doc.name, {
				"custom_fiscal_status": "Voided",
			})
	except Exception as e:
		_log_fiscal_error(doc.name, str(e))


# ---------------------------------------------------------------------------
# Core ZIMRA API Functions
# ---------------------------------------------------------------------------

def submit_invoice_to_zimra(invoice_doc):
	"""
	Build the fiscal payload, sign it, and POST to ZIMRA.
	Returns dict with success flag and fiscal response fields.
	"""
	settings = get_fiscalisation_settings()
	payload = _build_invoice_payload(invoice_doc, settings)
	signature = _sign_payload(payload, settings.device_private_key)
	payload["signature"] = signature

	response = _post_to_zimra(
		endpoint=settings.zimra_api_url + "/receipts",
		payload=payload,
		device_id=settings.device_id,
		device_serial=settings.device_serial_no,
	)

	if response.status_code == 200:
		data = response.json()
		qr_data = _generate_qr_code(data, invoice_doc)
		return {
			"success": True,
			"fiscal_day_no": data.get("fiscalDayNo"),
			"receipt_counter": data.get("receiptCounter"),
			"signature": signature,
			"qr_code": qr_data,
		}
	else:
		return {
			"success": False,
			"error": f"ZIMRA API error {response.status_code}: {response.text}",
		}


def void_invoice_in_zimra(invoice_doc):
	"""Send a void/credit note receipt to ZIMRA for a cancelled invoice."""
	settings = get_fiscalisation_settings()
	payload = {
		"receiptType": "CREDIT_NOTE",
		"originalFiscalSignature": invoice_doc.custom_fiscal_signature,
		"invoiceNo": invoice_doc.name,
		"reason": "Invoice Cancelled",
	}
	signature = _sign_payload(payload, settings.device_private_key)
	payload["signature"] = signature

	response = _post_to_zimra(
		endpoint=settings.zimra_api_url + "/receipts/void",
		payload=payload,
		device_id=settings.device_id,
		device_serial=settings.device_serial_no,
	)
	return {"success": response.status_code == 200}


@frappe.whitelist()
def retry_pending_fiscal_submissions():
	"""Scheduled task: retry invoices that failed fiscalisation."""
	pending = frappe.get_all(
		"Sales Invoice",
		filters={"custom_fiscal_status": "Failed", "docstatus": 1},
		fields=["name"],
		limit=20,
	)
	for inv in pending:
		doc = frappe.get_doc("Sales Invoice", inv.name)
		on_sales_invoice_submit(doc, None)


# ---------------------------------------------------------------------------
# Payload Builders
# ---------------------------------------------------------------------------

def _build_invoice_payload(doc, settings):
	"""Build the ZIMRA-compliant receipt payload from a Sales Invoice."""
	items = []
	for item in doc.items:
		items.append({
			"itemDescription": item.item_name,
			"quantity": item.qty,
			"unitPrice": item.rate,
			"totalAmount": item.amount,
			"taxCode": _get_tax_code(item, doc),
			"taxAmount": _get_item_tax(item, doc),
		})

	tax_lines = _extract_tax_lines(doc)

	payload = {
		"deviceID": settings.device_id,
		"receiptType": "FISCAL_RECEIPT",
		"invoiceNo": doc.name,
		"customerName": doc.customer_name,
		"customerTIN": doc.get("tax_id") or "",
		"receiptDate": str(doc.posting_date),
		"receiptTime": str(doc.posting_time or "00:00:00"),
		"receiptLinesTaxInclusive": True,
		"receiptLines": items,
		"receiptTaxes": tax_lines,
		"receiptTotal": doc.grand_total,
		"receiptCurrency": doc.currency,
		"receiptExchangeRate": doc.conversion_rate or 1,
		"paymentType": _get_payment_type(doc),
	}
	return payload


def _get_tax_code(item, doc):
	"""Return ZIMRA tax code (A=standard VAT, B=exempt, C=zero-rated)."""
	# Map ERPNext tax templates to ZIMRA codes
	tax_map = {
		"VAT 15%": "A",
		"VAT Exempt": "B",
		"Zero Rated": "C",
	}
	template = item.get("item_tax_template") or ""
	for key, code in tax_map.items():
		if key.lower() in template.lower():
			return code
	return "A"  # default to standard VAT


def _get_item_tax(item, doc):
	"""Calculate tax amount for an individual line item."""
	if not doc.taxes:
		return 0
	total_tax = sum(t.tax_amount for t in doc.taxes)
	if doc.net_total:
		return round((item.amount / doc.net_total) * total_tax, 2)
	return 0


def _extract_tax_lines(doc):
	"""Build ZIMRA tax summary lines from invoice taxes."""
	tax_lines = []
	for tax in (doc.taxes or []):
		tax_lines.append({
			"taxCode": "A",
			"taxRate": tax.rate,
			"taxAmount": tax.tax_amount,
			"taxableAmount": tax.base_tax_amount_after_discount_amount or doc.net_total,
		})
	return tax_lines


def _get_payment_type(doc):
	"""Map ERPNext payment mode to ZIMRA payment type."""
	mode = doc.get("mode_of_payment") or ""
	mapping = {
		"Cash": "CASH",
		"Bank": "TRANSFER",
		"Credit Card": "CARD",
		"Mobile Money": "MOBILE_MONEY",
	}
	return mapping.get(mode, "CASH")


# ---------------------------------------------------------------------------
# Signing & QR Code
# ---------------------------------------------------------------------------

def _sign_payload(payload, private_key_pem):
	"""
	Sign the payload using SHA256 hash.
	In production, replace with RSA private key signing using the
	cryptography library as required by ZIMRA device specifications.
	"""
	if not private_key_pem:
		# Fallback: SHA256 hash for development/testing
		payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
		return hashlib.sha256(payload_str.encode()).hexdigest()

	try:
		from cryptography.hazmat.primitives import hashes, serialization
		from cryptography.hazmat.primitives.asymmetric import padding

		private_key = serialization.load_pem_private_key(
			private_key_pem.encode(), password=None
		)
		payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
		signature = private_key.sign(
			payload_str.encode(),
			padding.PKCS1v15(),
			hashes.SHA256(),
		)
		return base64.b64encode(signature).decode()
	except Exception as e:
		frappe.log_error(f"ZIMRA signing error: {e}", "KDV Fiscalisation")
		return ""


def _generate_qr_code(zimra_response, invoice_doc):
	"""Generate a QR code string for the fiscal receipt."""
	try:
		import qrcode
		import io

		qr_data = (
			f"ZIMRA|{invoice_doc.name}|"
			f"{zimra_response.get('fiscalDayNo')}|"
			f"{zimra_response.get('receiptCounter')}|"
			f"{invoice_doc.grand_total}|"
			f"{invoice_doc.posting_date}"
		)
		qr = qrcode.QRCode(version=1, box_size=6, border=2)
		qr.add_data(qr_data)
		qr.make(fit=True)
		img = qr.make_image(fill_color="black", back_color="white")
		buffer = io.BytesIO()
		img.save(buffer, format="PNG")
		encoded = base64.b64encode(buffer.getvalue()).decode()
		return f"data:image/png;base64,{encoded}"
	except Exception:
		return ""


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

def _post_to_zimra(endpoint, payload, device_id, device_serial):
	"""POST fiscal data to ZIMRA API with device authentication headers."""
	headers = {
		"Content-Type": "application/json",
		"DeviceID": str(device_id),
		"DeviceSerial": str(device_serial),
	}
	return requests.post(
		endpoint,
		json=payload,
		headers=headers,
		timeout=30,
	)


# ---------------------------------------------------------------------------
# Error Logging
# ---------------------------------------------------------------------------

def _log_fiscal_error(invoice_name, error_message):
	"""Log fiscalisation error and update invoice status."""
	frappe.log_error(
		message=f"Invoice: {invoice_name}\nError: {error_message}",
		title="KDV Fiscalisation Error",
	)
	frappe.db.set_value("Sales Invoice", invoice_name, {
		"custom_fiscal_status": "Failed",
		"custom_fiscal_error": error_message[:500],
	})
	frappe.msgprint(
		_("Fiscalisation failed. The invoice was submitted but not fiscalised. Error: {0}").format(
			error_message
		),
		indicator="orange",
		alert=True,
	)


# ---------------------------------------------------------------------------
# Whitelisted API Endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_fiscal_status(invoice_name):
	"""Return fiscal status for a given invoice (used by JS client)."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	return {
		"fiscal_status": doc.get("custom_fiscal_status"),
		"receipt_counter": doc.get("custom_receipt_counter"),
		"fiscal_day_no": doc.get("custom_fiscal_day_no"),
		"qr_code": doc.get("custom_qr_code"),
	}


@frappe.whitelist()
def test_zimra_connection():
	"""Test ZIMRA API connectivity — whitelisted for settings page."""
	frappe.only_for("System Manager")
	settings = get_fiscalisation_settings()
	try:
		response = requests.get(
			settings.zimra_api_url + "/health",
			timeout=10,
		)
		if response.status_code == 200:
			return {"success": True, "message": "ZIMRA API reachable"}
		return {"success": False, "message": f"HTTP {response.status_code}"}
	except Exception as e:
		return {"success": False, "message": str(e)}
