# SQLAlchemy & LangChain DB Bağlantısı
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv
import os

load_dotenv()

def get_df_connection():
    # LangChain'in anlık olarak şemayı okuyabilmesi için SQLDatabase nesnesi dönüyoruz
    db_uri = os.getenv("NEON_DATABASE_URL")
    return SQLDatabase.from_uri(db_uri)