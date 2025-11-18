from pydantic import BaseModel, Field
from typing import Literal, Optional

class ContractExecution(BaseModel):
    """Contract execution details."""
    execution_place: str = Field(..., alias="executionPlace", description="Place where the contract is executed.")
    execution_day: str = Field(..., alias="executionDay", description="Day of execution (e.g., '15th').")
    execution_month: str = Field(..., alias="executionMonth", description="Month of execution (e.g., 'January').")
    execution_year: str = Field(..., alias="executionYear", description="Year of execution (e.g., '2023').")

class LessorInfo(BaseModel):
    """Information about the property owner/lessor."""
    name: str = Field(..., description="Full name of the lessor.")
    nationality: str = Field(default="Filipino", description="Nationality of the lessor.")
    civil_status: Literal['Single', 'Married', 'Widowed', 'Separated'] = Field(..., alias="civilStatus", description="Civil status of the lessor.")
    postal_address: str = Field(..., alias="postalAddress", description="Postal address of the lessor.")

class RetireeInfo(BaseModel):
    """Information about the retiree-lessee."""
    name: str = Field(..., description="Full name of the retiree-lessee.")
    nationality: str = Field(..., description="Nationality of the retiree-lessee.")
    civil_status: Literal['Single', 'Married', 'Widowed', 'Separated'] = Field(..., alias="civilStatus", description="Civil status of the retiree-lessee.")
    srrv_visa_number: str = Field(..., alias="srrvVisaNumber", description="SRRV Visa number of the retiree.")
    postal_address: str = Field(..., alias="postalAddress", description="Postal address of the retiree-lessee.")

class PropertyDetails(BaseModel):
    """Details of the property being leased."""
    location: str = Field(..., description="Full address/location of the property.")
    title_type: Literal['TCT', 'CCT', 'OCT', 'Other'] = Field(..., alias="titleType", description="Type of land title.")
    title_number: str = Field(..., alias="titleNumber", description="Title certificate number.")
    property_description: str = Field(..., alias="propertyDescription", description="Detailed description of the property (lot number, area, boundaries, etc.).")

class LeaseTerms(BaseModel):
    """Terms and conditions of the lease."""
    lease_period_years: int = Field(default=25, alias="leasePeriodYears", description="Initial lease period in years.")
    renewable_period_years: int = Field(default=25, alias="renewablePeriodYears", description="Renewable period in years.")
    is_renewable: bool = Field(default=True, alias="isRenewable", description="Whether the lease is renewable.")
    is_transferable: bool = Field(default=True, alias="isTransferable", description="Whether the lease is transferable to heirs.")
    property_use: str = Field(default="residential purposes only", alias="propertyUse", description="Allowed use of the property.")

class RentalDetails(BaseModel):
    """Rental payment details."""
    total_rental_amount: float = Field(..., alias="totalRentalAmount", description="Total rental amount for the lease period.")
    currency: str = Field(default="USD", description="Currency of the rental amount.")
    rental_amount_php: Optional[float] = Field(None, alias="rentalAmountPhp", description="Peso equivalent of rental amount.")
    payment_terms: str = Field(
        default="payable in advance upon approval of lease from PRA",
        alias="paymentTerms",
        description="Payment terms and conditions."
    )
    is_fixed_rate: bool = Field(default=True, alias="isFixedRate", description="Whether rental rate is fixed with no escalation.")
    no_escalation_period_years: int = Field(default=25, alias="noEscalationPeriodYears", description="Period in years with no rental escalation.")

class LeaseExpiry(BaseModel):
    """Lease expiration details."""
    expiry_date: str = Field(..., alias="expiryDate", description="Full expiration date of the lease (e.g., '31st day of December, 2048').")

class Transferability(BaseModel):
    """Transferability and succession details."""
    transferee_name: str = Field(..., alias="transfereeName", description="Name of the person to whom rights will transfer upon lessee's death.")
    transferee_relationship: str = Field(..., alias="transfereeRelationship", description="Relationship to the lessee (e.g., 'spouse', 'child', 'heir').")

class Witnesses(BaseModel):
    """Witness information."""
    witness_1_name: str = Field(..., alias="witness1Name", description="Full name of first witness.")
    witness_2_name: str = Field(..., alias="witness2Name", description="Full name of second witness.")

class NotaryInfo(BaseModel):
    """Notarization details."""
    notary_location: str = Field(..., alias="notaryLocation", description="Location of the notary public.")
    
    party_1_name: str = Field(..., alias="party1Name", description="Name of first party (Lessor).")
    party_1_passport_number: str = Field(..., alias="party1PassportNumber", description="Passport number of first party.")
    party_1_issue_date_place: str = Field(..., alias="party1IssueDatePlace", description="Date and place of passport issuance.")
    
    party_2_name: str = Field(..., alias="party2Name", description="Name of second party (Retiree-Lessee).")
    party_2_passport_number: str = Field(..., alias="party2PassportNumber", description="Passport number of second party.")
    party_2_issue_date_place: str = Field(..., alias="party2IssueDatePlace", description="Date and place of passport issuance.")
    
    notarization_day: str = Field(..., alias="notarizationDay", description="Day of notarization.")
    notarization_month: str = Field(..., alias="notarizationMonth", description="Month of notarization.")
    notarization_year: str = Field(..., alias="notarizationYear", description="Year of notarization.")
    notarization_place: str = Field(..., alias="notarizationPlace", description="Place of notarization.")
    
    doc_no: Optional[str] = Field(None, alias="docNo", description="Document number.")
    page_no: Optional[str] = Field(None, alias="pageNo", description="Page number.")
    book_no: Optional[str] = Field(None, alias="bookNo", description="Book number.")
    series_of: Optional[str] = Field(None, alias="seriesOf", description="Series year.")

class ContractOfLeaseData(BaseModel):
    """
    A Pydantic model representing a Contract of Lease specifically designed for
    Philippine Retirement Authority (PRA) retirees under the SRRV program.
    
    This contract allows foreign retirees to lease land for up to 25 years
    (renewable for another 25 years) for residential purposes.
    """
    
    execution: ContractExecution = Field(..., description="Contract execution details.")
    lessor: LessorInfo = Field(..., description="Information about the property owner.")
    retiree_lessee: RetireeInfo = Field(..., alias="retireeLessee", description="Information about the retiree-lessee.")
    property: PropertyDetails = Field(..., description="Details of the property being leased.")
    lease_terms: LeaseTerms = Field(..., alias="leaseTerms", description="Terms and conditions of the lease.")
    rental: RentalDetails = Field(..., description="Rental payment details.")
    lease_expiry: LeaseExpiry = Field(..., alias="leaseExpiry", description="Lease expiration details.")
    transferability: Transferability = Field(..., description="Transferability details in case of lessee's death.")
    witnesses: Witnesses = Field(..., description="Witness information.")
    notary: NotaryInfo = Field(..., description="Notarization details.")
    
    # Additional contract provisions (with defaults from standard PRA contract)
    improvements_ownership: str = Field(
        default="After final expiration of lease, improvements shall be left for the lessor to enjoy",
        alias="improvementsOwnership",
        description="Terms regarding improvements/construction on the property."
    )
    sublease_allowed: bool = Field(default=False, alias="subleaseAllowed", description="Whether sublease to third parties is allowed.")
    taxes_responsibility: Literal['Lessor', 'Lessee', 'Shared'] = Field(
        default='Lessee',
        alias="taxesResponsibility",
        description="Who bears the realty taxes and maintenance costs."
    )
    pra_approval_required: bool = Field(
        default=True,
        alias="praApprovalRequired",
        description="Whether PRA approval is required for sale, transfer or encumbrance during lease period."
    )

    class Config:
        populate_by_name = True
