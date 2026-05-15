"""
KDV Bedding — Inventory Module
Tracks stock levels, reorder alerts, and purchase order status.
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, flt


def on_stock_entry_submit(doc, method):
	"""Triggered on Stock Entry submit — check reorder levels."""
	for item in doc.items:
		_check_single_item_reorder(item.item_code, item.s_warehouse or item.t_warehouse)


@frappe.whitelist()
def check_reorder_levels():
	"""
	Scheduled daily task.
	Finds items below reorder level and creates Purchase Orders if auto-reorder is set.
	"""
	items_below_reorder = frappe.db.sql("""
		SELECT
			ir.name,
			ir.parent as item_code,
			i.item_name,
			ir.warehouse,
			ir.warehouse_reorder_level,
			ir.warehouse_reorder_qty,
			COALESCE(b.actual_qty, 0) as current_qty,
			ir.material_request_type
		FROM `tabItem Reorder` ir
		INNER JOIN `tabItem` i ON i.name = ir.parent
		LEFT JOIN `tabBin` b ON b.item_code = ir.parent AND b.warehouse = ir.warehouse
		WHERE i.disabled = 0
		AND COALESCE(b.actual_qty, 0) <= ir.warehouse_reorder_level
	""", as_dict=True)

	alerts = []
	for item in items_below_reorder:
		alerts.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"warehouse": item.warehouse,
			"current_qty": item.current_qty,
			"reorder_level": item.warehouse_reorder_level,
			"reorder_qty": item.warehouse_reorder_qty,
		})
		# Create notification for store manager
		_create_reorder_notification(item)

	return alerts


def _check_single_item_reorder(item_code, warehouse):
	"""Check if a single item has crossed reorder level after a stock movement."""
	if not item_code or not warehouse:
		return
	bin_qty = frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
	) or 0
	reorder_level = frappe.db.get_value(
		"Item Reorder", {"parent": item_code, "warehouse": warehouse}, "warehouse_reorder_level"
	) or 0
	if flt(bin_qty) <= flt(reorder_level):
		_create_reorder_notification({
			"item_code": item_code,
			"item_name": frappe.db.get_value("Item", item_code, "item_name"),
			"warehouse": warehouse,
			"current_qty": bin_qty,
			"reorder_level": reorder_level,
		})


def _create_reorder_notification(item):
	"""Create a Frappe notification for stock reorder."""
	# Avoid duplicate notifications (one per day per item)
	existing = frappe.db.exists("Notification Log", {
		"document_type": "Item",
		"document_name": item["item_code"],
		"creation": [">=", today()],
	})
	if existing:
		return

	notification = frappe.get_doc({
		"doctype": "Notification Log",
		"subject": f"Reorder Alert: {item['item_name']}",
		"for_user": frappe.db.get_single_value("Stock Settings", "stock_manager") or "Administrator",
		"type": "Alert",
		"document_type": "Item",
		"document_name": item["item_code"],
		"email_content": (
			f"Item <b>{item['item_name']}</b> in warehouse <b>{item.get('warehouse', '')}</b> "
			f"has reached reorder level.<br>"
			f"Current Qty: <b>{item['current_qty']}</b> | "
			f"Reorder Level: <b>{item['reorder_level']}</b>"
		),
	})
	notification.insert(ignore_permissions=True)


@frappe.whitelist()
def get_inventory_kpis():
	"""Return inventory KPIs for dashboard."""
	frappe.has_permission("Item", "read", throw=True)

	# Items below reorder level
	below_reorder = frappe.db.sql("""
		SELECT COUNT(DISTINCT ir.parent)
		FROM `tabItem Reorder` ir
		LEFT JOIN `tabBin` b ON b.item_code = ir.parent AND b.warehouse = ir.warehouse
		WHERE COALESCE(b.actual_qty, 0) <= ir.warehouse_reorder_level
	""")[0][0]

	# Items due for reorder with details
	reorder_items = frappe.db.sql("""
		SELECT
			ir.parent as item_code,
			i.item_name,
			ir.warehouse,
			ir.warehouse_reorder_level as reorder_level,
			ir.warehouse_reorder_qty as reorder_qty,
			COALESCE(b.actual_qty, 0) as current_qty,
			COALESCE(b.actual_qty, 0) - ir.warehouse_reorder_level as shortage
		FROM `tabItem Reorder` ir
		INNER JOIN `tabItem` i ON i.name = ir.parent
		LEFT JOIN `tabBin` b ON b.item_code = ir.parent AND b.warehouse = ir.warehouse
		WHERE i.disabled = 0
		AND COALESCE(b.actual_qty, 0) <= ir.warehouse_reorder_level
		ORDER BY shortage ASC
		LIMIT 10
	""", as_dict=True)

	# Open Purchase Orders
	open_pos = frappe.db.sql("""
		SELECT
			COUNT(name) as count,
			COALESCE(SUM(base_grand_total), 0) as total_value
		FROM `tabPurchase Order`
		WHERE docstatus = 1
		AND status NOT IN ('Completed', 'Cancelled', 'Closed')
	""", as_dict=True)[0]

	# Total stock value
	total_stock_value = frappe.db.sql("""
		SELECT COALESCE(SUM(actual_qty * valuation_rate), 0)
		FROM `tabBin`
		WHERE actual_qty > 0
	""")[0][0]

	# Warehouse-wise stock summary
	warehouse_summary = frappe.db.sql("""
		SELECT
			b.warehouse,
			COUNT(DISTINCT b.item_code) as items,
			SUM(b.actual_qty * b.valuation_rate) as stock_value
		FROM `tabBin` b
		WHERE b.actual_qty > 0
		GROUP BY b.warehouse
		ORDER BY stock_value DESC
		LIMIT 5
	""", as_dict=True)

	# Slow-moving items (no movement in 60 days)
	slow_moving = frappe.db.sql("""
		SELECT COUNT(DISTINCT item_code)
		FROM `tabBin`
		WHERE actual_qty > 0
		AND item_code NOT IN (
			SELECT DISTINCT item_code FROM `tabStock Ledger Entry`
			WHERE posting_date >= %s AND is_cancelled = 0
		)
	""", add_days(today(), -60))[0][0]

	return {
		"below_reorder_count": below_reorder,
		"reorder_items": reorder_items,
		"open_purchase_orders": open_pos.count,
		"open_po_value": flt(open_pos.total_value),
		"total_stock_value": flt(total_stock_value),
		"warehouse_summary": warehouse_summary,
		"slow_moving_items": slow_moving,
	}


@frappe.whitelist()
def get_stock_movement_trend():
	"""Return daily stock in/out trend for the last 30 days."""
	frappe.has_permission("Stock Ledger Entry", "read", throw=True)
	from_date = add_days(today(), -30)

	trend = frappe.db.sql("""
		SELECT
			posting_date as date,
			SUM(CASE WHEN actual_qty > 0 THEN actual_qty ELSE 0 END) as stock_in,
			SUM(CASE WHEN actual_qty < 0 THEN ABS(actual_qty) ELSE 0 END) as stock_out
		FROM `tabStock Ledger Entry`
		WHERE posting_date >= %s AND is_cancelled = 0
		GROUP BY posting_date
		ORDER BY posting_date ASC
	""", from_date, as_dict=True)
	return trend
