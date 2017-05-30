# encoding=utf8
import sys
# sys.path.append("/home/linshi_package_sys/")
import os
from datetime import datetime as dt
import sqlalchemy
from sqlalchemy.pool import NullPool
import json
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, bindparam
import logging
import urllib2
from urllib import urlencode
import numpy as np
from package import PackerSolution
from myApi import my_settings
from django_api import settings
from myApi.tools import send_mail


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


def init_connection():
    # 'mysql://uid:pwd@localhost/mydb?charset=utf8'
    engine = create_engine('mssql+pymssql://%s:%s@%s/%s?charset=utf8' % (
        my_settings.HOST_USER,
        my_settings.HOST_PASSWORD,
        my_settings.HOST,
        my_settings.DB
    ), poolclass=NullPool)

    connection = engine.connect()
    metadata = sqlalchemy.schema.MetaData(bind=engine, reflect=True)
    table_schema = sqlalchemy.Table(my_settings.TABLE, metadata, autoload=True)
    return engine, connection, table_schema


def update_data(data):
    # init output connection
    log.info('Saving the result into DB.......')
    _, connection, table_schema = init_connection()
    sql_text = table_schema.update().where(
        table_schema.columns.id == bindparam('row_id')).values(Status=bindparam('status'), Result=bindparam('result'))
    try:
        connection.execute(sql_text, data)
    except Exception as e:
        log.error('error reason', e)
    finally:
        connection.close()


def get_data():
    # init output connection
    log.info('get the table class....')
    engine, connection, table_schema = init_connection()
    # 创建Session:
    Session = sessionmaker(bind=engine)
    session = Session()
    # 获取任务
    res = session.query(table_schema).filter(table_schema.columns.Status == 0).all()
    if len(res) == 0:
        log.info('without work to do, exit now.')
        exit(1)
    # 更新为运行中状态
    sql_text = table_schema.update().where(
        table_schema.columns.id == bindparam('row_id')).values(Status=bindparam('status'))
    content = list()
    for input_data in res:
        content.append({
            'row_id': input_data.id,
            'status': my_settings.RUNNING_STATUS
        })
    connection.execute(sql_text, content)
    # 断开连接
    session.close()
    connection.close()
    return res


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
    s_data, b_data = multi_piece(result['piece'], shape_data, bin_data)

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
    res = send_mail(mail_to, u"林氏利用率API邮件提醒", body)
    if res:
        log.info('Has sent the email to Liangxu email')
    else:
        log.error('Can not send the email')


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
    datas = json.loads(input_data['works'])
    log.info('Loading the data....')
    result = list()
    insert_list = list()
    # connection
    log.info('initiation the db connection....')
    engine, connection, table_schema = init_connection()
    # 创建Session:
    Session = sessionmaker(bind=engine)
    session = Session()

    for data in datas:
        # 获取任务状态
        res = session.query(table_schema.columns.Status, table_schema.columns.Result).filter(
            table_schema.columns.BOMVersion == data['BOMVersion']).first()
        if res:
            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': res.Status,
                'Result': json.loads(res.Result)
            })
        else:
            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': 0,
                'Result': ''
            })
            insert_list.append({
                'BOMVersion': data['BOMVersion'],
                'Status': 0,
                'Result': u' ',
                'ShapeData': json.dumps(data['ShapeData'], ensure_ascii=False),
                'BinData': json.dumps(data['BinData'], ensure_ascii=False),
                'Created': created
            })

    # update db
    if len(insert_list) > 0:
        try:
            log.info('saving %d works into the db....' % len(insert_list))
            connection.execute(table_schema.insert(), insert_list)
            session.commit()
        except Exception as e:
            log.error('can not saving the works into the db')
            log.error(e)

    session.close()
    connection.close()
    log.info('return %d results from db' % len(result))
    return result

if __name__ == '__main__':
    end_day = dt.today()
    log = log_init('find_best_piece%s.log' % end_day.strftime('%Y_%m_%d'))
    rows = get_data()
    log.info('connect to the DB and get the data, there are %d works today' % len(rows))
    # 结果保存,批量更新
    content = list()
    for input_data in rows:
        error, result = find_best_piece(input_data.ShapeData, input_data.BinData)
        if error:
            content.append({
                'row_id': input_data.id,
                'status': my_settings.ERROR_STATUS,
                'result': result['info'],
            })
            log.error('work id=%d has error in input data ' % input_data.id)
            # 如果出错发送邮件通知
            body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
            send_mail_process(body)
        else:
            log.info('finish work id=%d and begin to draw the solution' % input_data.id)
            # 访问API
            http_response = http_post(result['piece'], input_data.ShapeData, input_data.BinData)
            result['url'] = my_settings.BASE_URL + http_response[1:-1] if http_response else 'no url'

            rate_list = list()
            for bin_info in json.loads(input_data.BinData):
                if bin_info['SkuCode'] in result['rates'].keys():
                    bin_info['rate'] = result['rates'][bin_info['SkuCode']]
                    rate_list.append(bin_info)
            result['rates'.encode('utf-8')] = rate_list

            content.append({
                'row_id': input_data.id,
                'status': my_settings.FINISH_STATUS,
                'result': json.dumps(result, ensure_ascii=False),
            })

    update_data(content)
    log.info('-------------------All works has done----------------------------')
