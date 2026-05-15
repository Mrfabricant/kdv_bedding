/**
 * KDV Bedding — Client-Side Customisations
 * Extends ERPNext forms with fiscalisation UI, QR code display, and helpers.
 */

// ---------------------------------------------------------------------------
// Sales Invoice — Fiscalisation UI
// ---------------------------------------------------------------------------

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			kdv_bedding.sales_invoice.add_fiscal_buttons(frm);
			kdv_bedding.sales_invoice.show_qr_code(frm);
			kdv_bedding.sales_invoice.show_fiscal_status_indicator(frm);
		}
	},

	on_submit(frm) {
		// Poll for fiscal status after submit
		setTimeout(() => {
			frm.reload_doc();
		}, 3000);
	},
});

const kdv_bedding = {
	sales_invoice: {
		add_fiscal_buttons(frm) {
			const status = frm.doc.custom_fiscal_status;

			if (status === "Failed" || !status) {
				frm.add_custom_button(
					__("Retry Fiscalisation"),
					() => kdv_bedding.sales_invoice.retry_fiscal(frm),
					__("ZIMRA")
				);
			}

			if (status === "Submitted") {
				frm.add_custom_button(
					__("Print Fiscal Receipt"),
					() => kdv_bedding.sales_invoice.print_fiscal(frm),
					__("ZIMRA")
				);
			}

			frm.add_custom_button(
				__("Check ZIMRA Status"),
				() => kdv_bedding.sales_invoice.check_status(frm),
				__("ZIMRA")
			);
		},

		show_fiscal_status_indicator(frm) {
			const status = frm.doc.custom_fiscal_status;
			const statusMap = {
				Submitted: ["green", "✓ Fiscalised"],
				Failed: ["red", "✗ Fiscal Failed"],
				Pending: ["orange", "⏳ Pending"],
				Voided: ["gray", "Voided"],
			};
			const [color, label] = statusMap[status] || ["gray", "Not Fiscalised"];
			frm.page.set_indicator(label, color);
		},

		show_qr_code(frm) {
			const qr = frm.doc.custom_qr_code;
			if (!qr || !qr.startsWith("data:image")) return;

			frm.fields_dict.custom_qr_code.$wrapper.html(`
				<div style="text-align:left; margin-top:8px;">
					<img src="${qr}" style="width:120px; height:120px; border:1px solid #dee2e6; border-radius:4px;" />
					<p style="font-size:11px; color:#6c757d; margin-top:4px;">ZIMRA Fiscal QR Code</p>
				</div>
			`);
		},

		retry_fiscal(frm) {
			frappe.confirm(
				__("Retry fiscalisation for invoice {0}?", [frm.doc.name]),
				() => {
					frappe.call({
						method: "kdv_bedding.fiscalisation.fiscalisation.on_sales_invoice_submit",
						args: { doc: frm.doc },
						freeze: true,
						freeze_message: __("Submitting to ZIMRA..."),
						callback(r) {
							frm.reload_doc();
						},
					});
				}
			);
		},

		check_status(frm) {
			frappe.call({
				method: "kdv_bedding.fiscalisation.fiscalisation.get_fiscal_status",
				args: { invoice_name: frm.doc.name },
				callback(r) {
					if (r.message) {
						const d = r.message;
						frappe.msgprint({
							title: __("ZIMRA Fiscal Status"),
							message: `
								<table class="table table-bordered table-sm">
									<tr><td><b>${__("Status")}</b></td><td>${d.fiscal_status || "—"}</td></tr>
									<tr><td><b>${__("Fiscal Day No")}</b></td><td>${d.fiscal_day_no || "—"}</td></tr>
									<tr><td><b>${__("Receipt Counter")}</b></td><td>${d.receipt_counter || "—"}</td></tr>
								</table>
							`,
							indicator: d.fiscal_status === "Submitted" ? "green" : "orange",
						});
					}
				},
			});
		},

		print_fiscal(frm) {
			const w = window.open("", "_blank");
			const qr = frm.doc.custom_qr_code || "";
			w.document.write(`
				<html><head><title>KDV Fiscal Receipt - ${frm.doc.name}</title>
				<style>
					body { font-family: monospace; font-size: 12px; max-width: 300px; margin: 0 auto; padding: 16px; }
					h2 { font-size: 14px; text-align: center; }
					.line { border-top: 1px dashed #000; margin: 8px 0; }
					.row { display: flex; justify-content: space-between; }
					.center { text-align: center; }
					img { display: block; margin: 8px auto; }
				</style></head><body>
				<h2>KDV BEDDING (PVT) LTD</h2>
				<p class="center">ZIMRA Fiscal Tax Invoice</p>
				<div class="line"></div>
				<div class="row"><span>Invoice:</span><span>${frm.doc.name}</span></div>
				<div class="row"><span>Customer:</span><span>${frm.doc.customer_name}</span></div>
				<div class="row"><span>Date:</span><span>${frm.doc.posting_date}</span></div>
				<div class="row"><span>Receipt No:</span><span>${frm.doc.custom_receipt_counter || "—"}</span></div>
				<div class="row"><span>Fiscal Day:</span><span>${frm.doc.custom_fiscal_day_no || "—"}</span></div>
				<div class="line"></div>
				<div class="row"><span><b>Total:</b></span><span><b>${frm.doc.currency} ${frm.doc.grand_total}</b></span></div>
				<div class="line"></div>
				${qr ? `<img src="${qr}" width="100" height="100" />` : ""}
				<p class="center" style="font-size:10px;">This is a valid ZIMRA fiscal receipt</p>
				</body></html>
			`);
			w.document.close();
			w.print();
		},
	},
};

// ---------------------------------------------------------------------------
// Work Order — Efficiency display
// ---------------------------------------------------------------------------

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		const eff = frm.doc.custom_production_efficiency;
		if (eff !== undefined && eff !== null) {
			const color = eff >= 90 ? "green" : eff >= 70 ? "orange" : "red";
			frm.dashboard.add_indicator(
				__("Efficiency: {0}%", [eff]),
				color
			);
		}
	},
});

// ---------------------------------------------------------------------------
// Migration helper — file upload trigger (called from Migration Page)
// ---------------------------------------------------------------------------

window.kdv_migration = {
	upload_and_import(doctype_key, file_input) {
		const file = file_input.files[0];
		if (!file) return;

		const reader = new FileReader();
		reader.onload = (e) => {
			const content = e.target.result;
			const method_map = {
				customers: "kdv_bedding.migration.sage_pastel_migration.import_customers",
				suppliers: "kdv_bedding.migration.sage_pastel_migration.import_suppliers",
				items: "kdv_bedding.migration.sage_pastel_migration.import_items",
				balances: "kdv_bedding.migration.sage_pastel_migration.import_opening_balances",
			};

			frappe.call({
				method: method_map[doctype_key],
				args: { file_content: content, file_type: "csv" },
				freeze: true,
				freeze_message: `Importing ${doctype_key}...`,
				callback(r) {
					if (r.message) {
						const res = r.message;
						frappe.msgprint({
							title: `Import Complete — ${doctype_key}`,
							message: `
								Created: <b>${res.created || 0}</b><br>
								Updated: <b>${res.updated || 0}</b><br>
								Errors: <b>${(res.errors || []).length}</b>
								${res.errors?.length ? "<br><pre>" + res.errors.join("\n") + "</pre>" : ""}
							`,
							indicator: res.errors?.length ? "orange" : "green",
						});
					}
				},
			});
		};
		reader.readAsText(file);
	},
};
