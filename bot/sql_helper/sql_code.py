from bot.sql_helper import Base, Session
from sqlalchemy import Column, BigInteger, String, DateTime, Integer

class Code(Base):
    """
    register_code表，code主键，tg,us,used,used_time
    """

    __tablename__ = "Rcode"
    code = Column(String(50), primary_key=True, autoincrement=False)
    tg = Column(BigInteger)
    us = Column(Integer)
    used = Column(BigInteger, nullable=True)
    usedtime = Column(DateTime, nullable=True)

def sql_add_code(code_list: list, tg: int, us: int):
    """批量添加记录，如果code已存在则忽略"""
    with Session() as session:
        try:
            code_list = [Code(code=c, tg=tg, us=us) for c in code_list]
            session.add_all(code_list)
            session.commit()
            return True
        except:
            session.rollback()
            return False
