# encoding=utf8
import pymssql
from datetime import datetime as dt
import uuid
import json
from mrq.context import log
import sys
reload(sys)
sys.setdefaultencoding("utf-8")


BOM_HOST = '192.168.3.253:1433'
BOM_HOST_USER = 'bsdb'
BOM_HOST_PASSWORD = 'ls123123'
BOM_DB = 'BSPRODUCTCENTER'

BEGIN_STATUS = u'新任务'
OK_STATUS = u'运算结束'
CALC_ERROR_STATUS = u'计算出错'
NO_NUM_STATUS = u'没有找到最佳数量'



class Mssql:
    def __init__(self):
        self.host = BOM_HOST
        self.user = BOM_HOST_USER
        self.pwd = BOM_HOST_PASSWORD
        self.db = BOM_DB

    def __get_connect(self):
        if not self.db:
            raise (NameError, "do not have db information")
        self.conn = pymssql.connect(
            host=self.host,
            user=self.user,
            password=self.pwd,
            database=self.db,
            charset="utf8"
        )
        cur = self.conn.cursor()
        if not cur:
            raise (NameError, "Have some Error")
        else:
            return cur

    def exec_query(self, sql):
        cur = self.__get_connect()
        cur.execute(sql)
        res_list = cur.fetchall()

        # the db object must be closed
        self.conn.close()
        return res_list

    def exec_non_query(self, sql):
        cur = self.__get_connect()
        cur.execute(sql)
        self.conn.commit()
        self.conn.close()

    def exec_many_query(self, sql, param):
        cur = self.__get_connect()
        try:
            cur.executemany(sql, param)
            self.conn.commit()
        except Exception as e:
            print e
            self.conn.rollback()

        self.conn.close()


def update_mix_status_time(guid):
    update_time = dt.today()
    conn = Mssql()
    sql_text = "UPDATE T_BOM_PlateUtilMixedState SET UpdateDate='{update_time}' WHERE Guid='{guid}'".format(
        guid=guid, update_time=update_time.strftime('%Y-%m-%d %H:%M:%S'))
    conn.exec_non_query(sql_text)


def update_mix_status_result(guid, url):
    update_time = dt.today()
    conn = Mssql()
    sql_text = """UPDATE T_BOM_PlateUtilMixedState SET
    UpdateDate='{update_time}', Url='{url}', Status='{status}' WHERE Guid='{guid}'""".format(
        guid=guid, status=u'运算结束', url=url, update_time=update_time.strftime('%Y-%m-%d %H:%M:%S'))
    log.info(sql_text)
    conn.exec_non_query(sql_text)


def update_mix_status(guid=None, status=None):
    if not guid:
        guid = uuid.uuid4()
    if not status:
        status = u'运行出错'
    update_time = dt.today()
    conn = Mssql()
    sql_text = """UPDATE T_BOM_PlateUtilMixedState
    SET UpdateDate='{update_time}', Status='{status}' WHERE Guid='{guid}'""".format(
        guid=guid, status=status, update_time=update_time.strftime('%Y-%m-%d %H:%M:%S'))
    conn.exec_non_query(sql_text)


def insert_mix_status(paramets, comments, user_name, other):
    created = dt.today()
    conn = Mssql()
    row_id = uuid.uuid4()
    sql_text = "insert into T_BOM_PlateUtilMixedState values ('%s','%s','%s','%s','%s','%s','%s', '%s', '%s', '%s')" % (
        row_id, u'新任务', ' ', paramets['comment'], user_name,
        created.strftime('%Y-%m-%d %H:%M:%S'), created.strftime('%Y-%m-%d %H:%M:%S'),
        paramets['shape_data'], paramets['bin_data'], other)
    conn.exec_non_query(sql_text)

    # 整理数据
    insert_data = list()
    for data in comments:
        insert_data.append((
            row_id,
            data['Series'],
            data['SkuCode'],
            data['ItemName'],
            data['SkuName'],
            data['SeriesVersion'],
            data['BOMVersion'],
            data['Amount']
        ))
    sql_text = "insert into T_BOM_PlateUtilMixedDetail values (%s,%s,%s,%s,%s,%s,%s,%s)"
    conn.exec_many_query(sql_text, insert_data)
    return row_id


def insert_same_data(bon_version, url, new_data, shape_data, bin_data, comment, best_num):
    conn = Mssql()
    sql_text = "SELECT * FROM T_BOM_PlateUtilUsedRate WHERE BOMVersion='%s'" % bon_version
    # 拿结果
    res = conn.exec_query(sql_text)

    # 先看是否存在, 存在就删除原来数据
    sql_text = "delete T_BOM_PlateUtilState where BOMVersion='%s'" % new_data['BOMVersion']
    conn.exec_non_query(sql_text)
    sql_text = "delete T_BOM_PlateUtilUsedRate where BOMVersion='%s'" % new_data['BOMVersion']
    conn.exec_non_query(sql_text)

    # 插入新数据
    insert_data = list()
    for data in res:
        insert_data.append((new_data['SkuCode'], new_data['BOMVersion'], data[3], data[4]))

    sql_text = "insert into T_BOM_PlateUtilUsedRate values (%s, %s, %s, %s)"
    conn.exec_many_query(sql_text, insert_data)

    # 插入新的状态
    timestamps = dt.today().strftime('%Y-%m-%d %H:%M:%S')
    sql_text = "insert into T_BOM_PlateUtilState values ('%s','%s','%s','%s','%s','%s','%s','%s','%s', '%s')" % (
        new_data['SkuCode'], new_data['BOMVersion'], comment, url, shape_data,
        bin_data, OK_STATUS, timestamps, timestamps, best_num)
    conn.exec_non_query(sql_text)


def find_skucode(bon_version):
    conn = Mssql()
    sql_text = "SELECT BOMVersion FROM T_BOM_PlateUtilState WHERE BOMVersion='%s'" % bon_version
    res = conn.exec_query(sql_text)
    if len(res) > 0:
        # 先删除（状态表和结果表），再更新
        sql_text = "DELETE T_BOM_PlateUtilState WHERE BOMVersion = '%s'" % bon_version
        conn.exec_non_query(sql_text)
        sql_text = "DELETE T_BOM_PlateUtilUsedRate WHERE BOMVersion = '%s'" % bon_version
        conn.exec_non_query(sql_text)


def get_data(bom_version=None):
    # init output connection
    conn = Mssql()
    if bom_version:
        sql_text = "select * From T_BOM_PlateUtilState where Status='{status}' " \
                   "and BOMVersion='{bom_version}'".format(status=BEGIN_STATUS.encode('utf8'),
                                                           bom_version=bom_version)
    else:
        sql_text = "select * From T_BOM_PlateUtilState where Status='%s'" % BEGIN_STATUS.encode('utf8')
    res = conn.exec_query(sql_text)
    content = list()
    for input_data in res:
        content.append({
            'row_id': input_data[0],
            'SkuCode': input_data[1],
            'ShapeData': input_data[5],
            'BinData': input_data[6],
            'Created': dt.today(),
            'Product': input_data[3],
            'BOMVersion': input_data[2],
        })

    update_running_work(content)
    return content


def update_new_work(data):
    conn = Mssql()

    for d in data:
        update_sql = "update T_BOM_PlateUtilState set Product='%s',UpdateDate='%s',SkuCode='%s'where BOMVersion='%s'" % (
            d['Product'], d['Update'].strftime('%Y-%m-%d %H:%M:%S'), d['SkuCode'], d['BOMVersion'])
        conn.exec_non_query(update_sql.encode('utf8'))


def has_same_work(shape_data, bin_data):
    conn = Mssql()
    sql_text = "SELECT BOMVersion, Status, Url, BestNum FROM T_BOM_PlateUtilState WHERE ShapeData='%s' and BinData='%s'" % (
        shape_data, bin_data)
    return conn.exec_query(sql_text)


def insert_work(data):
    insert_data = list()
    for d in data:
        insert_data.append((
            d['SkuCode'], d['BOMVersion'], d['Product'], '', d['ShapeData'], d['BinData'],
            u'新任务', d['Created'].strftime('%Y-%m-%d %H:%M:%S'),
            d['Created'].strftime('%Y-%m-%d %H:%M:%S'), 0
        ))
    conn = Mssql()
    insert_sql = "insert into T_BOM_PlateUtilState values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%d)"
    conn.exec_many_query(insert_sql, insert_data)


def update_running_work(data):
    conn = Mssql()
    for d in data:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s' where BOMVersion='%s'" % (
            u'运行中', d['Created'].strftime('%Y-%m-%d %H:%M:%S'), d['BOMVersion'])
        conn.exec_non_query(update_sql.encode('utf8'))


def update_middle_result(data):
    # TODO: 保存中间结果
    conn = Mssql()

    if data['status'] == OK_STATUS:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',Url='%s',UpdateDate='%s', BestNum=%d " \
                     "where BOMVersion='%s'" % (data['status'], data['url'],
                                                data["Created"].strftime('%Y-%m-%d %H:%M:%S'),
                                                data['best_num'], data['BOMVersion'])
    elif data['status'] == NO_NUM_STATUS:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s'where BOMVersion='%s'" % (
            data['status'],  data['Created'].strftime('%Y-%m-%d %H:%M:%S'), data['BOMVersion'])
    else:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s', BestNum=%d " \
                     "where BOMVersion='%s'" % (data['status'], data["Created"].strftime('%Y-%m-%d %H:%M:%S'),
                                                data['best_num'], data['BOMVersion'])

    conn.exec_non_query(update_sql.encode('utf8'))


def update_result(data):
    update_middle_result(data)
    conn = Mssql()

    if 'rates' in data.keys():
        # 先看是否存在, 存在就删除原来数据
        sql_text = "delete T_BOM_PlateUtilUsedRate where BOMVersion='%s'" % data['BOMVersion']
        conn.exec_non_query(sql_text)
        sql_text = "insert into T_BOM_PlateUtilUsedRate values (%s, %s, %s, %s)"
        conn.exec_many_query(sql_text, data['rates'])

