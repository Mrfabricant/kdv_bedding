app_name = "kdv_bedding"
app_title = "KDV Bedding"
app_publisher = "Kazishe Implementation Team"
app_description = "ERPNext customisation for KDV Bedding Manufacturing Plant"
app_email = "admin@kdv.co.zw"
app_license = "MIT"
app_version = "1.0.0"

# Apps
required_apps = ["frappe", "erpnext"]

# Document Events
doc_events = {
	"Sales Invoice": {
		"on_submit": "kdv_bedding.fiscalisation.fiscalisation.on_sales_invoice_submit",
		"on_cancel": "kdv_bedding.fiscalisation.fiscalisation.on_sales_invoice_cancel",
	},
	"Sales Order": {
		"on_submit": "kdv_bedding.sales.sales_hooks.on_sales_order_submit",
	},
	"Production Plan": {
		"on_submit": "kdv_bedding.manufacturing.manufacturing_hooks.on_production_plan_submit",
	},
	"Stock Entry": {
		"on_submit": "kdv_bedding.inventory.inventory_hooks.on_stock_entry_submit",
	},
}

# Scheduled Tasks
scheduler_events = {
	"daily": [
		"kdv_bedding.inventory.inventory_hooks.check_reorder_levels",
		"kdv_bedding.manufacturing.manufacturing_hooks.update_production_efficiency",
		"kdv_bedding.fiscalisation.fiscalisation.retry_pending_fiscal_submissions",
	],
	"hourly": [
		"kdv_bedding.sales.sales_hooks.update_sales_pipeline_status",
	],
}

# Website Route Rules
website_route_rules = [
	{
		"from_route": "/kdv-dashboard",
		"to_route": "kdv-dashboard"
	},
]

# Fixtures — export these with bench export-fixtures
fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [["module", "in", ["KDV Bedding"]]]
	},
	{
		"doctype": "Property Setter",
		"filters": [["module", "in", ["KDV Bedding"]]]
	},
	{
		"doctype": "Client Script",
		"filters": [["module", "in", ["KDV Bedding"]]]
	},
	{
		"doctype": "Server Script",
		"filters": [["module", "in", ["KDV Bedding"]]]
	},
	{
		"doctype": "Workspace",
		"filters": [["module", "in", ["KDV Bedding"]]]
	},
]

# Custom Doctypes listed in this module
app_include_css = ["/assets/kdv_bedding/css/kdv_bedding.css"]
app_include_js = ["/assets/kdv_bedding/js/kdv_bedding.js"]

# Whitelisted API Methods
override_whitelisted_methods = {}

# Permission Query Conditions
permission_query_conditions = {}

# Boot Session
boot_session = "kdv_bedding.config.boot.boot_session"
