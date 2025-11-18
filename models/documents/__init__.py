from .demand_letter import DemandLetterData
from .employment_contract import EmploymentContract
from .sales_promotion_permit import DtiSalesPromoApplicationData
from .service_agreement import ServiceAgreementData
from .treasurers_affidavit import TreasurersAffidavitData
from .affidavit_of_loss import AffidavitOfLossData
from .contract_of_lease import ContractOfLeaseData
# TODO: Add other document schemas here as needed

ALL_SCHEMAS = {
    "demand_letter": DemandLetterData,
    "employment_contract": EmploymentContract,
    "sales_promotion_permit": DtiSalesPromoApplicationData,
    "service_agreement": ServiceAgreementData,
    "treasurers_affidavit": TreasurersAffidavitData,
    "affidavit_of_loss": AffidavitOfLossData,
    "contract_of_lease": ContractOfLeaseData,
    # TODO: Add other document schemas here as needed
}