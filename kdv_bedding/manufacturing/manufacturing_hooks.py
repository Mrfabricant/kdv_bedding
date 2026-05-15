"""
KDV Bedding — Manufacturing Module
Tracks production efficiency, cycle time, and inventory turnover for dashboards.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, date_diff, flt, today, add_days


def on_production_plan_submit(doc, method):
	"""Triggered on Production Plan submit — initialise KPI tracking."""
	frappe.db.set_value("Production Plan", doc.name, {
		"custom_planned_start_date": today(),
		"custom_efficiency_status": "In Progress",
	})


@frappe.whitelist()
def update_production_efficiency():
	"""
	Scheduled daily task.
	Calculates cycle time and efficiency for all in-progress Work Orders.
	"""
	work_orders = frappe.get_all(
		"Work Order",
		filters={"status": ["in", ["In Process", "Completed"]]},
		fields=["name", "planned_start_date", "actual_start_date",
				"planned_end_date", "actual_end_date",
				"qty", "produced_qty", "item_code"],
	)

	for wo in work_orders:
		efficiency = _calculate_efficiency(wo)
		cycle_time = _calculate_cycle_time(wo)
		frappe.db.set_value("Work Order", wo.name, {
			"custom_production_efficiency": efficiency,
			"custom_cycle_time_days": cycle_time,
		})


def _calculate_efficiency(work_order):
	"""Calculate production efficiency as (produced / planned) * 100."""
	if not work_order.qty:
		return 0
	return round(flt(work_order.produced_qty) / flt(work_order.qty) * 100, 2)


def _calculate_cycle_time(work_order):
	"""Calculate actual cycle time in days."""
	start = work_order.actual_start_date or work_order.planned_start_date
	end = work_order.actual_end_date or today()
	if start and end:
		return date_diff(end, start)
	return 0


@frappe.whitelist()
def get_manufacturing_kpis():
	"""
	Return manufacturing KPIs for dashboard.
	Called via frappe.call from dashboard JS.
	"""
	frappe.has_permission("Work Order", "read", throw=True)

	# Inventory Turnover (30-day window)
	from_date = add_days(today(), -30)
	cogs = frappe.db.sql("""
		SELECT COALESCE(SUM(ste.total_incoming_value), 0)
		FROM `tabStock Entry` ste
		WHERE ste.stock_entry_type = 'Manufacture'
		AND ste.posting_date >= %s
		AND ste.docstatus = 1
	""", from_date)[0][0]

	avg_inventory = frappe.db.sql("""
		SELECT COALESCE(AVG(sle.qty_after_transaction * sle.valuation_rate), 0)
		FROM `tabStock Ledger Entry` sle
		WHERE sle.posting_date >= %s
	""", from_date)[0][0]

	inventory_turnover = round(flt(cogs) / flt(avg_inventory), 2) if avg_inventory else 0

	# Average cycle time
	avg_cycle_time = frappe.db.sql("""
		SELECT COALESCE(AVG(custom_cycle_time_days), 0)
		FROM `tabWork Order`
		WHERE status IN ('In Process', 'Completed')
		AND actual_start_date >= %s
	""", from_date)[0][0]

	# Average efficiency
	avg_efficiency = frappe.db.sql("""
		SELECT COALESCE(AVG(custom_production_efficiency), 0)
		FROM `tabWork Order`
		WHERE status = 'Completed'
		AND actual_end_date >= %s
	""", from_date)[0][0]

	# Pending work orders
	pending_wo = frappe.db.count("Work Order", {"status": ["in", ["Not Started", "In Process"]]})

	# Top produced items
	top_items = frappe.db.sql("""
		SELECT item_code, item_name, SUM(produced_qty) as total_produced
		FROM `tabWork Order`
		WHERE status = 'Completed'
		AND actual_end_date >= %s
		GROUP BY item_code, item_name
		ORDER BY total_produced DESC
		LIMIT 5
	""", from_date, as_dict=True)

	return {
		"inventory_turnover": inventory_turnover,
		"avg_cycle_time": round(flt(avg_cycle_time), 1),
		"avg_efficiency": round(flt(avg_efficiency), 1),
		"pending_work_orders": pending_wo,
		"top_produced_items": top_items,
		"period": "Last 30 days",
	}


@frappe.whitelist()
def get_production_timeline():
	"""Return production timeline data for Gantt-style chart."""
	frappe.has_permission("Work Order", "read", throw=True)
	from_date = add_days(today(), -14)

	work_orders = frappe.get_all(
		"Work Order",
		filters={"planned_start_date": [">=", from_date]},
		fields=[
			"name", "item_code", "item_name", "qty", "produced_qty",
			"status", "planned_start_date", "planned_end_date",
			"actual_start_date", "actual_end_date",
			"custom_production_efficiency",
		],
		order_by="planned_start_date asc",
		limit=20,
	)
	return work_orders
