from pydantic import BaseModel,Field,field_validator
from typing import Optional,Literal
class Register(BaseModel):
    full_name:str=Field(min_length=3);phone:str;password:str=Field(min_length=8);role:Literal['buyer','seller','transporter'];province:str;address:str;company_name:Optional[str]=None;farm_name:Optional[str]=None;bi_number:Optional[str]=None
    @field_validator('phone')
    @classmethod
    def valid_phone(cls,v):
        d=''.join(c for c in v if c.isdigit())
        if not ((len(d)==9 and d.startswith('9')) or (len(d)==12 and d.startswith('2449'))):raise ValueError('Telefone angolano inválido')
        return d
class Login(BaseModel):phone:str;password:str
class Product(BaseModel):name:str;description:str='';price_kz:float=Field(gt=0);quantity:float=Field(gt=0);unit:str='kg';category_id:Optional[int]=None;location:str='';photo:Optional[str]=None
class Order(BaseModel):product_id:int;quantity:float=Field(gt=0);delivery_address:str;transport_mode:Literal['buyer','seller','agrolink']
class Review(BaseModel):accepted:bool;note:Optional[str]=None
class Payment(BaseModel):method:Literal['MULTICAIXA_REFERENCE','MULTICAIXA_EXPRESS','IBAN','KWIK'];amount_kz:float=Field(gt=0);reference:Optional[str]=None;transaction_id:Optional[str]=None;idempotency_key:str=Field(min_length=8)
class Code(BaseModel):code:str=Field(min_length=6,max_length=6)
class Location(BaseModel):latitude:float;longitude:float;speed:Optional[float]=None;heading:Optional[float]=None;captured_at:str
class Chat(BaseModel):body:str=Field(min_length=1,max_length=4000)
class Offline(BaseModel):device_id:str;event_type:str;payload:dict
class Vehicle(BaseModel):plate:str;model:str='';vehicle_type:str='camião';capacity_kg:float=0;photo:Optional[str]=None
class AssignTransporter(BaseModel):transporter_id:int;origin:Optional[str]=None
