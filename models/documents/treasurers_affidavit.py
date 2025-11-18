from pydantic import BaseModel, Field
from typing import Optional

class VenueInfo(BaseModel):
    """Venue where the affidavit is executed."""
    province_city_municipality: str = Field(..., alias="provinceCityMunicipality", description="Province, City, or Municipality.")

class AffiantInfo(BaseModel):
    """Information about the Treasurer making the affidavit."""
    name: str = Field(..., description="Full name of the duly elected Treasurer.")
    cooperative_name: str = Field(..., alias="cooperativeName", description="Full legal name of the CSF cooperative.")

class CapitalStructure(BaseModel):
    """Capital structure details of the CSF cooperative."""
    authorized_share_capital_words: str = Field(..., alias="authorizedShareCapitalWords", description="Authorized share capital in words.")
    authorized_share_capital_amount: float = Field(..., alias="authorizedShareCapitalAmount", description="Authorized share capital amount in PHP.")
    
    subscribed_share_capital_words: str = Field(..., alias="subscribedShareCapitalWords", description="Subscribed share capital in words (at least 25% of authorized).")
    subscribed_share_capital_amount: float = Field(..., alias="subscribedShareCapitalAmount", description="Subscribed share capital amount in PHP.")
    
    paid_up_share_capital_words: str = Field(..., alias="paidUpShareCapitalWords", description="Paid-up share capital in words (at least 25% of subscribed).")
    paid_up_share_capital_amount: float = Field(..., alias="paidUpShareCapitalAmount", description="Paid-up share capital amount in PHP.")
    
    restricted_capital_for_surety_words: str = Field(..., alias="restrictedCapitalForSuretyWords", description="Restricted capital for surety in words.")
    restricted_capital_for_surety_amount: float = Field(..., alias="restrictedCapitalForSuretyAmount", description="Restricted capital for surety amount in PHP.")
    
    currency: str = Field(default="PHP", description="Currency code.")

class WitnessClause(BaseModel):
    """Witness clause date and place."""
    execution_day: str = Field(..., alias="executionDay", description="Day of execution (e.g., '15th').")
    execution_month: str = Field(..., alias="executionMonth", description="Month of execution (e.g., 'January').")
    execution_place: str = Field(..., alias="executionPlace", description="Place of execution (e.g., 'Manila').")

class NotaryInfo(BaseModel):
    """Notarization details."""
    notarization_day: str = Field(..., alias="notarizationDay", description="Day of notarization.")
    notarization_month: str = Field(..., alias="notarizationMonth", description="Month of notarization.")
    notarization_place: str = Field(..., alias="notarizationPlace", description="Place of notarization.")
    affiant_name: str = Field(..., alias="affiantName", description="Affiant's name as stated in notary section.")
    proof_of_identity_type: str = Field(..., alias="proofOfIdentityType", description="Type of ID presented (e.g., 'Driver's License').")
    proof_of_identity_issue_date: str = Field(..., alias="proofOfIdentityIssueDate", description="Date when the ID was issued.")
    proof_of_identity_issue_place: str = Field(..., alias="proofOfIdentityIssuePlace", description="Place where the ID was issued.")
    
    doc_no: Optional[str] = Field(None, alias="docNo", description="Document number in notarial register.")
    page_no: Optional[str] = Field(None, alias="pageNo", description="Page number in notarial register.")
    book_no: Optional[str] = Field(None, alias="bookNo", description="Book number in notarial register.")
    series_of: Optional[str] = Field(None, alias="seriesOf", description="Series year of notarial register.")

class TreasurersAffidavitData(BaseModel):
    """
    A Pydantic model representing a Treasurer's Affidavit for CSF (Credit and 
    Surety Fund) Cooperatives, certifying capital structure and receipt of funds.
    """
    
    venue: VenueInfo = Field(..., description="Venue information (province/city/municipality).")
    affiant: AffiantInfo = Field(..., description="Treasurer's information.")
    capital_structure: CapitalStructure = Field(..., alias="capitalStructure", description="Capital structure details.")
    witness_clause: WitnessClause = Field(..., alias="witnessClause", description="Execution date and place.")
    notary: NotaryInfo = Field(..., description="Notarization details.")

    class Config:
        populate_by_name = True
