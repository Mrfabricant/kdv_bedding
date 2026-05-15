"""
KDV Bedding — Accounts Module
Financial KPIs, supplier performance, and procurement metrics.
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, flt, add_months, get_first_day, get_last_day


@frappe.whitelist()
def get_accounts_kpis():
	"""Return accounts and procurement KPIs for dashboard."""
	frappe.has_permission("Sales Invoice", "read", throw=True)

	this_month_start = get_first_day(today())
	this_month_end = get_last_day(today())
	last_month_start = get_first_day(add_months(today(), -1))
	last_month_end = get_last_day(add_months(today(), -1))

	# Revenue this month vs last month
	revenue_this_month = _get_revenue(this_month_start, this_month_end)
	revenue_last_month = _get_revenue(last_month_start, last_month_end)

	# Outstanding receivables
	outstanding_receivables = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0
	""")[0][0]

	# Overdue receivables
	overdue_receivables = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		AND outstanding_amount > 0
		AND due_date < %s
	""", today())[0][0]

	# Outstanding payables
	outstanding_payables = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0)
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0
	""")[0][0]

	# Gross profit margin (last 30 days)
	from_date = add_days(today(), -30)
	gross_profit = frappe.db.sql("""
		SELECT
			COALESCE(SUM(si.base_grand_total), 0) as revenue,
			COALESCE(SUM(sii.base_amount * sii.valuation_rate / NULLIF(sii.rate, 0)), 0) as cogs
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE si.docstatus = 1
		AND si.posting_date >= %s
	""", from_date, as_dict=True)[0]

	revenue = flt(gross_profit.revenue)
	cogs = flt(gross_profit.cogs)
	gross_margin = round((revenue - cogs) / revenue * 100, 1) if revenue else 0

	# Supplier performance
	supplier_performance = frappe.db.sql("""
		SELECT
			po.supplier,
			po.supplier_name,
			COUNT(po.name) as total_orders,
			SUM(po.base_grand_total) as total_value,
			AVG(DATEDIFF(pr.posting_date, po.transaction_date)) as avg_lead_time,
			SUM(CASE WHEN pr.posting_date <= po.schedule_date THEN 1 ELSE 0 END) as on_time,
			COUNT(pr.name) as received
		FROM `tabPurchase Order` po
		LEFT JOIN `tabPurchase Receipt` pr ON pr.purchase_order = po.name AND pr.docstatus = 1
		WHERE po.docstatus = 1
		AND po.transaction_date >= %s
		GROUP BY po.supplier, po.supplier_name
		ORDER BY total_value DESC
		LIMIT 8
	""", from_date, as_dict=True)

	# On-time delivery rate
	for supplier in supplier_performance:
		received = flt(supplier.received) or 1
		on_time = flt(supplier.on_time)
		supplier["on_time_percent"] = round(on_time / received * 100, 1)
		supplier["avg_lead_time"] = round(flt(supplier.avg_lead_time), 1)

	# Cash flow summary
	receipts = frappe.db.sql("""
		SELECT COALESCE(SUM(paid_amount), 0)
		FROM `tabPayment Entry`
		WHERE docstatus = 1
		AND payment_type = 'Receive'
		AND posting_date >= %s
	""", this_month_start)[0][0]

	payments = frappe.db.sql("""
		SELECT COALESCE(SUM(paid_amount), 0)
		FROM `tabPayment Entry`
		WHERE docstatus = 1
		AND payment_type = 'Pay'
		AND posting_date >= %s
	""", this_month_start)[0][0]

	return {
		"revenue_this_month": flt(revenue_this_month),
		"revenue_last_month": flt(revenue_last_month),
		"revenue_growth": _growth_percent(revenue_last_month, revenue_this_month),
		"outstanding_receivables": flt(outstanding_receivables),
		"overdue_receivables": flt(overdue_receivables),
		"outstanding_payables": flt(outstanding_payables),
		"gross_margin": gross_margin,
		"supplier_performance": supplier_performance,
		"cash_receipts": flt(receipts),
		"cash_payments": flt(payments),
		"net_cash_flow": flt(receipts) - flt(payments),
	}


def _get_revenue(from_date, to_date):
	return frappe.db.sql("""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))[0][0]


def _growth_percent(previous, current):
	if not previous:
		return 0
	return round((flt(current) - flt(previous)) / flt(previous) * 100, 1)
