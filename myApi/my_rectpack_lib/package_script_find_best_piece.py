# encoding=utf8
import sys
# sys.path.append("/home/django/linshi_package_sys/")
from datetime import datetime as dt
import json
import urllib2
from urllib import urlencode
import numpy as np
from package import PackerSolution
from myApi import my_settings
from myApi.tools import send_mail
from package_tools import run_product_rate_func, multi_piece
from base_tools import log_init, Mssql

BEGIN_STATUS = u'新任务'
OK_STATUS = u'运算结束'
CALC_ERROR_STATUS = u'计算出错'
NO_NUM_STATUS = u'没有找到最佳数量'


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


def http_post(num_piece, shape_data, bin_data, comment=None):
    """
    用于脚步访问自身网络，调用django的自身数据库
    :param num_piece:
    :param shape_data:
    :param bin_data:
    :param comment:
    :return:
    """
    url = my_settings.URL_POST
    # 整理input data
    s_data, b_data = multi_piece(num_piece, shape_data, bin_data)
    # 整理描述
    if comment:
        try:
            comment = json.loads(comment)
            comment['Amount'] = num_piece
            comment = json.dumps(comment, ensure_ascii=False)
        except:
            if type(comment) == type('string'):
                comment += ' 最优利用率推荐生产数量=%d' % num_piece
            else:
                comment = json.dumps(comment, ensure_ascii=False)
    else:
        comment = '最优利用率推荐生产数量=%d' % num_piece
    values = {
        'project_comment': comment.encode('utf8'),
        'border': 5,
        'shape_data': s_data,
        'bin_data': b_data
    }
    data = urlencode(values)
    req = urllib2.Request(url, data)  # 生成页面请求的完整数据
    response = None
    try:
        response = urllib2.urlopen(req)  # 发送页面请求
        result = json.loads(response.read())
    except urllib2.URLError as e:
        code = ''
        reason = ''
        if hasattr(e, 'code'):
            # log.error('there is error in http post,error code:%d' % e.code)
            code = e.code
        if hasattr(e, 'reason'):
            # log.error('there is error in http post,error reason:%s' % e.reason)
            reason = e.reason

        # 如果出错发送邮件通知
        body = '<p>运行 package_script_find_best_piece.py 出错，不能post到服务器生产具体方案</p>'
        body += '<p>http respose code:%s, reason: %s</p>' % (str(code), reason)
        send_mail_process(body)
    finally:
        if result:
            response.close()

    return result['url'], result['rates']


def send_mail_process(body):
    # 如果出错发送邮件通知
    mail_to = 'chenliangxu68@163.com'
    send_mail(mail_to, u"林氏利用率API邮件提醒", body)


def generate_work(input_data):
    """
    接受任务，存入数据库，（然后调出数据库里面需要执行的所有任务），马上执行
    :param input_data:
    :return:
    """
    # 更新日期
    created = dt.today()
    log_g = log_init('save_works%s.log' % created.strftime('%Y_%m_%d'))
    log_g.info('Loading data ....')
    try:
        datas = json.loads(input_data['works'])
    except ValueError:
        log_g.error('can not decode json data ....')
        return {'ErrDesc': u'数据格式错误，不符合json格式', 'IsErr': True, 'data': ''}
    result = list()
    insert_list = list()
    update_list = list()
    log_g.info('connecting the DB ....')
    for data in datas:
        # 获取任务状态
        try:
            shape_data = json.dumps(data['ShapeData'], ensure_ascii=False)
            bin_data = json.dumps(data['BinData'], ensure_ascii=False)
            product_comment = json.dumps(data['Product'], ensure_ascii=False)
        except KeyError:
            log_g.error('missing some of data (ShapeData, BinData or Product comment) ....')
            return {'ErrDesc': u'数据中缺少 ShapeData 或者 BinData 的数据', 'IsErr': True, 'data': ''}
        res = has_same_work(shape_data, bin_data)
        # 已存相同的数据，返回任务状态和结果 0:BOMVersion, 1:Status, 2:Url 3:best num
        if res:
            # 如果BOMVersion相同，直接返回结果, BOMVersion不相同，如果状态是运算结束，写入详细结果
            # 如果不行就要重新计算
            if res[0][0] != data['BOMVersion']:
                if res[0][1] == OK_STATUS:
                    insert_same_data(res[0][0], res[0][2], data, shape_data, bin_data, product_comment, res[0][3])
                else:
                    # TODO;有相同数据计算在进行，等一下再查一下
                    insert_list.append({
                        'SkuCode': data['SkuCode'],
                        'Status': 0,
                        'ShapeData': shape_data,
                        'BinData': bin_data,
                        'Created': created,
                        'Product': product_comment,
                        'BOMVersion': data['BOMVersion']
                    })

            else:
                update_list.append({
                    'SkuCode': data['SkuCode'],
                    'Product': product_comment,
                    'BOMVersion': data['BOMVersion'],
                    'Update': created,
                })

            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': res[0][1],
                'Result': res[0][2],
            })

        else:
            # 新任务
            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': 0,
            })

            # 是否有相同的BOMVersion, 有就清除
            find_skucode(data['BOMVersion'])

            # 插入新数据
            insert_list.append({
                'SkuCode': data['SkuCode'],
                'Status': 0,
                'ShapeData': shape_data,
                'BinData': bin_data,
                'Created': created,
                'Product': product_comment,
                'BOMVersion': data['BOMVersion']
            })

    # update db
    log_g.info('saving the new works into DB ....')

    # 更新数据库
    if len(insert_list) > 0:
        insert_work(insert_list)
    if len(update_list) > 0:
        update_new_work(update_list)
    log_g.info('-------------finish and return the result----------------')
    return {'ErrDesc': u'操作成功', 'IsErr': False, 'data': result}, log_g


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


def main_process():
    end_day = dt.today()
    log_main = log_init('find_best_piece%s.log' % end_day.strftime('%Y_%m_%d'))
    log_main.info('connect to the DB and get the jobs....')
    rows = get_data()
    log_main.info('there are %d works today' % len(rows))

    for input_data in rows:
        # 更新另外的数据库,每得到结果更新一次
        content_2 = {}
        error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
        content_2['BOMVersion'] = input_data['BOMVersion']
        content_2['Created'] = dt.today()
        if error:
            content_2['status'] = CALC_ERROR_STATUS
            update_result(content_2)
            log_main.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])
            # 如果出错发送邮件通知
            body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
            send_mail_process(body)
        else:
            log_main.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
                input_data['BOMVersion'], result['piece']))
            # 访问API
            http_response, rates = run_product_rate_func(result['piece'], input_data['ShapeData'],
                                                         input_data['BinData'], comment=input_data['Product'])
            result['url'] = my_settings.BASE_URL + http_response if http_response else 'no url'
            content_2['status'] = OK_STATUS
            content_2['url'] = result['url']
            content_2['rates'] = list()

            if content_2['status'] == OK_STATUS:
                for skucode, rate in rates.items():
                    content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))
                # 更新数据结果
                update_result(content_2)
                log_main.info('finish draw solution BOMVersion=%s' % input_data['BOMVersion'])
            else:
                log_main.info('error in draw solution BOMVersion=%s' % input_data['BOMVersion'])

    log_main.info('-------------------All works has done----------------------------')


def get_work_and_calc(post_data, only_one=True):
    """
    收到任务请求
    第一步（generate_work）：保存任务到数据库，然后通过比对，过虑重复任务，调用所有需要计算的任务
    第二步：找出最佳生产数量，然后求这样的数量的板材排列
    :param post_data:
    :param only_one:
    :return:
    """
    result, log_work = generate_work(post_data)
    yield result
    if not result['IsErr']:
        if only_one and len(result['data']) > 0:
            rows = get_data(bom_version=result['data'][0]['BOMVersion'])
        else:
            rows = get_data()
        log_work.info('connect to the DB and get the data, there are %d works today' % len(rows))
        yield u'<p>一共有%d任务</p>' % len(rows)
        # TODO：队列任务修改，每一个循环一个任务
        for input_data in rows:
            # 更新另外的数据库,每得到结果更新一次
            content_2 = {}
            error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
            content_2['BOMVersion'] = input_data['BOMVersion']
            content_2['SkuCode'] = input_data['SkuCode']
            content_2['Created'] = dt.today()
            if error:
                content_2['status'] = NO_NUM_STATUS
                update_result(content_2)
                log_work.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])
                yield u'<p>运行出错，输入数据有误</p>'
                # 如果出错发送邮件通知
                body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
                send_mail_process(body)
            else:
                log_work.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
                    input_data['BOMVersion'], result['piece']))
                content_2['best_num'] = result['piece']
                # TODO:换成函数
                try:
                    http_response, rates, status = run_product_rate_func(
                        result['piece'], input_data['ShapeData'],
                        input_data['BinData'], comment=input_data['Product'])
                except Exception as e:
                    log_work.error(status)
                    log_work.error(e)
                    content_2['status'] = u'生产项目详细页面出错'
                    update_result(content_2)
                    yield u'<p>计算BOMVersion:%s 出错</p>' % input_data['BOMVersion']
                    continue

                result['url'] = my_settings.BASE_URL + http_response if http_response else 'no url'
                content_2['status'] = status
                content_2['url'] = result['url']
                content_2['rates'] = list()
                if content_2['status'] == OK_STATUS:
                    for skucode, rate in rates.items():
                        content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))

                    # 更新数据结果
                    update_result(content_2)
                    log_work.info('finish draw solution BOMVersion=%s' % input_data['BOMVersion'])
                    yield u'<p>计算BOMVersion:%s 结束，更新数据</p>' % input_data['BOMVersion']
                else:
                    log_work.info('error in draw solution BOMVersion=%s' % input_data['BOMVersion'])
                    yield u'<p>BOMVersion=%s 画图出错, %s</p>' % (input_data['BOMVersion'], content_2['status'])

        log_work.info('-------------------All works has done----------------------------')


if __name__ == '__main__':
    main_process()



