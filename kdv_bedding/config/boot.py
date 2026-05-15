import frappe


def boot_session(bootinfo):
    """Add KDV Bedding specific data to boot session"""
    try:
        fiscalisation_enabled = frappe.db.get_single_value(
            "KDV Fiscalisation Settings", "enabled"
        ) or 0
    except Exception:
        fiscalisation_enabled = 0

    bootinfo.kdv_bedding = {
        "version": "1.0.0",
        "fiscalisation_enabled": fiscalisation_enabled,
    }
