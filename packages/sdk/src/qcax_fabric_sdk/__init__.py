from .plugin import PluginDefinition, PluginContextProtocol
from .discovery import discover_entry_points
from .installation import (
    AdmissionTicket,
    InstallationReceipt,
    installed_image_digest_from_record,
    installed_image_digest_from_record_text,
    issue_admission_ticket,
    make_installation_receipt,
    validate_admission_ticket,
    verify_installed_record,
)
