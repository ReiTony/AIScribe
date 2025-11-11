from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class RepresentativeInfo(BaseModel):
    name: str = Field(..., alias="authorizedRepresentative") 
    designation: str

class CompanyInfo(BaseModel):
    name: str
    address: str
    telephone_no: Optional[str] = Field(None, alias="telephoneNo") 
    representative: RepresentativeInfo

class PromoPeriod(BaseModel):
    start_date: str = Field(..., alias="startDate") 
    end_date: str = Field(..., alias="endDate") 

class PromoTypeDetails(BaseModel):
    types: List[Literal["Discount", "Premium", "Raffle", "Games", "Contests", "Redemption"]]
    others_specify: Optional[str] = Field(None, alias="othersSpecify") 

class CoveredProduct(BaseModel):
    brand: str
    sizes: Optional[str] = None
    specifications: str

class MediaUtilized(BaseModel):
    radio_ad_script: bool = Field(..., alias="radioAdScript") 
    tv_cinema_ad_storyboard: bool = Field(..., alias="tvCinemaAdStoryboard") 
    web_based_ads_screenshots: bool = Field(..., alias="webBasedAdsScreenshots") 
    email_based_ads_transcript: bool = Field(..., alias="emailBasedAdsTranscript") 
    text_based_ads_transcript: bool = Field(..., alias="textBasedAdsTranscript") 
    poster_layout: bool = Field(..., alias="posterLayout") 
    streamer_layout: bool = Field(..., alias="streamerLayout") 
    print_ad_compre: bool = Field(..., alias="printAdCompre") 
    mailers_compre: bool = Field(..., alias="mailersCompre") 
    flyers_compre: bool = Field(..., alias="flyersCompre") 
    others_specify: Optional[str] = Field(None, alias="othersSpecify") 

class ApplicationAttachments(BaseModel):
    list_of_items_on_sale: bool = Field(..., alias="listOfItemsOnSale") 
    total_prizes_or_premium_cost: bool = Field(..., alias="totalPrizesOrPremiumCost") 
    complete_mechanics: bool = Field(..., alias="completeMechanics") 
    control_measures: bool = Field(..., alias="controlMeasures") 
    promo_particulars: bool = Field(..., alias="promoParticulars") 
    registration_requirements: bool = Field(..., alias="registrationRequirements") 
    agreement_of_participating_outlets: bool = Field(..., alias="agreementOfParticipatingOutlets") 
    legal_docs_for_high_value_prizes: bool = Field(..., alias="legalDocsForHighValuePrizes") 
    media_utilized: MediaUtilized = Field(..., alias="mediaUtilized") 

class Undertaking(BaseModel):

    sponsor_representative_name: str = Field(..., alias="sponsorRepresentativeName") 
    advertising_company_representative_name: Optional[str] = Field(None, alias="advertisingCompanyRepresentativeName")
    certified_by_name: str = Field(..., alias="certifiedByName") 


class DtiSalesPromoApplicationData(BaseModel):
    promo_title: str = Field(..., alias="promoTitle")
    application_date: str = Field(..., alias="applicationDate")
    
    sponsor: CompanyInfo
    advertising_agency: Optional[CompanyInfo] = Field(None, alias="advertisingAgency")
    
    promo_period: PromoPeriod = Field(..., alias="promoPeriod")
    promo_type: PromoTypeDetails = Field(..., alias="promoType")
    coverage: Literal["NCR", "Nationwide"]
    
    participating_establishments: List[str] = Field(..., alias="participatingEstablishments")
    products_covered: List[CoveredProduct] = Field(..., alias="productsCovered")
    
    attachments: ApplicationAttachments
    undertaking: Undertaking

    class Config:
        populate_by_name = True