from pydantic import BaseModel, Field
from typing import Literal, Optional

class AffiantInfo(BaseModel):
    """Information about the person making the affidavit."""
    name: str = Field(..., description="Full name of the affiant.")
    civil_status: Literal['Single', 'Married', 'Widowed', 'Separated', 'Divorced'] = Field(..., alias="civilStatus", description="Civil status of the affiant.")
    address: str = Field(..., description="Current residential address of the affiant.")

class LostItemDetails(BaseModel):
    """Details about the lost item/document."""
    item_type: Literal['Philippine Passport', 'Driver\'s License', 'National ID', 'Birth Certificate', 'TIN ID', 'SSS ID', 'Postal ID', 'PRC ID', 'School ID', 'Other'] = Field(..., alias="itemType", description="Type of lost item/document.")
    other_item_type: Optional[str] = Field(None, alias="otherItemType", description="Specify if item_type is 'Other'.")
    document_number: str = Field(..., alias="documentNumber", description="Document/ID number of the lost item.")
    issue_place: str = Field(..., alias="issuePlace", description="Place where the document was issued.")
    issue_date: str = Field(..., alias="issueDate", description="Date when the document was issued.")

class LossDetails(BaseModel):
    """Details about when and where the loss occurred."""
    discovery_date: str = Field(..., alias="discoveryDate", description="Date when the loss was discovered.")
    loss_location: str = Field(..., alias="lossLocation", description="Location/place where the item was lost.")
    circumstances: str = Field(..., description="Brief description of how the item was lost (e.g., 'I lost my bag containing my passport while traveling').")
    police_report_filed: Optional[bool] = Field(None, alias="policeReportFiled", description="Whether a police report was filed.")

class PurposeInfo(BaseModel):
    """Purpose of executing the affidavit."""
    purpose: str = Field(
        default="to request for a replacement document/passport",
        description="The reason for executing this affidavit."
    )

class WitnessClause(BaseModel):
    """Execution details."""
    execution_date: str = Field(..., alias="executionDate", description="Date of affidavit execution (e.g., '15th day of January').")
    execution_year: str = Field(..., alias="executionYear", description="Year of execution (e.g., '2019', '2025').")
    execution_place: str = Field(..., alias="executionPlace", description="Place where affidavit is executed (e.g., 'Philippine Embassy in Budapest, Hungary').")

class NotaryInfo(BaseModel):
    """Notarization details."""
    notary_location: str = Field(..., alias="notaryLocation", description="Location of notary (e.g., 'Philippine Embassy, Consular Section, Budapest, Hungary').")
    notarization_day: str = Field(..., alias="notarizationDay", description="Day of notarization (e.g., '15th').")
    notarization_month: str = Field(..., alias="notarizationMonth", description="Month of notarization (e.g., 'January').")
    notarization_year: str = Field(..., alias="notarizationYear", description="Year of notarization (e.g., '2019').")
    notarization_place: str = Field(..., alias="notarizationPlace", description="Place of notarization (e.g., 'Philippine Embassy in Hungary').")
    
    affiant_id_type: str = Field(..., alias="affiantIdType", description="Type of ID presented by affiant (e.g., 'Driver's License').")
    affiant_id_issue_place: str = Field(..., alias="affiantIdIssuePlace", description="Place where the ID was issued.")
    affiant_id_issue_date: str = Field(..., alias="affiantIdIssueDate", description="Date when the ID was issued.")
    affiant_id_expiry_date: str = Field(..., alias="affiantIdExpiryDate", description="Expiry date of the ID.")
    
    doc_no: Optional[str] = Field(None, alias="docNo", description="Document number.")
    service_no: Optional[str] = Field(None, alias="serviceNo", description="Service number.")
    or_no: Optional[str] = Field(None, alias="orNo", description="Official Receipt number.")
    fee_paid: Optional[str] = Field(None, alias="feePaid", description="Fee paid amount.")

class AffidavitOfLossData(BaseModel):
    """
    A Pydantic model representing an Affidavit of Loss for lost documents,
    IDs, or personal property. Commonly used for passport replacement,
    ID reissuance, and official documentation of lost items.
    """
    
    affiant: AffiantInfo = Field(..., description="Information about the person making the affidavit.")
    lost_item: LostItemDetails = Field(..., alias="lostItem", description="Details about the lost item/document.")
    loss_details: LossDetails = Field(..., alias="lossDetails", description="Information about when and where the loss occurred.")
    purpose: PurposeInfo = Field(default_factory=PurposeInfo, description="Purpose of executing the affidavit.")
    witness_clause: WitnessClause = Field(..., alias="witnessClause", description="Execution date and place.")
    notary: NotaryInfo = Field(..., description="Notarization details.")

    class Config:
        populate_by_name = True
