"""
KDV Bedding — Dashboard API
Aggregates KPIs from all modules for the main dashboard.
"""

import frappe
from frappe import _
from kdv_bedding.sales.sales_hooks import get_sales_kpis
from kdv_bedding.inventory.inventory_hooks import get_inventory_kpis
from kdv_bedding.manufacturing.manufacturing_hooks import get_manufacturing_kpis
from kdv_bedding.accounts.accounts_hooks import get_accounts_kpis


@frappe.whitelist()
def get_all_kpis():
	"""
	Master KPI endpoint — called once by the dashboard to load all data.
	Returns a dict keyed by module.
	"""
	data = {}

	try:
		data["sales"] = get_sales_kpis()
	except Exception as e:
		data["sales"] = {"error": str(e)}

	try:
		data["inventory"] = get_inventory_kpis()
	except Exception as e:
		data["inventory"] = {"error": str(e)}

	try:
		data["manufacturing"] = get_manufacturing_kpis()
	except Exception as e:
		data["manufacturing"] = {"error": str(e)}

	try:
		data["accounts"] = get_accounts_kpis()
	except Exception as e:
		data["accounts"] = {"error": str(e)}

	return data


@frappe.whitelist()
def get_dashboard_summary():
	"""
	Lightweight summary for the top stat cards.
	Fast query — minimal DB load.
	"""
	from frappe.utils import today, add_days, flt

	from_date = add_days(today(), -30)
	this_month_start = today()[:8] + "01"

	# Monthly revenue
	revenue = frappe.db.sql("""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND posting_date >= %s
	""", this_month_start)[0][0]

	# Open sales orders
	open_so = frappe.db.count(
		"Sales Order",
		{"docstatus": 1, "status": ["not in", ["Completed", "Cancelled", "Closed"]]}
	)

	# Items below reorder
	below_reorder = frappe.db.sql("""
		SELECT COUNT(DISTINCT ir.parent)
		FROM `tabItem Reorder` ir
		LEFT JOIN `tabBin` b ON b.item_code = ir.parent AND b.warehouse = ir.warehouse
		WHERE COALESCE(b.actual_qty, 0) <= ir.warehouse_reorder_level
	""")[0][0]

	# Active work orders
	active_wo = frappe.db.count(
		"Work Order", {"status": ["in", ["Not Started", "In Process"]]}
	)

	# Outstanding receivables
	receivables = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0
	""")[0][0]

	# Pending fiscal submissions
	pending_fiscal = frappe.db.count(
		"Sales Invoice",
		{"custom_fiscal_status": "Failed", "docstatus": 1}
	)

	return {
		"monthly_revenue": flt(revenue),
		"open_sales_orders": open_so,
		"items_below_reorder": below_reorder,
		"active_work_orders": active_wo,
		"outstanding_receivables": flt(receivables),
		"pending_fiscal": pending_fiscal,
	}
