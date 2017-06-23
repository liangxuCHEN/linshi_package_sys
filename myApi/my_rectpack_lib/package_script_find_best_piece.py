# encoding=utf8
import sys
# sys.path.append("/home/django/linshi_package_sys/")
import os
from datetime import datetime as dt
import sqlalchemy
from sqlalchemy.pool import NullPool
import json
import pymssql
import logging
import urllib2
from urllib import urlencode
import numpy as np
from package import PackerSolution
from myApi import my_settings
from django_api import settings
from myApi.tools import send_mail


class Mssql:
    def __init__(self):
        self.host = my_settings.BOM_HOST
        self.user = my_settings.BOM_HOST_USER
        self.pwd = my_settings.BOM_HOST_PASSWORD
        self.db = my_settings.BOM_DB

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
            self.conn.rollback()

        self.conn.close()


def log_init(file_name):
    """
    logging.debug('This is debug message')
    logging.info('This is info message')
    logging.warning('This is warning message')
    """
    path = os.path.join(settings.BASE_DIR, 'static')
    path = os.path.join(path, 'log')
    file_name = os.path.join(path, file_name)

    level = logging.DEBUG
    logging.basicConfig(level=level,
                        format='%(asctime)s [line:%(lineno)d] %(levelname)s %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        filename=file_name,
                        filemode='a+')
    return logging


def get_data():
    # init output connection
    log.info('get the table class....')
    conn = Mssql()
    sql_text = "select * From T_BOM_PlateUtilState where Status='新任务'"
    res = conn.exec_query(sql_text)
    content = list()
    for input_data in res:
        content.append({
            'row_id': input_data[0],
            'SkuCode': input_data[1],
            'ShapeData': input_data[3],
            'BinData': input_data[4],
            'Created': dt.today()
        })

    update_running_work(content)
    return content


def find_best_piece(shape_data, bin_data, border=5):

    rate_res = list()
    num_pic = 1
    best_pic = 1
    best_rate = 0
    best_rates = {}

    while True:
        # 创建分析对象
        packer = PackerSolution(
            shape_data,
            bin_data,
            border=border,
            num_pic=num_pic
        )
        if packer.is_valid():
            # 选择几种经常用的算法
            res = packer.find_solution(algo_list=[0, 4, 40, 8, 20, 44, 24])
            # 平均使用率
            total_rate = 0
            for data in res:
                total_rate += data['rate']
            tmp_avg_rate = total_rate / len(res)

            # 记录最大值
            if best_rate < tmp_avg_rate:
                best_rate = tmp_avg_rate
                best_pic = num_pic
                for data in res:
                    best_rates[data['bin_key']] = data['rate']

            if num_pic > my_settings.NUM_SAVE:
                rate_res.append(tmp_avg_rate)
                np_arr = np.array(rate_res[-1 * my_settings.NUM_SAVE:])
                var_rate = np_arr.var()
                if var_rate < my_settings.MAX_VAR_RATE:
                    # 少于阈值返回最佳值
                    return False, {'piece': best_pic, 'rates': best_rates}
            else:
                rate_res.append(tmp_avg_rate)

        else:
            return True, {'info': packer.error_info()}

        num_pic += 1


def http_post(num_piece, shape_data, bin_data):
    url = my_settings.URL_POST
    # 整理input data
    s_data, b_data = multi_piece(num_piece, shape_data, bin_data)

    values = {
        'project_comment': '最优利用率推荐生产数量=%d' % num_piece,
        'border': 5,
        'shape_data': s_data,
        'bin_data': b_data
    }
    data = urlencode(values)
    req = urllib2.Request(url, data)  # 生成页面请求的完整数据
    response_url = None
    response = None
    try:
        response = urllib2.urlopen(req)  # 发送页面请求
        response_url = response.read()
    except urllib2.URLError as e:
        code = ''
        reason = ''
        if hasattr(e, 'code'):
            log.error('there is error in http post,error code:%d' % e.code)
            code = e.code
        if hasattr(e, 'reason'):
            log.error('there is error in http post,error reason:%s' % e.reason)
            reason = e.reason

        # 如果出错发送邮件通知
        body = '<p>运行 package_script_find_best_piece.py 出错，不能post到服务器生产具体方案</p>'
        body += '<p>http respose code:%s, reason: %s</p>' % (str(code), reason)
        send_mail_process(body)
    finally:
        if response_url:
            response.close()

    return response_url


def send_mail_process(body):
    # 如果出错发送邮件通知
    mail_to = 'chenliangxu68@163.com'
    send_mail(mail_to, u"林氏利用率API邮件提醒", body)


def multi_piece(num_piece, shape_data, bin_data):
    shape_data = shape_data.encode('utf-8')
    bin_data = bin_data.encode('utf-8')
    shape_data = json.loads(shape_data)
    for shape in shape_data:
        shape['Amount'] = shape['Amount'] * num_piece
    shape_data = json.dumps(shape_data)
    return shape_data, bin_data


def generate_work(input_data):
    # date
    created = dt.today()
    log = log_init('save_works%s.log' % created.strftime('%Y_%m_%d'))
    log.info('Loading data ....')
    try:
        datas = json.loads(input_data['works'])
    except ValueError:
        log.error('can not decode json data ....')
        return {'ErrDesc': u'数据格式错误，不符合json格式', 'IsErr': True, 'data': ''}
    result = list()
    insert_list = list()
    update_list = list()
    log.info('connecting the DB ....')
    for data in datas:
        # 获取任务状态
        try:
            shape_data = json.dumps(data['ShapeData'], ensure_ascii=False)
            bin_data = json.dumps(data['BinData'], ensure_ascii=False)
        except KeyError:
            log.error('missing the some of data ....')
            return {'ErrDesc': u'数据中缺少 ShapeData 或者 BinData 的数据', 'IsErr': True, 'data': ''}
        res = has_same_work(shape_data, bin_data)
        # 已存在任务，返回任务状态和结果
        if res:
            result.append({
                'SkuCode': data['SkuCode'],
                'Satuts': res[0][1],
                'Result': res[0][2],
            })
        else:
            # 新任务
            result.append({
                'SkuCode': data['SkuCode'],
                'Satuts': 0,
            })
            is_exist = find_skucode(data['SkuCode'])
            # 存在就更新数据，不存在就插入新数据
            if len(is_exist) > 0:
                update_list.append({
                    'SkuCode': data['SkuCode'],
                    'status': 0,
                    'shapeData': shape_data,
                    'binData': bin_data,
                    'created': created
                })
            else:
                insert_list.append({
                    'SkuCode': data['SkuCode'],
                    'Status': 0,
                    'ShapeData': shape_data,
                    'BinData': bin_data,
                    'Created': created
                })

    # update db
    log.info('saving the new works into DB ....')

    # 更新另外的数据库
    if len(insert_list) > 0:
        insert_work(insert_list)
    if len(update_list) > 0:
        update_new_work(update_list)
    log.info('-------------finish and return the result----------------')
    return {'ErrDesc': u'操作成功', 'IsErr': False, 'data': result}


def find_skucode(skucode):
    conn = Mssql()
    sql_text = "SELECT SkuCode FROM T_BOM_PlateUtilState WHERE SkuCode='%s'" % skucode
    return conn.exec_query(sql_text)


def has_same_work(shape_data, bin_data):
    conn = Mssql()
    sql_text = "SELECT SkuCode, Status, Url FROM T_BOM_PlateUtilState WHERE ShapeData='%s' and BinData='%s'" % (
        shape_data, bin_data)
    return conn.exec_query(sql_text)


def insert_work(data):
    insert_data = list()
    for d in data:
        insert_data.append((
            d['SkuCode'], '', d['ShapeData'], d['BinData'],
            u'新任务', d['Created'].strftime('%Y-%m-%d %H:%M:%S'),
            d['Created'].strftime('%Y-%m-%d %H:%M:%S')
        ))
    conn = Mssql()
    insert_sql = "insert into T_BOM_PlateUtilState values (%s,%s,%s,%s,%s,%s,%s)"
    conn.exec_many_query(insert_sql, insert_data)


def update_new_work(data):
    conn = Mssql()
    for d in data:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s' where SkuCode='%s'" % (
            u'新任务', d['Created'].strftime('%Y-%m-%d %H:%M:%S'), d['SkuCode'])
        conn.exec_non_query(update_sql.encode('utf8'))


def update_running_work(data):
    conn = Mssql()
    for d in data:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s' where SkuCode='%s'" % (
            u'运行中', d['Created'].strftime('%Y-%m-%d %H:%M:%S'), d['SkuCode'])
        conn.exec_non_query(update_sql.encode('utf8'))


def update_ending_work(data):
    conn = Mssql()

    if data['status'] == u'计算出错':
        update_sql = "update T_BOM_PlateUtilState set Status='%s',UpdateDate='%s'where SkuCode='%s'" % (
            data['status'],  data['Created'].strftime('%Y-%m-%d %H:%M:%S'), data['SkuCode'])
    else:
        update_sql = "update T_BOM_PlateUtilState set Status='%s',Url='%s',UpdateDate='%s'where SkuCode='%s'" % (
            data['status'], data['url'], data['Created'].strftime('%Y-%m-%d %H:%M:%S'), data['SkuCode'])
    conn.exec_non_query(update_sql.encode('utf8'))


def update_result(data):
    update_ending_work(data)
    conn = Mssql()
    # 先看是否存在, 存在就删除原来数据
    sql_text = "delete T_BOM_PlateUtilUsedRate where ProductSkuCode='%s'" % data['SkuCode']
    conn.exec_non_query(sql_text)
    sql_text = "insert into T_BOM_PlateUtilUsedRate values (%s, %s, %s)"
    conn.exec_many_query(sql_text, data['rates'])


def main_process():
    global log
    end_day = dt.today()
    log = log_init('find_best_piece%s.log' % end_day.strftime('%Y_%m_%d'))
    rows = get_data()
    log.info('connect to the DB and get the data, there are %d works today' % len(rows))
    yield u'<p>一共有%d任务</p>' % len(rows)

    for input_data in rows:
        # 更新另外的数据库,每得到结果更新一次
        content_2 = {}
        error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
        content_2['SkuCode'] = input_data['SkuCode']
        content_2['Created'] = dt.today()
        if error:
            content_2['status'] = u'计算出错'
            update_result(content_2)
            log.error('work id=%d has error in input data ' % input_data['SkuCode'])
            yield u'<p>运行出错，输入数据有误</p>'
            # 如果出错发送邮件通知
            body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
            send_mail_process(body)
        else:
            log.info('finish work skucode=%s and begin to draw the solution' % input_data['SkuCode'])
            # 访问API
            http_response = http_post(result['piece'], input_data['ShapeData'], input_data['BinData'])
            result['url'] = my_settings.BASE_URL + http_response[1:-1] if http_response else 'no url'
            content_2['status'] = u'运算结束'
            content_2['url'] = result['url']
            content_2['rates'] = list()

            for bin_info in json.loads(input_data['BinData']):
                if bin_info['SkuCode'] in result['rates'].keys():
                    bin_info['rate'] = result['rates'][bin_info['SkuCode']]
                    content_2['rates'].append((content_2['SkuCode'], bin_info['SkuCode'], bin_info['rate']))

            # 更新数据结果
            update_result(content_2)
            yield u'<p>计算Skucode:%s 结束，更新数据</p>' % input_data['SkuCode']

    log.info('-------------------All works has done----------------------------')


def get_work_and_calc(post_data):
    result = generate_work(post_data)
    yield result
    if not result['IsErr']:
        global log
        end_day = dt.today()
        log = log_init('find_best_piece%s.log' % end_day.strftime('%Y_%m_%d'))
        rows = get_data()
        log.info('connect to the DB and get the data, there are %d works today' % len(rows))
        yield u'<p>一共有%d任务</p>' % len(rows)

        for input_data in rows:
            # 更新另外的数据库,每得到结果更新一次
            content_2 = {}
            error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
            content_2['SkuCode'] = input_data['SkuCode']
            content_2['Created'] = dt.today()
            if error:
                content_2['status'] = u'计算出错'
                update_result(content_2)
                log.error('work id=%d has error in input data ' % input_data['SkuCode'])
                yield u'<p>运行出错，输入数据有误</p>'
                # 如果出错发送邮件通知
                body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
                send_mail_process(body)
            else:
                log.info('finish work skucode=%s and begin to draw the solution' % input_data['SkuCode'])
                # 访问API
                http_response = http_post(result['piece'], input_data['ShapeData'], input_data['BinData'])
                result['url'] = my_settings.BASE_URL + http_response[1:-1] if http_response else 'no url'
                content_2['status'] = u'运算结束'
                content_2['url'] = result['url']
                content_2['rates'] = list()

                for bin_info in json.loads(input_data['BinData']):
                    if bin_info['SkuCode'] in result['rates'].keys():
                        bin_info['rate'] = result['rates'][bin_info['SkuCode']]
                        content_2['rates'].append((content_2['SkuCode'], bin_info['SkuCode'], bin_info['rate']))

                # 更新数据结果
                update_result(content_2)
                yield u'<p>计算Skucode:%s 结束，更新数据</p>' % input_data['SkuCode']

        log.info('-------------------All works has done----------------------------')

if __name__ == '__main__':
    main_process()


