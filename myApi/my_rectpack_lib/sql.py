# encoding=utf8
from base_tools import Mssql
from datetime import datetime as dt
import uuid
import json


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


def insert_mix_status(paramets, user_name, other):
    created = dt.today()
    conn = Mssql()
    row_id = uuid.uuid4()
    sql_text = "insert into T_BOM_PlateUtilMixedState values ('%s','%s','%s','%s','%s','%s','%s', '%s', '%s', '%s')" % (
        row_id, u'新任务', ' ', paramets['comment'], user_name,
        created.strftime('%Y-%m-%d %H:%M:%S'), created.strftime('%Y-%m-%d %H:%M:%S'),
        paramets['shape_data'], paramets['bin_data'], other)
    conn.exec_non_query(sql_text)

    # 更新明细
    comments = json.loads(paramets['comment'])
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