# encoding=utf8
import os
import pymssql
import logging
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
from django_api import settings
from myApi import my_settings


SIDE_CUT = 10  # 板材的切边宽带


def use_rate(use_place, width, height, side_cut=SIDE_CUT):
    total_use = 0
    for b_x, b_y, w, h in use_place:
        total_use += w * h
    return int(
        float(total_use) / (width * height + (width + height) * side_cut - side_cut * side_cut) * 10000) / 10000.0


def find_the_same_position(positions):
    # 初始化，默认每个都不一样，数量都是1
    num_list = [1] * len(positions)
    for i in range(len(positions) - 1, 0, -1):
        for j in range(0, i):
            if positions[i] == positions[j] and num_list[j] != 0:
                num_list[i] += 1
                num_list[j] = 0
    return num_list


def del_same_data(same_bin_list, data_list):
    if len(same_bin_list) != len(data_list):
        return data_list
    res = list()
    for id_data in range(0, len(data_list)):
        if int(same_bin_list[id_data]) != 0:
            res.append(data_list[id_data])
    return res


def draw_one_pic(positions, rates, width=None, height=None, path=None, border=0, num_list=None,
                 shapes=None, empty_positions=None, title=None, bins_list=None):
    # 多个图像需要处理

    if shapes is not None:
        if num_list is None:
            # 返回唯一的排版列表，以及数量
            num_list = find_the_same_position(positions)

    else:
        # 单个图表
        num_list = [1]

    i_p = 0  # 记录板材索引
    i_pic = 1  # 记录图片的索引
    num = len(del_same_data(num_list, num_list))
    fig_height = num * 4
    fig1 = Figure(figsize=(8, fig_height))
    # 使用中文
    # path_ttc = os.path.join(settings.BASE_DIR, 'static')
    # path_ttc = os.path.join(path_ttc, 'simsun.ttc')
    # font_set = FontProperties(fname=path_ttc, size=12)

    if title is not None:
        fig1.suptitle(title, fontweight='bold')
    FigureCanvas(fig1)

    for position in positions:
        if num_list[i_p] != 0:
            ax1 = fig1.add_subplot(num, 1, i_pic, aspect='equal')
            i_pic += 1
            ax1.set_title('rate: %s, piece: %d' % (str(rates[i_p]), num_list[i_p]))
            output_obj = list()
            for v in position:
                output_obj.append(
                    patches.Rectangle((v[0], v[1]), v[2], v[3], edgecolor='black', lw=border, facecolor='none'))

            if empty_positions is not None:
                for em_v in empty_positions[i_p]:
                    output_obj.append(
                        patches.Rectangle(
                            (em_v[0], em_v[1]), em_v[2], em_v[3], edgecolor='black',
                            lw=border, hatch='/', facecolor='none'))

            for p in output_obj:
                ax1.add_patch(p)
                # 计算显示位置
                if shapes is not None:
                    rx, ry = p.get_xy()
                    cx = rx + p.get_width() / 2.0
                    cy = ry + p.get_height() / 2.0
                    # 找到对应的序号
                    p_id = -1
                    if (p.get_width(), p.get_height()) in shapes:
                        p_id = shapes.index((p.get_width(), p.get_height()))
                    if (p.get_height(), p.get_width()) in shapes:
                        p_id = shapes.index((p.get_height(), p.get_width()))

                    # 标记尺寸
                    shape_label = "({p_id}){width}x{height}".format(
                        p_id=p_id, width=p.get_width(), height=p.get_height())

                    rotation = 0
                    if p.get_width() < 450:
                        if p.get_height() > 450 and p.get_width() > 50:
                            rotation = 90
                        else:
                            shape_label = p_id
                    elif p.get_height() < 50:
                        shape_label = p_id

                    ax1.annotate(shape_label, (cx, cy), color='black', weight='bold',
                                 fontsize=8, ha='center', va='center', rotation=rotation)
            # 坐标长度
            if width is not None and height is not None:
                ax1.set_xlim(0, width)
                ax1.set_ylim(0, height)
            elif bins_list is not None:
                ax1.set_xlim(0, bins_list[i_p][0])
                ax1.set_ylim(0, bins_list[i_p][1])
            else:
                ax1.set_xlim(0, 2430)
                ax1.set_ylim(0, 1210)

        i_p += 1

    if path is not None:
        fig1.savefig('%s.png' % path)
    else:
        fig1.show()


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
            print e
            self.conn.rollback()

        self.conn.close()