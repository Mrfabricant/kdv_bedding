import frappe
from frappe.model.document import Document

class KDVFiscalisationSettings(Document):
    def validate(self):
        if self.enabled and not self.device_id:
            frappe.throw("Device ID is required when fiscalisation is enabled")
