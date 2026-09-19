import os
from dotenv import load_dotenv
load_dotenv()
APP_NAME=os.getenv('APP_NAME','AgroLink Angola')
SECRET_KEY=os.getenv('SECRET_KEY','change-me')
DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./agrolink_v11.db')
SELLER_COMMISSION_RATE=float(os.getenv('SELLER_COMMISSION_RATE','0.04'))
TRANSPORTER_COMMISSION_RATE=float(os.getenv('TRANSPORTER_COMMISSION_RATE','0.01'))
BASE_DELIVERY_FEE=float(os.getenv('BASE_DELIVERY_FEE','0'))
DELIVERY_RATE_PER_KM=float(os.getenv('DELIVERY_RATE_PER_KM','150'))
