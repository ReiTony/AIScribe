from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class CompanyInfo(BaseModel):
    name: str 
    address: str
    business_nature: str 
    representative_name: str
    representative_title: str

class EmployeeInfo(BaseModel):
    name: str 
    address: str 

class EmploymentDetails(BaseModel):
    position: str 
    status: Literal['Probationary', 'Regular', 'Project', 'Fixed-Term'] = Field(..., description="The initial employment status.")
    probationary_period_months: Optional[int] 
    job_description: str

class CompensationPackage(BaseModel):
    basic_monthly_salary: float 
    currency: str = Field(default="PHP")
    deductions: List[str] = Field(default=["withholding tax", "SSS premiums", "Pag-ibig contributions", "Philhealth dues"], description="List of standard government-required deductions.")
    has_thirteenth_month_pay: bool = Field(True, alias="hasThirteenthMonthPay")
    performance_bonus_clause: Optional[str] 
    salary_adjustment_clause: Optional[str] 

class LeaveBenefits(BaseModel):
    applicable_after_regularization: Optional[bool] = Field(True, alias="applicableAfterRegularization")
    vacation_leave_days: int 
    sick_leave_days: int 
    are_leaves_convertible_to_cash: Optional[bool] = Field(False,)
    accrual_policy: Optional[str]

class WorkConditions(BaseModel):
    primary_location: Optional[str] 
    is_transferable: Optional[bool] = Field(True, alias="isTransferable")
    travel_required: Optional[bool] = Field(True, alias="travelRequired")
    daily_hours: Optional[int] 
    weekly_days: Optional[int] 
    overtime_policy: Optional[str] 

class Covenants(BaseModel):
    non_competition_period_years: Optional[int] 
    non_competition_clause: Optional[str] 
    intellectual_property_clause: Optional[str] 
    confidentiality_clause: Optional[str] 
    exclusivity_clause: Optional[str] 

class TerminationClause(BaseModel):
    termination_grounds: List[str] = Field(..., alias="terminationGrounds", description="List of causes for which employment can be terminated.")
    due_process_mention: bool = Field(True, alias="dueProcessMention", description="Indicates if the contract mentions observing due process for termination.")

class NotaryDetails(BaseModel):
    doc_no: Optional[str] = Field(None, alias="docNo")
    page_no: Optional[str] = Field(None, alias="pageNo")
    book_no: Optional[str] = Field(None, alias="bookNo")
    series_of: Optional[str] = Field(None, alias="seriesOf")

class SignatureInfo(BaseModel):
    witnesses: List[str] = Field([], description="Names of the witnesses to the contract signing.")
    is_notarized: bool = Field(True, alias="isNotarized", description="Indicates if the contract is to be notarized.")
    notary_details: Optional[NotaryDetails] = Field(None, alias="notaryDetails")


# This is the main model that encapsulates the entire Employment Contract
class EmploymentContract(BaseModel):
    """
    A Pydantic model representing a comprehensive Contract of Employment.
    """
    execution_date: str = Field(..., alias="executionDate")
    execution_place: str = Field(..., alias="executionPlace")

    employer: CompanyInfo = Field(..., description="Details of the employer.")
    employee: EmployeeInfo = Field(..., description="Details of the employee.")

    employment_details: EmploymentDetails = Field(..., alias="employmentDetails", description="Core terms of the employment.")
    compensation: CompensationPackage = Field(..., description="Salary and financial benefits.")
    leave_benefits: LeaveBenefits = Field(..., alias="leaveBenefits", description="Leave entitlements.")
    work_conditions: WorkConditions = Field(..., alias="workConditions", description="Work location, hours, and other conditions.")
    covenants: Covenants = Field(..., description="Agreements on confidentiality, non-competition, etc.")
    termination: TerminationClause = Field(..., description="Conditions for employment termination.")

    signature_info: SignatureInfo = Field(..., alias="signatureInfo", description="Information about signatories and notarization.")

    acceptance_clause: str = Field(..., alias="acceptanceClause", description="The clause confirming the employee's understanding and acceptance.")

    class Config:
        populate_by_name = True # Allows using both snake_case and camelCase

 