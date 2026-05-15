"""
KDV Bedding — Sage Pastel Migration Module
Tools for importing customers, suppliers, items, and opening balances
from Sage Pastel CSV/Excel exports into ERPNext.
"""

import frappe
from frappe import _
from frappe.utils import flt, cstr, today
import csv
import io


@frappe.whitelist()
def import_customers(file_content, file_type="csv"):
	"""
	Import customers from Sage Pastel export.
	Expected CSV columns: AccountCode, AccountName, ContactName, Email,
	                      Phone, Address1, Address2, City, TaxNumber, CreditLimit
	"""
	frappe.only_for("System Manager")
	rows = _parse_file(file_content, file_type)
	results = {"created": 0, "updated": 0, "errors": []}

	for i, row in enumerate(rows):
		try:
			_import_single_customer(row, results)
		except Exception as e:
			results["errors"].append(f"Row {i+2}: {str(e)}")

	frappe.db.commit()
	return results


def _import_single_customer(row, results):
	account_code = cstr(row.get("AccountCode", "")).strip()
	account_name = cstr(row.get("AccountName", "")).strip()
	if not account_name:
		return

	existing = frappe.db.get_value("Customer", {"custom_sage_account_code": account_code})

	if existing:
		doc = frappe.get_doc("Customer", existing)
		results["updated"] += 1
	else:
		doc = frappe.new_doc("Customer")
		doc.customer_name = account_name
		results["created"] += 1

	doc.customer_name = account_name
	doc.customer_type = "Company"
	doc.customer_group = "Commercial"
	doc.territory = "Zimbabwe"
	doc.tax_id = cstr(row.get("TaxNumber", ""))
	doc.custom_sage_account_code = account_code
	doc.credit_limits = []

	credit_limit = flt(row.get("CreditLimit", 0))
	if credit_limit:
		doc.append("credit_limits", {
			"credit_limit": credit_limit,
			"company": frappe.defaults.get_global_default("company"),
		})

	# Contact
	email = cstr(row.get("Email", "")).strip()
	phone = cstr(row.get("Phone", "")).strip()
	contact_name = cstr(row.get("ContactName", account_name)).strip()

	doc.save(ignore_permissions=True)

	if email or phone:
		_create_or_update_contact(
			link_doctype="Customer",
			link_name=doc.name,
			contact_name=contact_name,
			email=email,
			phone=phone,
		)

	# Address
	address1 = cstr(row.get("Address1", "")).strip()
	city = cstr(row.get("City", "")).strip()
	if address1:
		_create_or_update_address(
			link_doctype="Customer",
			link_name=doc.name,
			address_line1=address1,
			address_line2=cstr(row.get("Address2", "")),
			city=city or "Harare",
			country="Zimbabwe",
		)


@frappe.whitelist()
def import_suppliers(file_content, file_type="csv"):
	"""
	Import suppliers from Sage Pastel export.
	Expected columns: AccountCode, AccountName, ContactName, Email,
	                  Phone, Address1, City, TaxNumber
	"""
	frappe.only_for("System Manager")
	rows = _parse_file(file_content, file_type)
	results = {"created": 0, "updated": 0, "errors": []}

	for i, row in enumerate(rows):
		try:
			account_name = cstr(row.get("AccountName", "")).strip()
			if not account_name:
				continue

			account_code = cstr(row.get("AccountCode", "")).strip()
			existing = frappe.db.get_value("Supplier", {"custom_sage_account_code": account_code})

			if existing:
				doc = frappe.get_doc("Supplier", existing)
				results["updated"] += 1
			else:
				doc = frappe.new_doc("Supplier")
				doc.supplier_name = account_name
				results["created"] += 1

			doc.supplier_name = account_name
			doc.supplier_group = "Raw Materials"
			doc.country = "Zimbabwe"
			doc.tax_id = cstr(row.get("TaxNumber", ""))
			doc.custom_sage_account_code = account_code
			doc.save(ignore_permissions=True)

		except Exception as e:
			results["errors"].append(f"Row {i+2}: {str(e)}")

	frappe.db.commit()
	return results


@frappe.whitelist()
def import_items(file_content, file_type="csv"):
	"""
	Import items/products from Sage Pastel export.
	Expected columns: ItemCode, Description, Category, UOM, SellingPrice,
	                  CostPrice, TaxCode, ReorderLevel, ReorderQty
	"""
	frappe.only_for("System Manager")
	rows = _parse_file(file_content, file_type)
	results = {"created": 0, "updated": 0, "errors": []}

	for i, row in enumerate(rows):
		try:
			item_code = cstr(row.get("ItemCode", "")).strip()
			item_name = cstr(row.get("Description", item_code)).strip()
			if not item_code:
				continue

			existing = frappe.db.exists("Item", item_code)

			if existing:
				doc = frappe.get_doc("Item", item_code)
				results["updated"] += 1
			else:
				doc = frappe.new_doc("Item")
				doc.item_code = item_code
				results["created"] += 1

			doc.item_name = item_name
			doc.item_group = cstr(row.get("Category", "Products"))
			doc.stock_uom = cstr(row.get("UOM", "Nos"))
			doc.is_stock_item = 1
			doc.is_sales_item = 1
			doc.is_purchase_item = 1

			# Pricing
			selling_price = flt(row.get("SellingPrice", 0))
			cost_price = flt(row.get("CostPrice", 0))
			doc.standard_rate = selling_price
			doc.valuation_rate = cost_price

			# Tax
			tax_code = cstr(row.get("TaxCode", ""))
			if "VAT" in tax_code.upper():
				doc.taxes = [{"item_tax_template": "VAT 15% - KDV"}]

			# Reorder
			reorder_level = flt(row.get("ReorderLevel", 0))
			reorder_qty = flt(row.get("ReorderQty", 0))
			if reorder_level:
				doc.reorder_levels = [{
					"warehouse": frappe.db.get_single_value(
						"Stock Settings", "default_warehouse"
					) or "Stores - KDV",
					"warehouse_reorder_level": reorder_level,
					"warehouse_reorder_qty": reorder_qty,
					"material_request_type": "Purchase",
				}]

			doc.save(ignore_permissions=True)

			# Set selling price in Price List
			if selling_price:
				_set_item_price(item_code, "Standard Selling", selling_price)

		except Exception as e:
			results["errors"].append(f"Row {i+2}: {str(e)}")

	frappe.db.commit()
	return results


@frappe.whitelist()
def import_opening_balances(file_content, file_type="csv"):
	"""
	Import opening account balances from Sage Pastel trial balance export.
	Expected columns: AccountCode, AccountName, AccountType, OpeningDebit, OpeningCredit
	"""
	frappe.only_for("System Manager")
	rows = _parse_file(file_content, file_type)
	results = {"processed": 0, "errors": []}

	company = frappe.defaults.get_global_default("company")
	fiscal_year = frappe.db.get_single_value("Global Defaults", "current_fiscal_year")

	je = frappe.new_doc("Journal Entry")
	je.posting_date = today()
	je.company = company
	je.voucher_type = "Opening Entry"
	je.remark = "Opening balances migrated from Sage Pastel"
	je.accounts = []

	for i, row in enumerate(rows):
		try:
			account_code = cstr(row.get("AccountCode", "")).strip()
			debit = flt(row.get("OpeningDebit", 0))
			credit = flt(row.get("OpeningCredit", 0))

			if not debit and not credit:
				continue

			account = frappe.db.get_value(
				"Account", {"account_number": account_code, "company": company}
			)
			if not account:
				results["errors"].append(f"Row {i+2}: Account {account_code} not found in ERPNext")
				continue

			je.append("accounts", {
				"account": account,
				"debit_in_account_currency": debit,
				"credit_in_account_currency": credit,
				"cost_center": frappe.db.get_value(
					"Cost Center", {"is_group": 0, "company": company}
				),
			})
			results["processed"] += 1

		except Exception as e:
			results["errors"].append(f"Row {i+2}: {str(e)}")

	if je.accounts:
		try:
			je.save(ignore_permissions=True)
			results["journal_entry"] = je.name
		except Exception as e:
			results["errors"].append(f"Journal Entry creation failed: {str(e)}")

	return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_file(file_content, file_type):
	"""Parse CSV or pipe-delimited content into list of dicts."""
	if isinstance(file_content, str):
		content = file_content
	else:
		content = file_content.decode("utf-8", errors="replace")

	delimiter = "," if file_type == "csv" else "|"
	reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
	return list(reader)


def _create_or_update_contact(link_doctype, link_name, contact_name, email, phone):
	"""Create or update a contact linked to a customer/supplier."""
	existing_contact = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": link_doctype, "link_name": link_name, "parenttype": "Contact"},
		"parent",
	)
	if existing_contact:
		return

	contact = frappe.new_doc("Contact")
	contact.first_name = contact_name
	contact.links = [{"link_doctype": link_doctype, "link_name": link_name}]
	if email:
		contact.email_ids = [{"email_id": email, "is_primary": 1}]
	if phone:
		contact.phone_nos = [{"phone": phone, "is_primary_phone": 1}]
	contact.save(ignore_permissions=True)


def _create_or_update_address(link_doctype, link_name, address_line1, address_line2, city, country):
	"""Create or update an address linked to a customer/supplier."""
	existing_address = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": link_doctype, "link_name": link_name, "parenttype": "Address"},
		"parent",
	)
	if existing_address:
		return

	address = frappe.new_doc("Address")
	address.address_title = link_name
	address.address_type = "Billing"
	address.address_line1 = address_line1
	address.address_line2 = address_line2
	address.city = city
	address.country = country
	address.links = [{"link_doctype": link_doctype, "link_name": link_name}]
	address.save(ignore_permissions=True)


def _set_item_price(item_code, price_list, price):
	"""Set or update item price in a price list."""
	existing = frappe.db.get_value(
		"Item Price", {"item_code": item_code, "price_list": price_list}
	)
	if existing:
		frappe.db.set_value("Item Price", existing, "price_list_rate", price)
	else:
		frappe.get_doc({
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": price,
			"currency": "USD",
		}).insert(ignore_permissions=True)
