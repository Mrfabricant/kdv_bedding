# KDV Bedding — ERPNext v15 Custom App

ERPNext customisation for **KDV Bedding Manufacturing Plant**, Zimbabwe.
Replaces Sage Pastel with a full manufacturing ERP including ZIMRA fiscalisation.

---

## Modules

| Module | Description |
|--------|-------------|
| `fiscalisation` | ZIMRA API integration — invoice signing, QR code, receipt counter |
| `sales` | Sales KPIs — top sellers, top customers, pipeline, daily trend |
| `inventory` | Reorder alerts, stock levels, slow-moving items, PO tracking |
| `manufacturing` | Production efficiency, cycle time, inventory turnover |
| `accounts` | Revenue, receivables, payables, supplier performance |
| `migration` | Sage Pastel CSV import — customers, suppliers, items, balances |
| `api` | Master dashboard API aggregating all KPI modules |

---

## Installation (Local Dev — WSL)

```bash
# 1. Activate bench
cd /home/frappe/kdv-bench
source env/bin/activate

# 2. Copy app into bench
cp -r /path/to/kdv_bedding apps/kdv_bedding

# 3. Install pip requirements
pip install -r apps/kdv_bedding/requirements.txt

# 4. Install app on site
bench --site kdv.localhost install-app kdv_bedding

# 5. Run migration (creates custom fields, fixtures)
bench --site kdv.localhost migrate

# 6. Build assets
bench build --app kdv_bedding

# 7. Start bench
bench start
```

---

## Installation (Staging — erp.novixcore.com)

```bash
# As frappe user on staging server
cd /home/frappe/frappe-bench

# Clone from GitHub (when ready)
bench get-app https://github.com/yourrepo/kdv_bedding --branch main

# Install
bench --site kazishe.local install-app kdv_bedding
bench --site kazishe.local migrate
bench build --app kdv_bedding
sudo supervisorctl restart all
```

---

## ZIMRA Fiscalisation Setup

1. Go to **KDV Fiscalisation Settings** in ERPNext
2. Enable fiscalisation
3. Enter your ZIMRA **Device ID** and **Device Serial No**
4. Set API URL:
   - Sandbox: `https://fdmstest.zimra.co.zw`
   - Production: `https://fdms.zimra.co.zw`
5. Paste your RSA **Private Key (PEM)** from ZIMRA
6. Click **Test ZIMRA Connection**

On Sales Invoice submit, the system will:
- Sign the invoice with your device private key
- POST to ZIMRA API
- Store the fiscal signature, receipt counter, and QR code
- Display QR code on the invoice

---

## Sage Pastel Migration

Upload CSV exports from Sage Pastel via the **Migration** page in ERPNext.

### Expected CSV columns:

**Customers:** `AccountCode, AccountName, ContactName, Email, Phone, Address1, Address2, City, TaxNumber, CreditLimit`

**Suppliers:** `AccountCode, AccountName, ContactName, Email, Phone, Address1, City, TaxNumber`

**Items:** `ItemCode, Description, Category, UOM, SellingPrice, CostPrice, TaxCode, ReorderLevel, ReorderQty`

**Opening Balances:** `AccountCode, AccountName, AccountType, OpeningDebit, OpeningCredit`

---

## Dashboard KPIs

### Sales
- Top 5 sellers by value (30-day)
- Top 5 customers by value (30-day)
- Pipeline by status (Active / Overdue / At Risk)
- Monthly revenue vs target
- Daily sales trend chart

### Inventory
- Items below reorder level (with shortage qty)
- Open purchase orders count and value
- Total stock value
- Warehouse-wise breakdown
- Slow-moving items (no movement 60+ days)

### Manufacturing
- Inventory turnover ratio (30-day)
- Average cycle time (days)
- Average production efficiency (%)
- Pending work orders
- Top produced items

### Accounts & Procurement
- Monthly revenue vs last month
- Outstanding receivables / overdue receivables
- Outstanding payables
- Gross profit margin
- Supplier on-time delivery rate
- Net cash flow (this month)

---

## Custom Fields Added

| DocType | Field | Purpose |
|---------|-------|---------|
| Sales Invoice | `custom_fiscal_status` | ZIMRA submission status |
| Sales Invoice | `custom_fiscal_day_no` | ZIMRA fiscal day number |
| Sales Invoice | `custom_receipt_counter` | ZIMRA receipt counter |
| Sales Invoice | `custom_fiscal_signature` | Digital signature |
| Sales Invoice | `custom_qr_code` | QR code (base64 PNG) |
| Sales Invoice | `custom_fiscal_error` | Error message if failed |
| Sales Order | `custom_pipeline_status` | Pipeline tracking |
| Work Order | `custom_production_efficiency` | Efficiency % |
| Work Order | `custom_cycle_time_days` | Cycle time in days |
| Customer | `custom_sage_account_code` | Sage Pastel account code |
| Supplier | `custom_sage_account_code` | Sage Pastel account code |

---

## Scheduled Tasks

| Frequency | Task |
|-----------|------|
| Daily | Check reorder levels & send alerts |
| Daily | Update production efficiency for all WOs |
| Daily | Retry failed ZIMRA submissions |
| Hourly | Update overdue sales order pipeline status |

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2026-05-15 | Initial release |
