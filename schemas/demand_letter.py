from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class BasicInfo(BaseModel):
    letter_date: str = Field(..., alias='letterDate')
    letter_number: Optional[str] = Field(None, alias='letterNumber')
    subject: str
    urgency: Literal['Low', 'Medium', 'High', 'Urgent']
    category: Literal['Payment Demand', 'Contract Breach', 'Service Issue', 'Other']

class SenderInfo(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    signature: Optional[str] = None

class RecipientInfo(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class DemandInfo(BaseModel):
    amount: float
    currency: str
    due_date: Optional[str] = Field(None, alias='dueDate')
    original_due_date: Optional[str] = Field(None, alias='originalDueDate')
    invoice_number: Optional[str] = Field(None, alias='invoiceNumber')
    contract_number: Optional[str] = Field(None, alias='contractNumber')
    description: str
    services_provided: List[str] = Field([], alias='servicesProvided')
    payment_terms: Optional[str] = Field(None, alias='paymentTerms')

class LegalBasis(BaseModel):
    contract_clause: Optional[str] = Field(None, alias='contractClause')
    applicable_laws: List[str] = Field([], alias='applicableLaws')
    previous_communications: List[str] = Field([], alias='previousCommunications')
    evidence_documents: List[str] = Field([], alias='evidenceDocuments')

class Demands(BaseModel):
    primary_demand: str = Field(..., alias='primaryDemand')
    secondary_demands: List[str] = Field([], alias='secondaryDemands')
    deadline: Optional[str] = None
    consequences: List[str] = []
    remedies: List[str] = []

class AdditionalInfo(BaseModel):
    grace_period: Optional[int] = Field(0, alias='gracePeriod')
    interest_rate: Optional[float] = Field(0.0, alias='interestRate')
    late_fees: Optional[float] = Field(0.0, alias='lateFees')
    collection_costs: Optional[bool] = Field(False, alias='collectionCosts')
    legal_action: Optional[bool] = Field(False, alias='legalAction')
    mediation: Optional[bool] = Field(False, alias='mediation')
    arbitration: Optional[bool] = Field(False, alias='arbitration')

class SignatureInfo(BaseModel):
    notarized: Optional[bool] = False
    witness_required: Optional[bool] = Field(False, alias='witnessRequired')
    witness_name: Optional[str] = Field(None, alias='witnessName')
    witness_address: Optional[str] = Field(None, alias='witnessAddress')
    notary_name: Optional[str] = Field(None, alias='notaryName')
    notary_commission: Optional[str] = Field(None, alias='notaryCommission')
    notary_expiry: Optional[str] = Field(None, alias='notaryExpiry')

class Miscellaneous(BaseModel):
    attachments: List[str] = []
    cc_recipients: List[str] = Field([], alias='ccRecipients')
    delivery_method: Literal['Email', 'Registered Mail', 'Personal Delivery', 'Courier'] = Field('Email', alias='deliveryMethod')
    tracking_number: Optional[str] = Field(None, alias='trackingNumber')
    notes: Optional[str] = None

# This is the main model that your endpoint will receive
class DemandLetterData(BaseModel):
    basic_info: BasicInfo = Field(..., alias='basicInfo')
    sender_info: SenderInfo = Field(..., alias='senderInfo')
    recipient_info: RecipientInfo = Field(..., alias='recipientInfo')
    demand_info: DemandInfo = Field(..., alias='demandInfo')
    legal_basis: LegalBasis = Field(..., alias='legalBasis')
    demands: Demands = Field(..., alias='demands')
    additional_info: AdditionalInfo = Field(..., alias='additionalInfo')
    signature_info: SignatureInfo = Field(..., alias='signatureInfo')
    miscellaneous: Miscellaneous = Field(..., alias='miscellaneous')

    class Config:
        populate_by_name = True # This allows using both snake_case and camelCase