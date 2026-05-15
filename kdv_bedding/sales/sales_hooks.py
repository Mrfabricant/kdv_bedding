"""
KDV Bedding — Sales Module
Tracks sales pipeline, top customers, top sellers, and pending orders.
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, flt, add_months, getdate


def on_sales_order_submit(doc, method):
	"""Triggered on Sales Order submit."""
	# Tag order with financial period for reporting
	frappe.db.set_value("Sales Order", doc.name, {
		"custom_pipeline_status": "Active",
	})


@frappe.whitelist()
def update_sales_pipeline_status():
	"""
	Scheduled hourly task.
	Mark overdue Sales Orders as 'Overdue' in pipeline status.
	"""
	overdue = frappe.get_all(
		"Sales Order",
		filters={
			"status": ["in", ["To Deliver and Bill", "To Bill", "To Deliver"]],
			"delivery_date": ["<", today()],
			"custom_pipeline_status": ["!=", "Overdue"],
		},
		fields=["name"],
	)
	for so in overdue:
		frappe.db.set_value("Sales Order", so.name, "custom_pipeline_status", "Overdue")


@frappe.whitelist()
def get_sales_kpis():
	"""
	Return all sales KPIs for the dashboard.
	30-day rolling window unless otherwise specified.
	"""
	frappe.has_permission("Sales Order", "read", throw=True)
	from_date = add_days(today(), -30)
	this_month_start = today()[:8] + "01"

	# Top sellers (items) by value
	top_sellers = frappe.db.sql("""
		SELECT
			soi.item_code,
			soi.item_name,
			SUM(soi.base_amount) as total_value,
			SUM(soi.qty) as total_qty
		FROM `tabSales Order Item` soi
		INNER JOIN `tabSales Order` so ON so.name = soi.parent
		WHERE so.docstatus = 1
		AND so.transaction_date >= %s
		GROUP BY soi.item_code, soi.item_name
		ORDER BY total_value DESC
		LIMIT 5
	""", from_date, as_dict=True)

	# Top customers by value
	top_customers = frappe.db.sql("""
		SELECT
			so.customer,
			so.customer_name,
			SUM(so.base_grand_total) as total_value,
			COUNT(so.name) as order_count
		FROM `tabSales Order` so
		WHERE so.docstatus = 1
		AND so.transaction_date >= %s
		GROUP BY so.customer, so.customer_name
		ORDER BY total_value DESC
		LIMIT 5
	""", from_date, as_dict=True)

	# Pipeline — pending orders by status
	pipeline = frappe.db.sql("""
		SELECT
			status,
			COUNT(name) as count,
			SUM(base_grand_total) as total_value
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND status NOT IN ('Completed', 'Cancelled', 'Closed')
		GROUP BY status
		ORDER BY count DESC
	""", as_dict=True)

	# Total sales this month
	monthly_sales = frappe.db.sql("""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND transaction_date >= %s
	""", this_month_start)[0][0]

	# Sales trend (daily for last 30 days)
	daily_trend = frappe.db.sql("""
		SELECT
			transaction_date as date,
			COUNT(name) as orders,
			SUM(base_grand_total) as value
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND transaction_date >= %s
		GROUP BY transaction_date
		ORDER BY transaction_date ASC
	""", from_date, as_dict=True)

	# Pending deliveries
	pending_deliveries = frappe.db.count(
		"Sales Order",
		{"docstatus": 1, "status": ["in", ["To Deliver and Bill", "To Deliver"]]}
	)

	# Overdue orders
	overdue_orders = frappe.db.count(
		"Sales Order",
		{
			"docstatus": 1,
			"status": ["in", ["To Deliver and Bill", "To Bill", "To Deliver"]],
			"delivery_date": ["<", today()],
		}
	)

	return {
		"top_sellers": top_sellers,
		"top_customers": top_customers,
		"pipeline": pipeline,
		"monthly_sales": flt(monthly_sales),
		"daily_trend": daily_trend,
		"pending_deliveries": pending_deliveries,
		"overdue_orders": overdue_orders,
		"period": "Last 30 days",
	}


@frappe.whitelist()
def get_sales_vs_target():
	"""Return sales vs target comparison for current month."""
	frappe.has_permission("Sales Order", "read", throw=True)
	this_month = today()[:7]

	actual = frappe.db.sql("""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND DATE_FORMAT(transaction_date, '%%Y-%%m') = %s
	""", this_month)[0][0]

	# Sales target if configured in ERPNext
	target = frappe.db.sql("""
		SELECT COALESCE(SUM(target_amount), 0)
		FROM `tabTarget Detail`
		WHERE parent IN (
			SELECT name FROM `tabSales Person` WHERE enabled = 1
		)
		AND fiscal_year = YEAR(CURDATE())
	""")[0][0]

	return {
		"actual": flt(actual),
		"target": flt(target),
		"achievement_percent": round(flt(actual) / flt(target) * 100, 1) if target else 0,
	}
