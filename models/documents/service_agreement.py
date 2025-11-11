from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class PartyInfo(BaseModel):
    """Represents a party (Client or Provider) in the agreement."""
    name: str
    address: str
    representative_name: str
    representative_title: str
    role: Literal['Client', 'Provider'] 

class ServiceItem(BaseModel):
    """Defines a specific service or deliverable."""
    name: str = Field(..., description="Name of the service or personnel position (e.g., 'GIS Support Staff', 'Software Development').")
    description: Optional[str] 
    duration_months: Optional[int] 

class CompensationDetails(BaseModel):
    """Details the payment terms, model, and schedule."""
    payment_model: Literal['Fixed Price', 'Time and Materials', 'Cost-Plus', 'Retainer'] 
    currency: str = Field(default="PHP")
    total_contract_value: Optional[float] 
    rate_details: Optional[str] = Field(None, alias="rateDetails")
    cost_plus_markup_percentage: Optional[float] 
    payment_schedule: str = Field(..., alias="paymentSchedule")
    invoicing_cycle: str = Field(..., alias="invoicingCycle")

class TermAndTermination(BaseModel):
    """Defines the agreement's duration and termination conditions."""
    agreement_term_description: str = Field(..., alias="agreementTermDescription")
    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")
    is_renewable: bool = Field(True, alias="isRenewable")
    termination_for_cause_notice_days: Optional[int]
    termination_convenience_clause: Optional[str] = Field(None, alias="terminationConvenienceClause")

class LegalAndCompliance(BaseModel):
    """A collection of key legal and compliance clauses."""
    relationship_of_parties: Literal['Independent Contractor', 'Other'] 
    confidentiality_clause: str = Field(..., alias="confidentialityClause")
    liability_clause: str = Field(..., description="Clause detailing liability for losses, damages, or negligence.")
    performance_security: Optional[str] = Field(None, alias="performanceSecurity", description="Details of any required performance security (e.g., '5% of contract price via bank guarantee').")
    insurance_requirements: List[str] = Field([], alias="insuranceRequirements", description="List of required insurance coverages.")
    governing_law: str = Field(default="Republic of the Philippines", alias="governingLaw")

class Miscellaneous(BaseModel):
    """Other details and attachments."""
    attached_documents: Optional[List[str]] = Field([], alias="attachedDocuments", description="List of all annexes, exhibits, or schedules that form part of the agreement.")
    notices_address_details: str = Field(..., alias="noticesAddressDetails", description="Instructions on how and where to send official notices.")

# This is the main model that encapsulates the entire Service Agreement
class ServiceAgreementData(BaseModel):
    """
    A Pydantic model for a general Service Agreement, adaptable for manpower,
    BPO, or other professional services.
    """
    agreement_date: str = Field(..., alias="agreementDate", description="The date the agreement is made or signed.")
    agreement_location: str = Field(..., alias="agreementLocation", description="The city/place where the agreement is entered into.")
    
    client: PartyInfo = Field(..., description="The party receiving the services (e.g., 'Principal', 'SPML').")
    provider: PartyInfo = Field(..., description="The party providing the services.")
    
    services_to_be_provided: List[ServiceItem] = Field(..., alias="servicesToBeProvided", description="A list of all services, roles, or deliverables under the agreement.")
    
    compensation: CompensationDetails = Field(..., description="All financial terms related to the services.")
    term_and_termination: TermAndTermination = Field(..., alias="termAndTermination", description="The duration of the agreement and conditions for its termination.")
    legal_and_compliance: LegalAndCompliance = Field(..., alias="legalAndCompliance", description="Key legal clauses governing the relationship and responsibilities.")
    
    miscellaneous: Optional[Miscellaneous] = Field(None, description="Additional clauses, attachments, and notice information.")

    class Config:
        populate_by_name = True
       