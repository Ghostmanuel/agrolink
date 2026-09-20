from pydantic import BaseModel,Field,field_validator
from typing import Optional,Literal

class Register(BaseModel):
    full_name:str=Field(min_length=3,max_length=120)
    phone:str
    password:str=Field(min_length=8,max_length=128)
    role:Literal["buyer","seller","transport_company","private_transporter","transporter"]
    province:str=Field(min_length=2,max_length=80)
    address:str=Field(min_length=3,max_length=240)
    company_name:Optional[str]=Field(default=None,max_length=160)
    farm_name:Optional[str]=Field(default=None,max_length=160)
    bi_number:Optional[str]=Field(default=None,max_length=40)
    turnstile_token:Optional[str]=None
    @field_validator("phone")
    @classmethod
    def valid_phone(cls,v):
        d="".join(c for c in v if c.isdigit())
        if d.startswith("244"): d=d[3:]
        if not (len(d)==9 and d.startswith("9")): raise ValueError("Telefone angolano inválido")
        return d

class Login(BaseModel):
    phone:str
    password:str=Field(min_length=8,max_length=128)
    turnstile_token:Optional[str]=None

class RegisterSecurity(BaseModel):
    turnstile_token:Optional[str]=None

class ForgotPassword(BaseModel):
    phone:str
    turnstile_token:Optional[str]=None

class ResetPassword(BaseModel):
    phone:str
    code:str=Field(pattern=r"^\d{6}$")
    new_password:str=Field(min_length=8,max_length=128)
    turnstile_token:Optional[str]=None
class Product(BaseModel):
    name:str=Field(min_length=2,max_length=120); description:str=""; price_kz:float=Field(gt=0); quantity:float=Field(gt=0); unit:str="kg"; category_id:Optional[int]=None; location:str=""; photo:Optional[str]=None
class Order(BaseModel):
    product_id:int; quantity:float=Field(gt=0); delivery_address:str=Field(min_length=3,max_length=240)
class Review(BaseModel): accepted:bool; note:Optional[str]=None
class TransportChoice(BaseModel): mode:Literal["buyer","seller","agrolink"]
class DeliveryQuote(BaseModel):
    distance_km:Optional[float]=Field(default=None,ge=0)
    origin:Optional[str]=None; destination:Optional[str]=None
    origin_lat:Optional[float]=Field(default=None,ge=-90,le=90); origin_lon:Optional[float]=Field(default=None,ge=-180,le=180)
    destination_lat:Optional[float]=Field(default=None,ge=-90,le=90); destination_lon:Optional[float]=Field(default=None,ge=-180,le=180)
class Payment(BaseModel):
    method:Literal["MULTICAIXA_REFERENCE","MULTICAIXA_EXPRESS","IBAN","KWIK"]; amount_kz:float=Field(gt=0); reference:Optional[str]=None; transaction_id:Optional[str]=None; idempotency_key:str=Field(min_length=8,max_length=120)
class Code(BaseModel): code:str=Field(pattern=r"^\d{6}$")
class Location(BaseModel):
    latitude:float=Field(ge=-90,le=90); longitude:float=Field(ge=-180,le=180); speed:Optional[float]=Field(default=None,ge=0); heading:Optional[float]=Field(default=None,ge=0,le=360); captured_at:str
class Chat(BaseModel): body:str=Field(min_length=1,max_length=4000)
class Offline(BaseModel): device_id:str=Field(min_length=1,max_length=120); event_type:str=Field(min_length=1,max_length=120); payload:dict
class Vehicle(BaseModel):
    plate:str=Field(min_length=4,max_length=20); model:str=""; vehicle_type:str="camião"; capacity_kg:float=Field(gt=0); photo:Optional[str]=None; driver_id:Optional[int]=None
class AssignTransporter(BaseModel): transporter_id:int; vehicle_id:Optional[int]=None; origin:Optional[str]=None
class DriverCreate(BaseModel):
    full_name:str=Field(min_length=3,max_length=120); phone:Optional[str]=None; bi_number:str=Field(min_length=4,max_length=40); license_number:Optional[str]=Field(default=None,max_length=60); photo:Optional[str]=None
class DriverUpdate(BaseModel):
    status:Optional[Literal["active","inactive"]]=None; vehicle_id:Optional[int]=None


class FileUpload(BaseModel):
    filename:str=Field(min_length=1,max_length=180); content_type:str=Field(min_length=3,max_length=120); data_base64:str=Field(min_length=10); purpose:str=Field(min_length=2,max_length=60); entity_id:Optional[int]=None
class AdminUserStatus(BaseModel): status:Literal["active","suspended"]
class SettlementPayment(BaseModel): payment_reference:str=Field(min_length=3,max_length=120)
