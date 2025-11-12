from .demand_letter import DemandLetterData
from .employment_contract import EmploymentContract
from .sales_promotion_permit import DtiSalesPromoApplicationData
from .service_agreement import ServiceAgreementData
# Add other document schemas here as needed

ALL_SCHEMAS = {
    "demand_letter": DemandLetterData,
    "employment_contract": EmploymentContract,
    "sales_promotion_permit": DtiSalesPromoApplicationData,
    "service_agreement": ServiceAgreementData,
    # Add other document schemas here as needed
}