"""
基本的sql操作
"""
from datetime import datetime

from bot.sql_helper import Base, Session
from sqlalchemy import Column, BigInteger, String, DateTime, Integer, case
from sqlalchemy import func
from sqlalchemy import or_
from bot import LOGGER



class Emby(Base):
    """
    emby表，tg主键，默认值lv，us，iv
    """
    __tablename__ = 'emby'
    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    embyid = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    pwd = Column(String(255), nullable=True)
    pwd2 = Column(String(255), nullable=True)
    lv = Column(String(1), default='d')
    cr = Column(DateTime, nullable=True)
    ex = Column(DateTime, nullable=True)
    us = Column(Integer, default=0)
    iv = Column(Integer, default=0)
    ch = Column(DateTime, nullable=True)

class EmbyServerAccount(Base):
    """
    emby_server_accounts 表，(tg, server) 复合主键
    记录某个 tg 在各台 Emby 服务器上的账户实体；emby 表仍是身份/计费/密码的权威源
    """
    __tablename__ = 'emby_server_accounts'
    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    server = Column(String(32), primary_key=True)
    embyid = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    status = Column(String(16), default='active')
    cr = Column(DateTime, nullable=True)


def sql_add_server_account(tg: int, server: str, embyid: str, name: str = None, status: str = 'active') -> bool:
    """
    新增或更新一条服务器账户记录（按 (tg, server) 幂等）
    """
    with Session() as session:
        try:
            row = session.query(EmbyServerAccount).filter(
                EmbyServerAccount.tg == tg, EmbyServerAccount.server == server
            ).first()
            if row is None:
                row = EmbyServerAccount(tg=tg, server=server, cr=datetime.now())
                session.add(row)
            row.embyid = embyid
            row.name = name
            row.status = status
            session.commit()
            return True
        except Exception as e:
            LOGGER.error(f"写入服务器账户记录失败 tg={tg} server={server}: {e}")
            session.rollback()
            return False


def sql_get_server_accounts(tg: int) -> list:
    """
    查询某个 tg 的全部服务器账户记录
    :return: [(server, embyid, name, status)]，按主键顺序
    """
    with Session() as session:
        try:
            rows = session.query(EmbyServerAccount).filter(EmbyServerAccount.tg == tg).all()
            return [(row.server, row.embyid, row.name, row.status) for row in rows]
        except Exception as e:
            LOGGER.error(f"查询服务器账户记录失败 tg={tg}: {e}")
            return []


def sql_delete_server_account(tg: int, server: str = None) -> bool:
    """
    删除某 tg 的服务器账户记录，server 为 None 时删除该 tg 的全部记录
    """
    with Session() as session:
        try:
            query = session.query(EmbyServerAccount).filter(EmbyServerAccount.tg == tg)
            if server is not None:
                query = query.filter(EmbyServerAccount.server == server)
            deleted = query.delete(synchronize_session=False)
            session.commit()
            return deleted > 0
        except Exception as e:
            LOGGER.error(f"删除服务器账户记录失败 tg={tg} server={server}: {e}")
            session.rollback()
            return False


def sql_add_emby(tg: int):
    """
    添加一条emby记录，如果tg已存在则忽略
    """
    with Session() as session:
        try:
            emby = Emby(tg=tg)
            session.add(emby)
            session.commit()
        except:
            pass

def sql_delete_emby_by_tg(tg):
    """
    根据tg删除一条emby记录
    """
    with Session() as session:
        try:
            emby = session.query(Emby).filter(Emby.tg == tg).first()
            if emby:
                session.delete(emby)
                # 一并清理该用户在各地 Emby 的账户记录，避免残留
                session.query(EmbyServerAccount).filter(EmbyServerAccount.tg == tg).delete(synchronize_session=False)
                session.commit()
                LOGGER.info(f"删除数据库记录成功 {tg}")
                return True
            else:
                LOGGER.info(f"数据库记录不存在 {tg}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            session.rollback()
            return False

def sql_clear_emby_iv():
    """
    清除所有emby的iv
    """
    with Session() as session:
        try:
            session.query(Emby).update({Emby.iv: 0})
            session.commit()
            return True
        except Exception as e:
            LOGGER.error(f"清除所有emby的iv时发生异常 {e}")
            return False

def sql_delete_emby(tg=None, embyid=None, name=None):
    """
    根据tg, embyid或name删除一条emby记录
    至少需要提供一个参数，如果所有参数都为None，则返回False
    """
    with Session() as session:
        try:
            # 构建条件列表，只包含非None的参数
            conditions = []
            if tg is not None:
                conditions.append(Emby.tg == tg)
            if embyid is not None:
                conditions.append(Emby.embyid == embyid)
            if name is not None:
                conditions.append(Emby.name == name)
            
            # 如果所有参数都为None，返回False
            if not conditions:
                LOGGER.warning("sql_delete_emby: 所有参数都为None，无法删除记录")
                return False
            
            # 使用or_组合所有条件
            condition = or_(*conditions)
            LOGGER.debug(f"删除数据库记录，条件: tg={tg}, embyid={embyid}, name={name}")
            
            # 用filter来过滤，使用with_for_update锁定记录
            emby = session.query(Emby).filter(condition).with_for_update().first()
            if emby:
                LOGGER.info(f"删除数据库记录 {emby.name} - {emby.embyid} - {emby.tg}")
                account_tg = emby.tg
                session.delete(emby)
                # 一并清理该用户在各地 Emby 的账户记录，避免残留
                if account_tg is not None:
                    session.query(EmbyServerAccount).filter(EmbyServerAccount.tg == account_tg).delete(
                        synchronize_session=False
                    )
                try:
                    session.commit()
                    LOGGER.info(f"成功删除数据库记录: tg={tg}, embyid={embyid}, name={name}")
                    return True
                except Exception as e:
                    LOGGER.error(f"删除数据库记录时提交事务失败 {e}")
                    session.rollback()
                    return False
            else:
                LOGGER.info(f"数据库记录不存在: tg={tg}, embyid={embyid}, name={name}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            session.rollback()
            return False


def sql_update_embys(some_list: list, method=None):
    """ 根据list中的tg值批量更新一些值 ，此方法不可更新主键"""
    with Session() as session:
        if method == 'iv':
            try:
                mappings = [{"tg": c[0], "iv": c[1]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                return True
            except:
                session.rollback()
                return False
        if method == 'ex':
            try:
                mappings = [{"tg": c[0], "ex": c[1]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                return True
            except:
                session.rollback()
                return False
        if method == 'bind':
            try:
                # mappings = [{"name": c[0], "embyid": c[1]} for c in some_list] 没有主键不能插入的这是emby表
                mappings = [{"tg": c[0], "name": c[1], "embyid": c[2]} for c in some_list]
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                return True
            except Exception as e:
                print(e)
                session.rollback()
                return False


def sql_get_emby(tg):
    """
    查询一条emby记录，可以根据tg, embyid或者name来查询
    """
    with Session() as session:
        try:
            # 使用or_方法来表示或者的逻辑，如果有tg就用tg，如果有embyid就用embyid，如果有name就用name，如果都没有就返回None
            emby = session.query(Emby).filter(or_(Emby.tg == tg, Emby.name == tg, Emby.embyid == tg)).first()
            return emby
        except:
            return None


# def sql_get_emby_by_embyid(embyid):
#     """
#     Retrieve an Emby object from the database based on the provided Emby ID.
#
#     Parameters:
#         embyid : The Emby ID used to identify the Emby object.
#
#     Returns:
#         tuple: A tuple containing a boolean value indicating whether the retrieval was successful
#                and the retrieved Emby object. If the retrieval was unsuccessful, the boolean value
#                will be False and the Emby object will be None.
#     """
#     with Session() as session:
#         try:
#             emby = session.query(Emby).filter((Emby.embyid == embyid)).first()
#             return True, emby
#         except Exception as e:
#             return False, None


def get_all_emby(condition):
    """
    查询所有emby记录
    """
    with Session() as session:
        try:
            embies = session.query(Emby).filter(condition).all()
            return embies
        except:
            return None


def sql_update_emby(condition, **kwargs):
    """
    更新一条emby记录，根据condition来匹配，然后更新其他的字段
    """
    with Session() as session:
        try:
            # 用filter来过滤，注意要加括号
            emby = session.query(Emby).filter(condition).first()
            if emby is None:
                return False
            # 然后用setattr方法来更新其他的字段，如果有就更新，如果没有就保持原样
            for k, v in kwargs.items():
                setattr(emby, k, v)
            session.commit()
            return True
        except Exception as e:
            LOGGER.error(e)
            return False


#
# def sql_change_emby(name, new_tg):
#     with Session() as session:
#         try:
#             emby = session.query(Emby).filter_by(name=name).first()
#             if emby is None:
#                 return False
#             emby.tg = new_tg
#             session.commit()
#             return True
#         except Exception as e:
#             print(e)
#             return False


def sql_count_emby():
    """
    # 检索有tg和embyid的emby记录的数量，以及Emby.lv =='a'条件下的数量
    # count = sql_count_emby()
    :return: int, int, int
    """
    with Session() as session:
        try:
            # 使用func.count来计算数量，使用filter来过滤条件
            count = session.query(
                func.count(Emby.tg).label("tg_count"),
                func.count(Emby.embyid).label("embyid_count"),
                func.count(case((Emby.lv == "a", 1))).label("lv_a_count")
            ).first()
        except Exception as e:
            # print(e)
            return None, None, None
        else:
            return count.tg_count, count.embyid_count, count.lv_a_count
